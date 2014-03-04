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

from nova.api.openstack.compute.contrib import fg_migrations
from nova.compute import power_state
from nova.compute import task_states
from nova.compute import utils as compute_utils
from nova.compute import vm_states
from nova import context
from nova import exception
from nova.objects import flavor as flavor_obj
from nova.openstack.common.gettextutils import _
from nova.openstack.common import timeutils
from nova import rpc
from nova import test
from nova.tests.api.openstack import fakes
from nova import utils

FAKE_UUID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
HOST_IP = "10.10.1.1"


class FGMigrationsTest(test.NoDBTestCase):
    def setUp(self):
        super(FGMigrationsTest, self).setUp()
        reservation_id = utils.generate_uid('r')
        self.context = context.get_admin_context()
        self.controller = fg_migrations.FGMigrationsController()
        self.image = {
            'properties': {
                'root_device_name': '/dev/xda',
                'os_type': 'linux',
                'architecture': 'x64',
                'vm_mode': 'xen'
                }
        }
        self.flavor = {
            'id': 2,
            'name': 'standard1',
            'memory_mb': 1024,
            'vcpus': 2,
            'root_gb': 20,
            'ephemeral_gb': 10,
            'flavorid': 'ST1',
            'swap': 10,
            'rxtx_factor': 1.1,
            'vcpu_weight': 1,
        }
        self.body = {
            "server": {
                "name": "test1",
                "imageRef": "c3153cde-2d23-4186-b7da-159adbe2858b",
                "flavorRef": "2",
                "projectId": "1234567",
                "userId": "98765",
                "ipv4": "111.111.111.111",
                "metadata": {
                    "foo": "bar"}
            },
            "scheduler_hints": {
                "target_cell": "parent!child"
            }
        }

        self.base_options = {
            'image_ref': 'c3153cde-2d23-4186-b7da-159adbe2858b',
            'power_state': power_state.NOSTATE,
            'vm_state': vm_states.BUILDING,
            'task_state': task_states.SCHEDULING,
            'user_id': '98765',
            'project_id': '1234567',
            'instance_type_id': 2,
            'memory_mb': 1024,
            'vcpus': 2,
            'root_gb': 20,
            'ephemeral_gb': 10,
            'display_name': 'test1',
            'display_description': 'test1',
            'metadata': {'foo': 'bar'},
            'access_ip_v4': '111.111.111.111',
            'root_device_name': '/dev/xda',
            'progress': 0,
            'os_type': 'linux',
            'architecture': 'x64',
            'vm_mode': 'xen',
            'hostname': 'test1',
            'cell_name': 'parent!child',
            'reservation_id': reservation_id,
            'system_metadata': {
                'instance_type_memory_mb': 1024,
                'instance_type_swap': 10,
                'instance_type_vcpu_weight': 1,
                'instance_type_root_gb': 20,
                'instance_type_id': 2,
                'instance_type_name': 'standard1',
                'instance_type_ephemeral_gb': 10,
                'instance_type_rxtx_factor': 1.1,
                'image_architecture': 'x64',
                'image_vm_mode': 'xen',
                'instance_type_flavorid': 'ST1',
                'instance_type_vcpus': 2,
                'image_min_disk': 20,
                'image_root_device_name': '/dev/xda',
                'image_os_type': 'linux',
                'image_base_image_ref': 'c3153cde-2d23-4186-b7da-159adbe2858b'
            }
        }

        def _generate_uid(topic, size=8):
            return reservation_id

        def _show(context, image_uuid):
            return self.image

        class FakeFlavor:
            @classmethod
            def _get_flavor(cls, context, flavorRef):
                return self.flavor

        self.request = fakes.HTTPRequest.blank("", use_admin_context=True)
        self.request.environ['nova.context'] = self.context
        self.stubs.Set(self.controller.glance_image_service, 'show', _show)
        self.stubs.Set(flavor_obj.Flavor, "get_by_flavor_id",
                       FakeFlavor._get_flavor)
        self.stubs.Set(utils, 'generate_uid', _generate_uid)

    def test_create(self):
        instance = {'uuid': FAKE_UUID}
        self.mox.StubOutWithMock(self.controller.compute_api,
                                 "migrate_from_fg")
        self.controller.compute_api.\
            migrate_from_fg(self.context, self.base_options,
            self.image, self.flavor).\
            AndReturn((instance, HOST_IP))
        self.mox.ReplayAll()

        res = self.controller.create(self.request, self.body)

        self.assertEqual(FAKE_UUID, res['instance_uuid'])
        self.assertEqual(HOST_IP, res['host_ip'])

    def test_create_with_valid_body(self):
        self.assertRaises(exc.HTTPUnprocessableEntity, self.controller
        .create, self.request, {'foo': {}})

        self.body.pop('scheduler_hints', None)
        self.assertRaises(exc.HTTPUnprocessableEntity, self.controller
        .create, self.request, self.body)

    def test_create_verify_presence_of_name(self):
        self.body['server'].pop('name', None)
        self.assertRaises(exc.HTTPBadRequest, self.controller
        .create, self.request, self.body)

    def test_create_verfiy_non_empty_name(self):
        self.body['server']['name'] = ' ' * 10
        self.assertRaises(exc.HTTPBadRequest, self.controller
        .create, self.request, self.body)

    def test_create_verify_server_name_too_long(self):
        self.body['server']['name'] = 'A' * 256
        self.assertRaises(exc.HTTPBadRequest, self.controller
        .create, self.request, self.body)

    def test_create_verify_presence_of_image_ref(self):
        self.body['server'].pop('name', None)
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_verify_if_valid_image_ref(self):
        self.body['server']['imageRef'] = ''
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_verify_if_image_exists_in_glance(self):
        self.mox.StubOutWithMock(self.controller.glance_image_service, 'show')
        self.controller.glance_image_service.show(self.context, self.body[
            'server']['imageRef']).AndRaise(exception.ImageNotFound(
            image_id=self.body['server']['imageRef']))
        self.mox.ReplayAll()
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_verify_presence_of_flavor_ref(self):
        self.body['server'].pop('flavorRef', None)
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_validate_flavor_ref(self):
        self.mox.StubOutWithMock(flavor_obj.Flavor, 'get_by_flavor_id')
        flavor_obj.Flavor.get_by_flavor_id(self.context, self.body['server'][
            'flavorRef']).AndRaise(exception.FlavorNotFound(
            flavor_id=self.body['server']['flavorRef']))
        self.mox.ReplayAll()
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_verify_if_project_id_in_request(self):
        self.body['server'].pop('projectId', None)
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_verify_if_user_id_in_request(self):
        self.body['server'].pop('userId', None)
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_validate_metadata_limit_in_request(self):
        self.mox.StubOutWithMock(self.controller.compute_api,
                                 "migrate_from_fg")
        self.controller.compute_api. \
            migrate_from_fg(self.context, self.base_options, self.image,
                            self.flavor). \
            AndRaise(exception.MetadataLimitExceeded(allowed=1))
        self.mox.ReplayAll()

        self.assertRaises(exc.HTTPRequestEntityTooLarge, self.controller
        .create, self.request, self.body)

    def test_create_validate_metadata_in_request(self):
        self.mox.StubOutWithMock(self.controller.compute_api,
                                 "migrate_from_fg")
        self.controller.compute_api. \
            migrate_from_fg(self.context, self.base_options, self.image,
                            self.flavor). \
            AndRaise(exception.InvalidMetadata(reason="Invalid"))
        self.mox.ReplayAll()

        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_validate_metadata_size(self):
        self.mox.StubOutWithMock(self.controller.compute_api,
                                 "migrate_from_fg")
        self.controller.compute_api. \
            migrate_from_fg(self.context, self.base_options, self.image,
                            self.flavor). \
            AndRaise(exception.InvalidMetadataSize(reason="Invalid"))
        self.mox.ReplayAll()

        self.assertRaises(exc.HTTPRequestEntityTooLarge, self.controller
        .create, self.request, self.body)

    def test_create_user_is_authorized(self):
        user_context = context.RequestContext(user_id="123",
                                              project_id='1234',
                                              is_admin=False)
        self.request.environ['nova.context'] = user_context

        self.assertRaises(exception.PolicyNotAuthorized,
                          self.controller.create, self.request, self.body)

    def test_create_verify_presence_of_ipv4(self):
        self.body['server'].pop('ipv4', None)
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_validate_ipv4(self):
        self.body['server']['ipv4'] = "1.2.3.foo"
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_create_verify_presence_of_target_cell(self):
        self.body['scheduler_hints'].pop('target_cell', None)
        self.assertRaises(exc.HTTPBadRequest, self.controller.create,
                          self.request, self.body)

    def test_delete(self):
        instance = {'uuid': FAKE_UUID}
        self.mox.StubOutWithMock(self.controller.compute_api, 'get')
        self.controller.compute_api.get(self.context, FAKE_UUID,
                                        want_objects=True).AndReturn(instance)
        self.mox.StubOutWithMock(self.controller.compute_api,
                                 "revert_fg_migration")
        self.controller.compute_api.revert_fg_migration(self.context, instance)
        self.mox.ReplayAll()

        self.controller.delete(self.request, FAKE_UUID)

    def test_delete_user_is_authorized(self):
        user_context = context.RequestContext(user_id="123",
                                              project_id='1234',
                                              is_admin=False)
        self.request.environ['nova.context'] = user_context

        self.assertRaises(exception.PolicyNotAuthorized,
                          self.controller.delete, self.request, FAKE_UUID)

    def test_delete_should_check_existence_of_instance(self):
        self.mox.StubOutWithMock(self.controller.compute_api, 'get')
        self.controller.compute_api.get(self.context, FAKE_UUID,
                                        want_objects=True). \
            AndRaise(exception.NotFound)
        self.mox.ReplayAll()

        self.assertRaises(exc.HTTPNotFound, self.controller.delete,
                          self.request, FAKE_UUID)


