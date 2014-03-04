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

from nova.compute import claims
from nova.compute import utils as compute_utils
from nova import context
from nova.objects import block_device
from nova.tests.compute.test_compute import BaseTestCase
from nova.tests.compute.test_compute import NODENAME
from nova.tests.virt.xenapi import stubs
from nova.virt import fake
from nova.virt.xenapi import driver


class TestComputeMigrateFromFG(BaseTestCase):
    def setUp(self):
        super(TestComputeMigrateFromFG, self).setUp()
        self.resource_tracker = self.compute._get_resource_tracker(NODENAME)
        self.context = context.get_admin_context()
        self.instance = self._create_fake_instance()
        self.image = {'name': 'CentOS'}
        self.bdms = ['bdm']

        def _instance_claim(context, instance):
            return claims.NopClaim()

        def _update_usage(context, instance):
            pass

        def _default_block_device_names(context, instance, image, bdms):
            pass

        self.mox.StubOutWithMock(block_device.BlockDeviceMappingList,
                                 'get_by_instance_uuid')
        block_device.BlockDeviceMappingList. \
            get_by_instance_uuid(self.context,
                                 self.instance['uuid']).AndReturn(self.bdms)
        self.stubs.Set(self.compute, '_default_block_device_names',
                       _default_block_device_names)
        self.stubs.Set(self.resource_tracker, 'instance_claim',
                       _instance_claim)
        self.stubs.Set(self.resource_tracker, 'update_usage', _update_usage)

    def test_allocate_resources_for_fg_instance_should_claim_resources(self):
        self.mox.StubOutWithMock(self.resource_tracker, 'instance_claim')
        self.resource_tracker.instance_claim(self.context, self.instance)\
            .AndReturn(claims.NopClaim())
        self.mox.ReplayAll()

        self.compute.allocate_resources_for_fg_instance(self.context,
                                                        self.instance,
                                                        self.image,
                                                        NODENAME)

    def test_allocate_resources_for_fg_instance_should_update_usages(self):
        self.mox.StubOutWithMock(self.resource_tracker, 'update_usage')
        self.resource_tracker.update_usage(self.context, self.instance)
        self.mox.ReplayAll()

        self.compute.allocate_resources_for_fg_instance(self.context,
                                                        self.instance,
                                                        self.image,
                                                        NODENAME)

    def test_allocate_resource_for_fg_instance_should_fetch_hyper_ip(self):
        hypervisor_ip = "10.2.3.10"
        self.mox.StubOutWithMock(self.compute.driver, 'hypervisor_ip')
        self.compute.driver.hypervisor_ip().AndReturn(hypervisor_ip)
        self.mox.ReplayAll()

        ip = self.compute.allocate_resources_for_fg_instance(self.context,
                                                             self.instance,
                                                             self.image,
                                                             NODENAME)

        self.assertEqual(hypervisor_ip, ip)

    def test_allocate_resource_for_fg_instance_notify_create_start(self):
        info = {
            'image_name': 'CentOS',
            'message': ''}
        notifier = self.compute.notifier
        self.mox.StubOutWithMock(compute_utils, 'notify_about_instance_usage')
        compute_utils.notify_about_instance_usage(notifier, self.context,
                                                  self.instance,
                                                  'create.start',
                                                  network_info=None,
                                                  system_metadata=None,
                                                  extra_usage_info=info,
                                                  fault=None)
        self.mox.ReplayAll()

        self.compute.allocate_resources_for_fg_instance(self.context,
                                                        self.instance,
                                                        self.image,
                                                        NODENAME)

    def test_allocate_resource_for_fg_instance_sets_default_device_name(self):
        self.mox.StubOutWithMock(self.compute, '_default_block_device_names')
        self.compute._default_block_device_names(self.context, self.instance,
                                                 self.image, self.bdms)
        self.mox.ReplayAll()

        self.compute.allocate_resources_for_fg_instance(self.context,
                                                        self.instance,
                                                        self.image,
                                                        NODENAME)


class XenDriverTest(stubs.XenAPITestBaseNoDB):
    def setUp(self):
        super(XenDriverTest, self).setUp()
        self.flags(connection_url='https://11.3.3.32',
                   connection_password='test_pass',
                   group='xenserver')
        stubs.stubout_session(self.stubs, stubs.FakeSessionForVMTests)
        self.conn = driver.XenAPIDriver(fake.FakeVirtAPI(), False)

    def test_hypervisor_ip(self):
        ip = self.conn.hypervisor_ip()

        self.assertEqual("11.3.3.32", ip)
