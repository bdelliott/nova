# Copyright (c) 2011 Citrix Systems, Inc.
# Copyright 2011 OpenStack Foundation
# Copyright (C) 2011 Nicira, Inc
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

"""VIF drivers for XenAPI."""

from oslo.config import cfg

from nova.virt.xenapi import network_utils
from nova.virt.xenapi import vif as xenvif
from nova.virt.xenapi import vm_utils


opts = [
    cfg.BoolOpt('rs_bridge_is_name_label',
                default=False,
                help='Should value in vif bridge be looked up in xen'),
    cfg.StrOpt('ovs_integration_bridge',
               default='xapi1',
               deprecated_name='xenapi_ovs_integration_bridge',
               help='Name of Integration Bridge used by Open vSwitch')
]


CONF = cfg.CONF
CONF.register_opts(opts)


class XenAPIRsBridgeDriver(xenvif.XenVIFDriver):
    """VIF Driver for XenAPI that uses XenAPI to create Networks."""

    def plug(self, instance, vif, vm_ref=None, device=None):
        if not vm_ref:
            vm_ref = vm_utils.lookup(self._session, instance['name'])
        if not device:
            device = 0

        bridge = vif['network'].get('bridge',
                                    CONF.ovs_integration_bridge)

        # NOTE(jkoelker) Sometimes the key will be there but already is None
        if bridge is None:
            bridge = CONF.ovs_integration_bridge

        if CONF.rs_bridge_is_name_label:
            lookup_func = network_utils.find_network_with_name_label

        else:
            lookup_func = network_utils.find_network_with_bridge

        network_ref = lookup_func(self._session, bridge)

        # NOTE(jkoelker) find_network_with_name_label will return None when
        #                the name-label isn't found, but
        #                find_network_with_bridge raises. Fall back to bridge
        #                lookup and let it raise.
        if network_ref is None and CONF.rs_bridge_is_name_label:
            network_ref = network_utils.find_network_with_bridge(self._session,
                                                                 bridge)

        vif_rec = {}
        vif_rec['device'] = str(device)
        vif_rec['network'] = network_ref
        vif_rec['VM'] = vm_ref
        vif_rec['MAC'] = vif['address']
        vif_rec['MTU'] = '1500'

        vif_rec['other_config'] = {}
        vif_rec['qos_algorithm_type'] = ''
        vif_rec['qos_algorithm_params'] = {}

        if vif['network'].get_meta('nvp_managed'):
            vif_rec['other_config']['nicira-iface-id'] = vif['id']
            vif_rec['qos_algorithm_type'] = ''
            vif_rec['qos_algorithm_params'] = {}

        return vif_rec

    def unplug(self, instance, vif):
        pass
