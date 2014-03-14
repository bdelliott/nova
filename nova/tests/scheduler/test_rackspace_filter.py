# Copyright 2012 Rackspace Hosting
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
"""
Tests For Scheduler Host Filters.
"""

import mock

from nova import context
from nova.scheduler import filters
from nova.scheduler import host_manager
from nova import test
from nova.tests.scheduler import fakes
from oslo.config import cfg


CONF = cfg.CONF
CONF.import_opt('rackspace_max_instances_per_host',
                'nova.scheduler.filters.rackspace_filter')
CONF.import_opt('rackspace_max_ios_per_host',
                'nova.scheduler.filters.rackspace_filter')
CONF.import_opt('scheduler_spare_host_percentage',
                'nova.scheduler.filters.rackspace_filter')


class RackspaceHostFiltersTestCase(test.TestCase):
    """Test case for host filters."""

    def setUp(self):
        super(RackspaceHostFiltersTestCase, self).setUp()
        self.flags(rackspace_max_ios_per_host=10,
                rackspace_max_instances_per_host=50,
                scheduler_spare_host_percentage=10,
                rackspace_ram_check_enabled=True)
        self.context = context.RequestContext('fake', 'fake')
        filter_handler = filters.HostFilterHandler()
        filt_name = 'nova.scheduler.filters.rackspace_filter.RackspaceFilter'
        classes = filter_handler.get_matching_classes([filt_name])
        self.assertEqual(len(classes), 1)
        self.filt_cls = classes[0]()
        self.filter_properties = dict(instance_type=dict(id=1,
                memory_mb=1024))

    def test_rackspace_filter_num_iops_passes(self):
        host = fakes.FakeHostState('host1', 'node1',
                {'num_io_ops': 6})
        self.assertTrue(self.filt_cls._io_ops_filter(host))

    def test_rackspace_filter_num_iops_fails(self):
        host = fakes.FakeHostState('host1', 'node1',
                {'num_io_ops': 11})
        self.assertFalse(self.filt_cls._io_ops_filter(host))

    def test_rackspace_filter_num_instances_passes(self):
        host = fakes.FakeHostState('host1', 'node1',
                {'num_instances': 49})
        self.assertTrue(self.filt_cls._num_instances_filter(host))

    def test_rackspace_filter_num_instances_fails(self):
        host = fakes.FakeHostState('host1', 'node1',
                {'num_instances': 51})
        self.assertFalse(self.filt_cls._num_instances_filter(host))

    def test_rackspace_filter_ram_check_fails(self):
        """Test that we need 1G of reserve for < 30G instance."""
        filt_props = {'instance_type': {'memory_mb': 1024}}
        host = fakes.FakeHostState('host1', 'node1',
                {'free_ram_mb': 1024})
        self.assertFalse(self.filt_cls._ram_check_filter(host, filt_props))

    def test_rackspace_filter_ram_check_passes_30g(self):
        filt_props = {'instance_type': {'memory_mb': 30 * 1024}}
        free_ram = 30 * 1024 + 245
        host = fakes.FakeHostState('host1', 'node1',
                {'free_ram_mb': free_ram})
        self.assertTrue(self.filt_cls._ram_check_filter(host, filt_props))

    def test_rackspace_filter_ram_check_passes(self):
        filt_props = {'instance_type': {'memory_mb': 1024}}
        free_ram = 1024 + 1024 + 13
        host = fakes.FakeHostState('host1', 'node1',
                {'free_ram_mb': free_ram})
        self.assertTrue(self.filt_cls._ram_check_filter(host, filt_props))

    def test_rackspace_filter_flags_no_reserve(self):
        # flavor not less than reserve threshold:
        self.flags(rackspace_ram_check_threshold=4096,
                   rackspace_ram_check_reserve=2)

        filt_props = {'instance_type': {'memory_mb': 4096}}
        host = fakes.FakeHostState('host1', 'node1', {'free_ram_mb': 4096})

        with mock.patch.object(self.filt_cls,
                "_estimate_instance_overhead", return_value=0):
            self.assertTrue(self.filt_cls._ram_check_filter(host, filt_props))

    def test_rackspace_filter_flags_reserve_fail(self):
        # flavor + reserve > free ram:
        self.flags(rackspace_ram_check_threshold=4096,
                   rackspace_ram_check_reserve=2)

        filt_props = {'instance_type': {'memory_mb': 4095}}
        host = fakes.FakeHostState('host1', 'node1', {'free_ram_mb': 4096})
        with mock.patch.object(self.filt_cls,
                "_estimate_instance_overhead", return_value=0):
            self.assertFalse(self.filt_cls._ram_check_filter(host, filt_props))

    def test_rackspace_filter_flags_reserve_pass(self):
        # flavor + reserve amount = free_ram:
        self.flags(rackspace_ram_check_threshold=4096,
                   rackspace_ram_check_reserve=1)

        filt_props = {'instance_type': {'memory_mb': 4095}}
        host = fakes.FakeHostState('host1', 'node1',
                {'free_ram_mb': 4096})
        with mock.patch.object(self.filt_cls,
                "_estimate_instance_overhead", return_value=0):
            self.assertTrue(self.filt_cls._ram_check_filter(host, filt_props))

    def _create_hosts(self, num_instances_mod, num_hosts=50):
        hosts = []
        num_empty = 0
        filter_properties = {'total_hosts': num_hosts}
        for i in xrange(num_hosts):
            host = host_manager.HostState('host-%03i' % (i + 1), 'node1')
            host.num_instances = ((i % num_instances_mod)
                    if num_instances_mod else 0)
            if not host.num_instances:
                num_empty += 1
            hosts.append(host)
        return hosts, filter_properties, num_empty

    def _spare_filter(self, hosts, filt_props):
        def my_host_passes(*args, **kwargs):
            return True

        self.stubs.Set(self.filt_cls, '_host_passes', my_host_passes)

        # filter_all returns a generator, so we need to convert to a
        # list to do proper checking.  Also, pass in 'hosts' as an
        # iterator so we're testing with that functionality.
        return list(self.filt_cls.filter_all(iter(hosts), filt_props))

    def test_spares_disabled(self):
        self.flags(scheduler_spare_host_percentage=0)
        hosts, filt_props, _num_empty = self._create_hosts(10)
        filtered_hosts = self._spare_filter(hosts, filt_props)
        self.assertEqual(len(hosts), len(filtered_hosts))

    def test_all_hosts_empty(self):
        hosts, filt_props, _num_empty = self._create_hosts(0)
        filtered_hosts = self._spare_filter(hosts, filt_props)
        # filtering 10% of 50..
        self.assertEqual(45, len(filtered_hosts))

    def test_no_empty_hosts(self):
        hosts, filt_props, _num_empty = self._create_hosts(100)
        # Fudge the first host to contain instances
        hosts[0].num_instances = 1
        filtered_hosts = self._spare_filter(hosts, filt_props)
        self.assertEqual(len(hosts), len(filtered_hosts))

    def test_more_empty_hosts_than_spares_percentage(self):
        hosts, filt_props, num_empty = self._create_hosts(2)
        filtered_hosts = self._spare_filter(hosts, filt_props)
        self.assertTrue(num_empty > 5)
        # Reserve 10% of 50 hosts... or 5 hosts.
        self.assertEqual(len(filtered_hosts), len(hosts) - 5)
        empties = [x for x in filtered_hosts if not x.num_instances]
        # Mod of 2 means we had 25 full and 25 empty before filtering
        self.assertEqual(len(empties), 20)

    def test_less_empty_hosts_than_spares_percentage(self):
        hosts, filt_props, num_empty = self._create_hosts(25)
        filtered_hosts = self._spare_filter(hosts, filt_props)
        self.assertEqual(len(filtered_hosts), len(hosts) - num_empty)
        empties = [x for x in filtered_hosts if not x.num_instances]
        self.assertEqual(len(empties), 0)

    def test_estimate_instance_overhead_one_vcpu(self):
        actual = self.filt_cls._estimate_instance_overhead(1024, 1)
        self.assertEqual(13, actual)

    def test_estimate_instance_overhead_one_vcpu_30g(self):
        actual = self.filt_cls._estimate_instance_overhead(30 * 1024, 1)
        self.assertEqual(245, actual)

    def test_estimate_instance_overhead_two_vcpus(self):
        actual = self.filt_cls._estimate_instance_overhead(1024, 2)
        self.assertEqual(14, actual)

    def test_estimate_used_memory_mb_no_vpus(self):
        instance_type = {'memory_mb': 1024}
        actual = self.filt_cls._estimate_used_memory_mb(instance_type)
        self.assertEqual(1037, actual)

    def test_estimate_used_memory_mb_with_vpus(self):
        instance_type = {'memory_mb': 1024, 'vcpus': 2}
        actual = self.filt_cls._estimate_used_memory_mb(instance_type)
        self.assertEqual(1038, actual)
