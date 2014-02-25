# Copyright 2014 Rackspace Hosting, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import mock

from nova import test
from nova.virt.disk.mount import api as mount


class TestVirtDiskMountApi(test.NoDBTestCase):
    def setUp(self):
        super(TestVirtDiskMountApi, self).setUp()

    @mock.patch('nova.virt.disk.mount.loop.LoopMount')
    def test_instance_for_format_raw(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = -1
        imgfmt = 'raw'
        mock_mounter.return_value = 'loop_mount'
        inst = mount.Mount.instance_for_format(image, mount_dir, partition,
                                               imgfmt)
        self.assertEqual(inst, 'loop_mount')

    @mock.patch('nova.virt.disk.mount.nbd.NbdMount')
    def test_instance_for_format_qcow2(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = -1
        imgfmt = 'qcow2'
        mock_mounter.return_value = 'nbd_mount'
        inst = mount.Mount.instance_for_format(image, mount_dir, partition,
                                               imgfmt)
        self.assertEqual(inst, 'nbd_mount')

    @mock.patch('nova.virt.disk.mount.noop.NoopMount')
    def test_instance_for_format_noop(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = -1
        imgfmt = 'raw'
        mock_mounter.return_value = 'noop_mount'
        inst = mount.Mount.instance_for_format(image, mount_dir, partition,
                                               imgfmt, noop_mount=True)
        self.assertEqual(inst, 'noop_mount')

    @mock.patch('nova.virt.disk.mount.loop.LoopMount')
    def test_instance_for_device_loop(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = -1
        device = '/dev/loop0'
        mock_mounter.return_value = 'loop_mount'
        inst = mount.Mount.instance_for_device(image, mount_dir, partition,
                                               device)
        self.assertEqual(inst, 'loop_mount')

    @mock.patch('nova.virt.disk.mount.loop.LoopMount')
    def test_instance_for_device_loop_partition(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = 1
        device = '/dev/mapper/loop0p1'
        mock_mounter.return_value = 'loop_mount'
        inst = mount.Mount.instance_for_device(image, mount_dir, partition,
                                               device)
        self.assertEqual(inst, 'loop_mount')

    @mock.patch('nova.virt.disk.mount.nbd.NbdMount')
    def test_instance_for_device_nbd(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = -1
        device = '/dev/nbd0'
        mock_mounter.return_value = 'nbd_mount'
        inst = mount.Mount.instance_for_device(image, mount_dir, partition,
                                               device)
        self.assertEqual(inst, 'nbd_mount')

    @mock.patch('nova.virt.disk.mount.nbd.NbdMount')
    def test_instance_for_device_nbd_partition(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = 1
        device = '/dev/mapper/nbd0p1'
        mock_mounter.return_value = 'nbd_mount'
        inst = mount.Mount.instance_for_device(image, mount_dir, partition,
                                               device)
        self.assertEqual(inst, 'nbd_mount')

    @mock.patch('nova.virt.disk.mount.noop.NoopMount')
    def test_instance_for_device_noop(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = -1
        device = '/dev/mapper/instances--instance-0000001_disk'
        mock_mounter.return_value = 'noop_mount'
        inst = mount.Mount.instance_for_device(image, mount_dir, partition,
                                               device)
        self.assertEqual(inst, 'noop_mount')

    @mock.patch('nova.virt.disk.mount.noop.NoopMount')
    def test_instance_for_device_noop_partiton(self, mock_mounter):
        image = mock.MagicMock()
        mount_dir = '/mount/dir'
        partition = 1
        device = '/dev/mapper/instances--instance-0000001_diskp1'
        mock_mounter.return_value = 'noop_mount'
        inst = mount.Mount.instance_for_device(image, mount_dir, partition,
                                               device)
        self.assertEqual(inst, 'noop_mount')
