# Copyright (c) 2014 Rackspace Hosting
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

from webob import exc

import six

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova import block_device
from nova import compute
from nova.compute import flavors
from nova.compute import power_state
from nova.compute import task_states
from nova.compute import utils as compute_utils
from nova.compute import vm_states
from nova import exception
from nova.image import glance
from nova.objects import flavor as flavor_obj
from nova.openstack.common.gettextutils import _
from nova.openstack.common import timeutils
from nova.openstack.common import uuidutils
from nova import rpc
from nova import utils

authorize = extensions.extension_authorizer('compute', 'rax-fg-migrations')


class FGMigrationsController(object):
    def __init__(self):
        self.compute_api = compute.API()
        self.glance_image_service = glance.GlanceImageService()

    @wsgi.response(201)
    def create(self, req, body):
        context = req.environ['nova.context']
        authorize(context, action='create')

        if not (wsgi.Controller.is_valid_body(body, 'server')):
            raise exc.HTTPUnprocessableEntity()
        if not (wsgi.Controller.is_valid_body(body, 'scheduler_hints')):
            raise exc.HTTPUnprocessableEntity()

        server_dict = body['server']
        scheduler_hints = body['scheduler_hints']

        self._verify_request_has_required_fields(scheduler_hints, server_dict)
        self._validate_ipv4(server_dict)
        self._validate_server_name(server_dict['name'])
        image = self.get_image(context, server_dict['imageRef'])
        flavor = self.get_flavor(context, server_dict['flavorRef'])
        base_options = self._base_options(body['server'], image, flavor)
        base_options['cell_name'] = scheduler_hints['target_cell']

        try:
            instance, hypervisor_ip = self.compute_api. \
                migrate_from_fg(context, base_options, image, flavor)

            return {'instance_uuid': instance['uuid'],
                    'host_ip': hypervisor_ip}
        except exception.InvalidMetadataSize as e:
            raise exc.HTTPRequestEntityTooLarge(explanation=e.format_message())
        except exception.QuotaError as e:
            raise exc.HTTPRequestEntityTooLarge(explanation=e.format_message(),
                                                headers={'Retry-After': 0})
        except exception.InvalidMetadata as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())

    def _notify_create_end(self, context, instance):
        extra_usage_info = dict(message=_('Success'))
        notifier = rpc.get_notifier(service='api')
        notify = compute_utils.notify_about_instance_usage

        notify(notifier, context, instance, 'create.end', network_info={},
               extra_usage_info=extra_usage_info)

    def _activate_instance(self, instance):
        instance.vm_state = vm_states.ACTIVE
        instance.task_state = None
        instance.power_state = power_state.RUNNING
        instance.launched_at = timeutils.utcnow()
        instance.progress = 100
        instance.save(admin_state_reset=True)

        return instance

    @wsgi.response(202)
    def activate(self, req, id, body):
        context = req.environ['nova.context']
        authorize(context, action='activate')

        try:
            instance = self.compute_api.get(context, id, want_objects=True)
        except exception.NotFound:
            msg = _("Instance could not be found")
            raise exc.HTTPNotFound(explanation=msg)
        instance = self._activate_instance(instance)
        self._notify_create_end(context, instance)

    @wsgi.response(204)
    def delete(self, req, id):
        context = req.environ['nova.context']
        authorize(context, action='delete')
        try:
            instance = self.compute_api.get(context, id, want_objects=True)
            self.compute_api.revert_fg_migration(context, instance)
        except exception.NotFound:
            msg = _("Instance could not be found")
            raise exc.HTTPNotFound(explanation=msg)

    def _verify_request_has_required_fields(self, scheduler_hints,
                                            server_dict):
        required_fields = ['name', 'projectId', 'userId', 'ipv4',
                           'imageRef', 'flavorRef']
        error_msgs = []
        for field in required_fields:
            if field not in server_dict:
                error_msgs.append(_("%s is not defined") % field)

        if "target_cell" not in scheduler_hints:
            error_msgs.append(_('target_cell is not defined'))

        if error_msgs:
            msg = ' ; '.join(error_msgs)
            raise exc.HTTPBadRequest(explanation=msg)

    def _validate_ipv4(self, server):
        if not utils.is_valid_ipv4(server['ipv4']):
            expl = _('accessIPv4 is not proper IPv4 format')
            raise exc.HTTPBadRequest(explanation=expl)

    def get_image(self, context, imageRef):
        if not uuidutils.is_uuid_like(imageRef):
            msg = _("Invalid imageRef provided.")
            raise exc.HTTPBadRequest(explanation=msg)
        try:
            return self.glance_image_service.show(context, imageRef)
        except exception.ImageNotFound:
            msg = _("Cannot find requested image")
            raise exc.HTTPBadRequest(explanation=msg)

    def _validate_server_name(self, value):
        try:
            if isinstance(value, six.string_types):
                value = value.strip()
            utils.check_string_length(value, "Server name", min_length=1,
                                      max_length=255)
        except exception.InvalidInput as e:
            raise exc.HTTPBadRequest(explanation=e.format_message())

    def get_flavor(self, context, flavorRef):
        try:
            return flavor_obj.Flavor.get_by_flavor_id(context, flavorRef)
        except exception.FlavorNotFound:
            msg = _("Cannot find requested flavor")
            raise exc.HTTPBadRequest(explanation=msg)

    def _root_device_name(self, image):
        return block_device.properties_root_device_name(image.get(
            'properties', {}))

    def _base_options(self, server, image, flavor):
        image_properties = image.get('properties', {})
        sys_metadata = flavors.save_flavor_info(dict(), flavor)
        image_sys_metadata = utils.get_system_metadata_from_image(image,
                                                                  flavor)
        sys_metadata.update(image_sys_metadata)
        sys_metadata.setdefault('image_base_image_ref', server['imageRef'])

        return {
            'image_ref': server['imageRef'],
            'power_state': power_state.NOSTATE,
            'vm_state': vm_states.BUILDING,
            'task_state': task_states.SCHEDULING,
            'user_id': server['userId'],
            'project_id': server['projectId'],
            'instance_type_id': flavor['id'],
            'memory_mb': flavor['memory_mb'],
            'vcpus': flavor['vcpus'],
            'root_gb': flavor['root_gb'],
            'ephemeral_gb': flavor['ephemeral_gb'],
            'display_name': server['name'],
            'display_description': server['name'],
            'hostname': utils.sanitize_hostname(server['name']),
            'metadata': server.get('metadata', {}),
            'access_ip_v4': server['ipv4'],
            'root_device_name': self._root_device_name(image),
            'progress': 0,
            'os_type': image_properties.get('os_type'),
            'architecture': image_properties.get('architecture'),
            'vm_mode': image_properties.get('vm_mode'),
            'system_metadata': sys_metadata,
            'reservation_id': utils.generate_uid('r'),
        }


class Fg_migrations(extensions.ExtensionDescriptor):
    """Extension to migrate FG instances."""
    name = "FGMigrations"
    namespace = "http://docs.openstack" \
                ".org/compute/ext/rax-fg-migrations/api/v2.0"
    alias = "rax-fg-migrations"
    updated = "2014-03-05T00:00:00Z"

    def get_resources(self):
        resources = []
        resource = extensions.ResourceExtension('rax-fg-migrations',
                                                FGMigrationsController(),
                                                member_actions={
                                                    'activate': 'POST'})
        resources.append(resource)
        return resources
