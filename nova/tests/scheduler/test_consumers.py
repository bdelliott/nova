# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
# All Rights Reserved.
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
"""Tests for scheduler host resource consumers"""


from nova import consumers
from nova import loadables
from nova import test
from nova.scheduler.consumers import network
from nova.tests.scheduler import fakes


def fake_node_dict(values={}):
    node = {
        'id': 1,
        'local_gb': 1024,
        'memory_mb': 1024,
        'vcpu': 1,
        'disk_available_least': 512,
        'free_ram_mb': 512,
        'vcpu_used': 1,
        'free_disk_mb': 512,
        'local_gb_used': 0,
        'updated_at': None,
        'service': {'host': 'host1', 'disabled': False},
        'hypervisor_hostname': 'node1',
        'host_ip': '127.0.0.1',
        'hypervisor_version': 0,
        'extra_resources': {'network_mbps': 1024, 'network_used_mbps': 512}
    }
    if values:
        for key in values.keys():
            node[key] = values[key]
    return node


def fake_instance_dict(values={}):
    instance = {
        'memory_mb': 512
    }
    if values:
        for key in values.keys():
            instance[key] = values[key]
    return instance


def fake_instance_type_dict(values={}):
    type = {
        'extra_specs': {'network_mbps': 512}
    }
    if values:
        for key in values.keys():
            type[key] = values[key]
    return type


class ConsumersTestCase(test.NoDBTestCase):

    def test_extra_resources(self):

        host_state = fakes.FakeHostState('host1', 'node1', fake_node_dict())
        instance = fake_instance_dict()
        instance_type = fake_instance_type_dict()

        network.NetworkBandwidthConsumer().consume_from_instance(
            host_state, instance, instance_type)

        self.assertTrue(host_state.extra_resources['network_used_mbps'] == 1024)


    def test_extra_resources_missing(self):
        pass

    def test_no_consumer_classes(self):
        pass

    def test_standard_resources(self):
        pass