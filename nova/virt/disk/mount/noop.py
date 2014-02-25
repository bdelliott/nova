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
"""No operation mounter for images already exposed as block devices"""

from nova.virt.disk.mount import api


class NoopMount(api.Mount):
    """This allows image backends that already expose their images as block
        devices to be mounted directly to the instances rootfs.
    """
    mode = 'noop'

    def get_dev(self):
        self.device = self.image
        self.mounted = True
        return True

    def unget_dev(self):
        if not self.mounted:
            return

        self.mounted = False
        self.device = None