class FGMigrationsActivateInstanceTest(test.NoDBTestCase):
    def setUp(self):
        super(FGMigrationsActivateInstanceTest, self).setUp()

        class FakeInstance():
            def __init__(self):
                self.uuid = FAKE_UUID
                self.vm_state = vm_states.BUILDING
                self.tast_state = task_states.SCHEDULING
                self.power_state = power_state.NOSTATE
                self.launched_at = None
                self.progress = 0

            def save(self, admin_state_reset):
                pass

        self.context = context.get_admin_context()
        self.request = fakes.HTTPRequest.blank("", use_admin_context=True)
        self.request.environ['nova.context'] = self.context
        self.controller = fg_migrations.FGMigrationsController()
        self.instance = FakeInstance()

        def _notify_about_instance_usage(notifier, context, instance,
                                         event_suffix,
                                         network_info=None,
                                         system_metadata=None,
                                         extra_usage_info=None, fault=None):
            pass

        self.stubs.Set(compute_utils, 'notify_about_instance_usage',
                       _notify_about_instance_usage)

        def _get_notifier(service=None, host=None, publisher_id=None):
            return "notifer"

        self.stubs.Set(rpc, 'get_notifier', _get_notifier)

    def test_activate_instance_should_activate_the_instance(self):
        utcnow = 'utc_now'
        self.mox.StubOutWithMock(timeutils, 'utcnow')
        timeutils.utcnow().AndReturn(utcnow)
        self.mox.StubOutWithMock(self.controller.compute_api, 'get')
        self.controller.compute_api.get(self.context, self.instance.uuid,
                                        want_objects=True).AndReturn(
            self.instance)
        self.mox.ReplayAll()

        self.controller.activate(self.request, self.instance.uuid, None)

        self.assertEqual(vm_states.ACTIVE, self.instance.vm_state)
        self.assertIsNone(self.instance.task_state)
        self.assertEqual(power_state.RUNNING, self.instance.power_state)
        self.assertEqual(utcnow, self.instance.launched_at)
        self.assertEqual(100, self.instance.progress)

    def test_activate_instance_should_notify_create_end(self):
        usage_info = dict(message=_('Success'))
        self.mox.StubOutWithMock(self.controller.compute_api, 'get')
        self.controller.compute_api.get(self.context, self.instance.uuid,
                                        want_objects=True). \
            AndReturn(self.instance)
        self.mox.StubOutWithMock(rpc, 'get_notifier')
        rpc.get_notifier(service='api').AndReturn('fake_notifier')
        self.mox.StubOutWithMock(compute_utils, 'notify_about_instance_usage')
        compute_utils.notify_about_instance_usage('fake_notifier',
                                                  self.context,
                                                  self.instance,
                                                  'create.end',
                                                  network_info={},
                                                  extra_usage_info=usage_info)
        self.mox.ReplayAll()

        self.controller.activate(self.request, self.instance.uuid, None)

    def test_activate_instance_should_verify_if_instance_exits(self):
        self.mox.StubOutWithMock(self.controller.compute_api, 'get')
        self.controller.compute_api.get(self.context, FAKE_UUID,
                                        want_objects=True). \
            AndRaise(exception.InstanceNotFound(instance_id=FAKE_UUID))
        self.mox.ReplayAll()

        self.assertRaises(exc.HTTPNotFound, self.controller.activate,
                          self.request, FAKE_UUID, None)

    def test_activate_instance_user_is_authorized(self):
        user_context = context.RequestContext(user_id="123", project_id='1234',
                                              is_admin=False)
        self.request.environ['nova.context'] = user_context

        self.assertRaises(exception.PolicyNotAuthorized,
                          self.controller.activate, self.request, FAKE_UUID,
                          None)
