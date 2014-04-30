#   Copyright 2013 OpenStack Foundation
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

import hashlib

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil


class PublicIPZoneIDController(wsgi.Controller):
    def _extend_server(self, server, instance):
        cell = instance.get("cell_name")
        project = str(instance.get("project_id"))
        if cell:
            sha_hash = hashlib.sha224(project + cell)  # pylint: disable=E1101
            key = '%s:publicIPZoneId' % Public_ip_zone_id.alias
            server[key] = sha_hash.hexdigest()

    @wsgi.extends
    def show(self, req, resp_obj, id):
        # Attach our slave template to the response object
        resp_obj.attach(xml=PublicIPZoneIDTemplate())
        server = resp_obj.obj['server']
        db_instance = req.get_db_instance(server['id'])
        # server['id'] is guaranteed to be in the cache due to
        # the core API adding it in its 'show' method.
        self._extend_server(server, db_instance)

    @wsgi.extends
    def detail(self, req, resp_obj):
        # Attach our slave template to the response object
        resp_obj.attach(xml=PublicIPZoneIDsTemplate())
        for server in resp_obj.obj['servers']:
            db_instance = req.get_db_instance(server['id'])
            # server['id'] is guaranteed to be in the cache due to
            # the core API adding it in its 'detail' method.
            self._extend_server(server, db_instance)


class Public_ip_zone_id(extensions.ExtensionDescriptor):
    """Adds public_ip_zone_id on Servers."""

    name = "PublicIPZoneID"
    alias = "RAX-PUBLIC-IP-ZONE-ID"
    namespace = ("http://docs.openstack.org/compute/ext/"
                 "public_ip_zone_id/api/v1.1")
    updated = "2013-04-29T00:00:00Z"

    def get_controller_extensions(self):
        controller = PublicIPZoneIDController()
        extension = extensions.ControllerExtension(self, 'servers', controller)
        return [extension]


def make_server(elem):
    elem.set('{%s}publicIPZoneId' % Public_ip_zone_id.namespace,
             '%s:publicIPZoneId' % Public_ip_zone_id.alias)


class PublicIPZoneIDTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('server', selector='server')
        make_server(root)
        return xmlutil.SlaveTemplate(root, 1, nsmap={
            Public_ip_zone_id.alias: Public_ip_zone_id.namespace})


class PublicIPZoneIDsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('servers')
        elem = xmlutil.SubTemplateElement(root, 'server', selector='servers')
        make_server(elem)
        return xmlutil.SlaveTemplate(root, 1, nsmap={
            Public_ip_zone_id.alias: Public_ip_zone_id.namespace})
