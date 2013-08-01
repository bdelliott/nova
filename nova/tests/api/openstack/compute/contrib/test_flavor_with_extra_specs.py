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

import datetime
import nova

import webob

from nova.compute import flavors
from nova.openstack.common import jsonutils
from nova import test
from nova.tests.api.openstack import fakes


def fake_get_flavor_by_flavor_id(flavorid, ctxt=None):
    return {
        'id': flavorid,
        'flavorid': flavorid,
        'root_gb': 1,
        'ephemeral_gb': 1,
        'name': u'test',
        'deleted': False,
        'created_at': datetime.datetime(2012, 1, 1, 1, 1, 1, 1),
        'updated_at': None,
        'memory_mb': 512,
        'vcpus': 1,
        'deleted_at': None,
        'vcpu_weight': None,
    }


def fake_get_all_flavors_sorted_list(context, filters, sort_key, sort_dir,
                                     limit, marker):
    return [
        fake_get_flavor_by_flavor_id(1),
        fake_get_flavor_by_flavor_id(2)
    ]


def fake_flavor_extra_specs_get(context, flavor_id):
    return flavor_extra_specs()


def flavor_extra_specs():
    return {
        "key1": "value1",
        "key2": "value2",
        "key3": "value3",
        "key4": "value4",
        "key5": "value5"}


class FlavorWithExtraSpecsTest(test.TestCase):
    def setUp(self):
        super(FlavorWithExtraSpecsTest, self).setUp()
        ext = ('nova.api.openstack.compute.contrib'
               '.flavor_with_extra_specs.Flavor_with_extra_specs')
        self.flags(osapi_compute_extension=[ext])
        self.stubs.Set(flavors, 'get_flavor_by_flavor_id',
                       fake_get_flavor_by_flavor_id)
        self.stubs.Set(flavors, 'get_all_flavors_sorted_list',
                       fake_get_all_flavors_sorted_list)
        self.stubs.Set(nova.db, 'flavor_extra_specs_get',
                       fake_flavor_extra_specs_get)

    def _verify_flavor_response(self, flavor, expected):
        for key in expected:
            self.assertEqual(flavor[key], expected[key])

    def test_show(self):
        expected = {
            'flavor': {
                'id': '1',
                'name': 'test',
                'ram': 512,
                'vcpus': 1,
                'disk': 1,
                'OS-FLV-WITH-EXT-SPECS:extra_specs': flavor_extra_specs(),
            }
        }

        url = '/v2/fake/flavors/1'
        req = webob.Request.blank(url)
        req.headers['Content-Type'] = 'application/json'
        res = req.get_response(fakes.wsgi_app(init_only=('flavors',)))
        body = jsonutils.loads(res.body)
        self._verify_flavor_response(body['flavor'], expected['flavor'])

    def test_detail(self):
        expected = [
            {
                'id': 1,
                'name': 'test',
                'ram': 512,
                'vcpus': 1,
                'disk': 1,
                'OS-FLV-WITH-EXT-SPECS:extra_specs': flavor_extra_specs(),
            },
            {
                'id': 2,
                'name': 'test',
                'ram': 512,
                'vcpus': 1,
                'disk': 1,
                'OS-FLV-WITH-EXT-SPECS:extra_specs': flavor_extra_specs(),
            },
        ]

        url = '/v2/fake/flavors/detail'
        req = webob.Request.blank(url)
        req.headers['Content-Type'] = 'application/json'
        res = req.get_response(fakes.wsgi_app(init_only=('flavors',)))
        body = jsonutils.loads(res.body)
        for i, flavor in enumerate(body['flavors']):
            self._verify_flavor_response(flavor, expected[i])
