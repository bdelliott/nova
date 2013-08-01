#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""The Flavor with extra specs extension

OpenStack API version 1.1 lists "name", "ram", "disk", "vcpus" as flavor
attributes.  This extension adds to that list:

- OS-FLV-WITH-EXT-SPECS:extra_specs
"""

from nova.api.openstack import extensions
from nova.api.openstack import wsgi
from nova.api.openstack import xmlutil
from nova import db


authorize = extensions.soft_extension_authorizer('compute',
                                                 'flavor_with_extra_specs')


class FlavorWithExtraSpecsController(wsgi.Controller):
    def _extend_flavor(self, req, flavor):
        extra_specs = db.flavor_extra_specs_get(req.environ['nova.context'],
                                                flavor['id'])
        key = "%s:extra_specs" % Flavor_with_extra_specs.alias
        flavor[key] = extra_specs

    def _extend_flavors(self, req, flavors):
        for flavor in flavors:
            self._extend_flavor(req, flavor)

    def _show(self, req, resp_obj):
        if not authorize(req.environ['nova.context']):
            return
        if 'flavor' in resp_obj.obj:
            resp_obj.attach(xml=FlavorWithExtraSpecsTemplate())
            self._extend_flavor(req, resp_obj.obj['flavor'])

    @wsgi.extends
    def show(self, req, resp_obj, id):
        return self._show(req, resp_obj)

    @wsgi.extends
    def detail(self, req, resp_obj):
        if not authorize(req.environ['nova.context']):
            return
        resp_obj.attach(xml=FlavorsWithExtraSpecsTemplate())
        self._extend_flavors(req, list(resp_obj.obj['flavors']))


class Flavor_with_extra_specs(extensions.ExtensionDescriptor):
    """Provide extra specs along with flavor data."""

    name = "FlavorWithExtraSpecs"
    alias = "OS-FLV-WITH-EXT-SPECS"
    namespace = ("http://docs.openstack.org/compute/ext/"
                 "flavor_with_extra_specs/api/v2.0")
    updated = "2013-08-01T00:00:00Z"

    def get_controller_extensions(self):
        controller = FlavorWithExtraSpecsController()
        extension = extensions.ControllerExtension(self, 'flavors', controller)
        return [extension]


def make_flavor(elem):
    extra_specs_selector = '%s:extra_specs' % Flavor_with_extra_specs.alias
    ns = Flavor_with_extra_specs.namespace
    extra_spec = xmlutil.TemplateElement("{%s}extra_specs" % ns,
                                         selector=extra_specs_selector)

    spec = xmlutil.SubTemplateElement(extra_spec, xmlutil.Selector(0),
                                      selector=xmlutil.get_items)
    spec.text = 1
    elem.append(extra_spec)


class FlavorWithExtraSpecsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('flavor')
        make_flavor(root)
        alias = Flavor_with_extra_specs.alias
        namespace = Flavor_with_extra_specs.namespace
        return xmlutil.SlaveTemplate(root, 1, nsmap={alias: namespace})


class FlavorsWithExtraSpecsTemplate(xmlutil.TemplateBuilder):
    def construct(self):
        root = xmlutil.TemplateElement('flavors')
        elem = xmlutil.SubTemplateElement(root, 'flavor', selector='flavors')
        make_flavor(elem)
        alias = Flavor_with_extra_specs.alias
        namespace = Flavor_with_extra_specs.namespace
        return xmlutil.SlaveTemplate(root, 1, nsmap={alias: namespace})
