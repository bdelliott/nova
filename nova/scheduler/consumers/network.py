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

from nova.scheduler import consumers


class NetworkBandwidthConsumer(consumers.BaseResourceConsumer):
    """Consume network bandwidth from the compute host resources.

    Network bandwidth is specified in extra_specs as network_mbps
    and in host state extra_resources as network_mbps and network_used_mbps
    """

    def consume_from_instance(self, host_state, instance, instance_type):
        """Increase network_used_mbps in extra_resources"""

        # We only apply this if extra_specs specifies a bandwidth
        # requirement
        extra_specs = instance_type.get('extra_specs', {})
        if not extra_specs.get('network_mbps'):
            return

        network_mbps = extra_specs['network_mbps']

        # This suggests it is optional when the user has specified
        # the extra_specs requirement. If we are here, the filter
        # has passed.
        extra_resources = host_state.extra_resources
        if extra_resources.get('network_used_mbps'):
            extra_resources['network_used_mbps'] += network_mbps