#!/usr/bin/env python
# Copyright 2011 OpenStack Foundation
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
This script is used to configure openvswitch flows on XenServer hosts.
"""

import os
import simplejson as json
import socket
import struct
import subprocess
import sys

# This is written to Python 2.4, since that is what is available on XenServer
OVS_OFCTL = '/usr/bin/ovs-ofctl'
OVS_VSCTL = '/usr/bin/ovs-vsctl'
XE = '/opt/xensource/bin/xe'
XENSTORE_READ = '/usr/bin/xenstore-read'
XENSTORE_LIST = '/usr/bin/xenstore-list'

PRIORITIES = {'drop': 50,
              'broadcast': 75,
              'base': 100,
              'port_security': 110,
              'security_group': 120,
              'rack_connect': 130,
              'default': 150,
             }

DATA_MARKER = 'cookie'

# NOTE(jkoelker) this splits the DATA_MARKER into one 16bit integer for the
#                DOM_ID and one 4bit integer for the VIF_ID.
VIF_ID_MASK = 983040
DOM_ID_MASK = 65535


# NOTE(jkoelker) Ported from 2.7's subprocess, modified for our needs
def check_output(*popenargs, **kwargs):
    kwargs['close_fds'] = kwargs.get('close_fds', True)
    input = kwargs.pop('input', None)

    if input is not None and kwargs.get('stdin') != subprocess.PIPE:
        kwargs['stdin'] = subprocess.PIPE

    process = subprocess.Popen(stdout=subprocess.PIPE, *popenargs, **kwargs)
    output, unused_err = process.communicate(input=input)
    retcode = process.poll()

    return (retcode, output)


def execute(*command, **kwargs):
    """Collect args in tuple for check_output, pass kwargs through."""
    return check_output(command, **kwargs)


def get_return_code(*command, **kwargs):
    return check_output(command, **kwargs)[0]


def get_output(*command, **kwargs):
    return check_output(command, **kwargs)[1].strip()


def get_ipv6_link_local(mac):
    """Get the link local ipv6 address. Based on code from netaddr."""
    mac = mac.lower()
    words = mac.split(':')
    int_val = 0xfe800000000000000000000000000000

    eui64_tokens = words[0:3] + ['ff', 'fe'] + words[3:6]
    int_val += int(''.join(eui64_tokens), 16)
    int_val ^= 0x00000000000000000200000000000000

    max_word = 2 ** 32 - 1

    _words = []
    for _ in range(4):
        word = int_val & max_word
        _words.append(int(word))
        int_val >>= 32

    packed_int = struct.pack('>4I', *tuple(reversed(_words)))
    return socket.inet_ntop(socket.AF_INET6, packed_int)


def get_snet_gws(ip, routes):
    def str_to_int(addr):
        return struct.unpack('>I', socket.inet_aton(addr))[0]

    ret_set = set()

    ip_int = str_to_int(ip['ip'])
    netmask_int = str_to_int(ip['netmask'])
    network_int = ip_int & netmask_int

    if routes is not None:
        for route in routes:
            gw_int = str_to_int(route['gateway'])
            gw_network_int = gw_int & netmask_int
            if gw_network_int == network_int:
                ret_set.add(route['gateway'])

    if ret_set:
        return tuple(ret_set)

    # NOTE(jkoelker) Fallback to using network address + 1
    gw_int = network_int + 1
    return ('%d.%d.%d.%d' % (gw_int >> 24, (gw_int >> 16) & 0xff,
                            (gw_int >> 8) & 0xff, gw_int & 0xff),)


def get_marker_fragment(dom_id, vif_id):
    dom_id = int(dom_id)
    vif_id = int(vif_id) << 16
    return {DATA_MARKER: dom_id + vif_id}


class OvsFragment(object):
    SEPARATOR = '='

    def __init__(self, key, value=None):
        if isinstance(key, dict):
            if len(key) > 1:
                raise ValueError('Fragment Dictionaries only support one key. '
                                 'Got: %s' % key)

            key, value = key.popitem()

        self.key = key
        self.value = value

    def __str__(self):
        if self.value is None:
            return str(self.key)
        return str(self.key) + self.SEPARATOR + str(self.value)


class OvsActionFragment(OvsFragment):
    SEPARATOR = ':'


class OvsFlow(list):
    def add(self, *fragments):
        for fragment in fragments:
            self.add_fragment(fragment)

    def add_fragment(self, fragment, style=OvsFragment):
        """Checking version of self.append(OvsFragment('key', 'value'))."""

        if isinstance(fragment, dict):
            fragment = OvsFragment(fragment)

        if isinstance(fragment, OvsFragment):
            return self.append(fragment)

        if isinstance(style, basestring):
            if style.lower() == 'action':
                style = OvsActionFragment
            else:
                style = OvsFragment

        key = fragment
        value = None

        # NOTE(jkoelker) Parsing is brittle please try to be explicit ;)
        if '=' in fragment:
            key, value = fragment.split('=', 1)
        elif ':' in fragment:
            key, value = fragment.split(':', 1)

        return self.add_fragment(style(key, value), style=style)

    def __str__(self):
        return ','.join([str(fragment) for fragment in self])


class OvsFlowGroup(list):
    def __init__(self, *args, **kwargs):
        self.forced_fragments = tuple(kwargs.pop('forced_fragments', []))
        self.priority = kwargs.pop('priority', PRIORITIES['default'])
        self.dom_id = kwargs.pop('dom_id', None)
        self.vif_id = kwargs.pop('vif_id', 0)

        list.__init__(self, *args, **kwargs)

    def add(self, *fragments):
        flow = OvsFlow()
        flow.add_fragment({'priority': self.priority})

        if self.dom_id is not None:
            flow.add_fragment(get_marker_fragment(self.dom_id, self.vif_id))

        flow.add(*(self.forced_fragments + fragments))
        self.append(flow)

    def __str__(self):
        return '\n'.join([str(flow) for flow in self])


class OvsFlowManager(list):
    def add(self, flow):
        self.append(flow)

    def _add(self, flow, bridge, exe_func=execute):
        return exe_func(OVS_OFCTL, 'add-flow', bridge, str(flow))

    def clear_flows(self, bridge, dom_id, vif_id, exe_func=execute):
        fragment = get_marker_fragment(dom_id, vif_id)
        fragment[DATA_MARKER] = '%s/%s' % (fragment[DATA_MARKER],
                                           DOM_ID_MASK | VIF_ID_MASK)
        marker = OvsFragment(fragment)
        return exe_func(OVS_OFCTL, 'del-flows', bridge, str(marker))

    def flush(self, bridge, exe_func=execute):
        return exe_func(OVS_OFCTL, 'add-flow', bridge, '-', input=str(self))

    def __str__(self):
        return '\n'.join([str(flow) for flow in self])


def get_default_drop():
    group = OvsFlowGroup(priority=PRIORITIES['drop'], dom_id=0)
    group.add({'actions': 'drop'})
    return group


def get_base_flows(bridge):
    # NOTE(jkoelker) Quick hack to get the phys_dev (xenbr1 -> eth1)
    phys_dev = 'eth' + bridge[-1]
    pnic_ofport = get_output(OVS_VSCTL, 'get', 'Interface', phys_dev, 'ofport')
    bridge_addr = get_output('/sbin/ip', '-o', '-f', 'inet', 'addr', 'show',
                             bridge)

    group = OvsFlowGroup(priority=PRIORITIES['base'], dom_id=0)
    group.add({'in_port': pnic_ofport}, {'actions': 'normal'})

    if bridge_addr:
        group.add({'in_port': 'LOCAL'}, {'actions': 'normal'})

    return group


def get_compute_flows(compute_dom_id):
    vifs = get_output(XENSTORE_LIST,
                      '/local/domain/%s/device/vif' % compute_dom_id)
    vifs = [vif.strip() for vif in vifs.split()]

    flows = OvsFlowManager()
    for vif_id in vifs:
        group = OvsFlowGroup(priority=PRIORITIES['base'],
                             dom_id=compute_dom_id, vif_id=vif_id)
        vif = 'vif%s.%s' % (compute_dom_id, vif_id)
        of_port = get_output(OVS_VSCTL, 'get', 'Interface', vif, 'ofport')
        group.add({'in_port': of_port}, {'actions': 'normal'})
        flows.add(group)
    return flows


def get_rackconnect_flows(dom_id, vif_id, snet_gws, phys_port, mac, ipv4_addr,
                          of_port):
    #    allow icmp -> local servicenet gateway for the cloud server VM
    #    allow icmp -> 10.191.208.0/24
    #    allow tcp:443 -> 10.191.208.0/24
    #    allow icmp -> 10.191.209.0/24
    #    allow tcp:443 -> 10.191.209.0/24
    #    allow tcp:1688 -> 10.179.63.253
    #    allow tcp:1688 -> 10.179.63.254
    #    allow icmp -> 10.188.0.0/16
    #    allow tcp -> 10.188.0.0/16
    #    allow udp -> 10.188.0.0/16

    group = OvsFlowGroup(priority=PRIORITIES['rack_connect'],
                         dom_id=dom_id, vif_id=vif_id)

    #          Proto   Port   Network
    allows = (('icmp', None, '10.191.208.0/24'),
              ('tcp', 443, '10.191.208.0/24'),
              ('icmp', None, '10.191.209.0/24'),
              ('tcp', 443, '10.191.209.0/24'),
              ('tcp', 1688, '10.179.63.253'),
              ('tcp', 1688, '10.179.63.254'),
              ('icmp', None, '10.188.0.0/16'),
              ('tcp', None, '10.188.0.0/16'),
              ('udp', None, '10.188.0.0/16'))

    snet_gw_allows = tuple(('icmp', None, snet_gw) for snet_gw in snet_gws)
    for allow in allows + snet_gw_allows:
        # Pass IP traffic from the external environment to the VM
        fragments = [{allow[0]: None},  # PROTO
                     {'in_port': phys_port},
                     {'dl_dst': mac},
                     {'nw_dst': ipv4_addr},
                     {'nw_src': allow[2]},
                     {'actions': OvsActionFragment('output', of_port)}]

        if allow[1] is not None:
            fragments.append({'tp_src': allow[1]})

        group.add(*fragments)

        # Pass IP traffic from VM to the external environment
        fragments = [{allow[0]: None},  # PROTO
                     {'in_port': of_port},
                     {'nw_src': ipv4_addr},
                     {'nw_dst': allow[2]},
                     {'actions': OvsActionFragment('output', phys_port)}]

        if allow[1] is not None:
            fragments.append({'tp_dst': allow[1]})

        group.add(*fragments)

    # Pass ARP traffic originating from external sources the VM with
    # the matching IP address
    group.add({'arp': None},
              {'in_port': phys_port},
              {'nw_dst': ipv4_addr},
              {'actions': OvsActionFragment('output', of_port)})

    return group


def get_common_ipv4(dom_id, vif_id, phys_port, mac, ipv4_addr, of_port):
    group = OvsFlowGroup(dom_id=dom_id, vif_id=vif_id)

    # When ARP traffic arrives from a vif, push it to virtual port
    # 9999 for further processing
    for nw_src in (ipv4_addr, '0.0.0.0'):
        group.add({'arp': None},
                  {'in_port': of_port},
                  {'dl_src': mac},
                  {'nw_src': nw_src},
                  {'arp_sha': mac},
                  {'actions': OvsActionFragment('resubmit', 9999)})

    # Pass ARP replies coming from the external environment to the
    # target VM
    group.add({'arp': None},
              {'in_port': phys_port},
              {'dl_dst': mac},
              {'actions': OvsActionFragment('output', of_port)})

    # Send any local traffic to the physical NIC's OVS port for
    # physical network learning
    group.add({'in_port': 9999},
              {'actions': OvsActionFragment('output', phys_port)})

    return group


def get_ipv4_flows(dom_id, vif_id, phys_port, mac, ipv4_addr, of_port):
    group = OvsFlowGroup(dom_id=dom_id, vif_id=vif_id)

    # When IP traffic arrives from a vif, push it to virtual port 9999
    # for further processing
    group.add({'ip': None},
              {'in_port': of_port},
              {'dl_src': mac},
              {'nw_src': ipv4_addr},
              {'actions': OvsActionFragment('resubmit', 9999)})

    # Pass ARP requests coming from any VMs on the local HV (port
    # 9999) or coming from external sources (PHYS_PORT) to the VM and
    # physical NIC.  We output this to the physical NIC as well, since
    # with instances of shared ip groups, the active host for the
    # destination IP might be elsewhere...
    group.add({'arp': None},
              {'in_port': 9999},
              {'nw_dst': ipv4_addr},
              {'actions': OvsFlow([OvsActionFragment('output', of_port),
                                   OvsActionFragment('output', phys_port)])})

    # Pass ARP traffic originating from external sources the VM with
    # the matching IP address
    group.add({'arp': None},
              {'in_port': phys_port},
              {'nw_dst': ipv4_addr},
              {'actions': OvsActionFragment('output', of_port)})

    # Pass ARP traffic from one VM (src mac already validated) to
    # another VM on the same HV
    group.add({'arp': None},
              {'in_port': 9999},
              {'dl_dst': mac},
              {'actions': OvsActionFragment('output', of_port)})

    # ALL IP traffic: Pass IP data coming from any VMs on the local HV
    # (port 9999) or coming from external sources (PHYS_PORT) to the
    # VM and physical NIC.  We output this to the physical NIC as
    # well, since with instances of shared ip groups, the active host
    # for the destination IP might be elsewhere...
    group.add({'arp': None},
              {'in_port': 9999},
              {'dl_dst': mac},
              {'nw_dst': ipv4_addr},
              {'actions': OvsFlow([OvsActionFragment('output', of_port),
                                   OvsActionFragment('output', phys_port)])})

    # Pass IP traffic from the external environment to the VM
    group.add({'ip': None},
              {'in_port': phys_port},
              {'dl_dst': mac},
              {'nw_dst': ipv4_addr},
              {'actions': OvsActionFragment('output', of_port)})

    return group


def get_ipv4_broadcast_flows(dom_id, vif_id, of_port):
    group = OvsFlowGroup(priority=PRIORITIES['broadcast'],
                         dom_id=dom_id, vif_id=vif_id)

    # Drop IP bcast/mcast
    group.add({'in_port': of_port},
              {'dl_dst': 'ff:ff:ff:ff:ff:ff'},
              {'actions': 'drop'})

    for nw_dst in ('244.0.0.0/4', '240.0.0.0/4'):
        group.add({'in_port': of_port},
                  {'nw_dst': nw_dst},
                  {'actions': 'drop'})

    return group


def get_ovs_ipv6_flows(dom_id, vif_id, phys_port, mac, ipv6_addr, link_local,
                       of_port):
    group = OvsFlowGroup(dom_id=dom_id, vif_id=vif_id)

    # allow valid IPv6 ND outbound (are both global and local IPs needed?)
    # Neighbor Discovery
    for icmp_type in (135, 136):
        for ip in (link_local, ipv6_addr):
            group.add({'icmp6': None},
                      {'icmp_type': icmp_type},
                      {'in_port': of_port},
                      {'dl_src': mac},
                      {'nd_sll': mac},
                      {'ipv6_src': ip},
                      {'actions': 'normal'})

            group.add({'icmp6': None},
                      {'icmp_type': icmp_type},
                      {'in_port': of_port},
                      {'dl_src': mac},
                      {'ipv6_src': ip},
                      {'actions': 'normal'})

    # allow valid IPv6 outbound, by type
    for proto in ('icmp6', 'tcp6', 'udp6'):
        for ip in (link_local, ipv6_addr):
            group.add({proto: None},
                      {'in_port': of_port},
                      {'dl_src': mac},
                      {'ipv6_src': ip},
                      {'actions': 'normal'})

    return group


def get_ipv6_broadcast_flows(dom_id, vif_id, of_port):
    group = OvsFlowGroup(priority=PRIORITIES['broadcast'],
                         dom_id=dom_id, vif_id=vif_id)

    # Do not allow sending specifc ICMPv6 types
    # Router Advertisement: 134
    # Neighbor Discovery: 135, 136
    # Redirect Gateway: 137
    # Mobile Prefix: 146, 147
    # Multicast Router: 151, 152, 153
    for icmp_type in (134, 135, 136, 137, 146, 147, 151, 152, 153):
        group.add({'icmp6': None},
                  {'icmp_type': icmp_type},
                  {'in_port': of_port},
                  {'actions': 'drop'})

    return group


def main(command, vif_raw, net_type):
    vif_name, dom_id, vif_id = vif_raw.split('-')
    vif = '%s%s.%s' % (vif_name, dom_id, vif_id)

    nvp_network_uuid = get_output(XE, 'network-list', 'name-label=NVP',
                                  '--minimal')
    nvp_br = get_output(XE, 'network-param-get', 'param-name=bridge',
                       'uuid=%s' % nvp_network_uuid)

    # this gets the bridge the vif is plugged into
    bridge = get_output(OVS_VSCTL, 'iface-to-br', vif)

    # NOTE(jkoelker) If we are plugged into the NVP integration bridge
    if bridge == nvp_br:
        return

    # get parent of bridge
    # which can be itself or in the case of xapi1 it will be a real
    # bridge like xenbr1 where we want to put the flows
    bridge = get_output(OVS_VSCTL, 'br-to-parent', bridge)

    compute_uuid = get_output(XE, 'vm-list', 'name-label=compute',
                              '--minimal')
    compute_dom_id = get_output(XE, 'vm-param-get', 'param-name=dom-id',
                                'uuid=%s' % compute_uuid)

    ovs = OvsFlowManager()

    # NOTE(jkoelker) Always apply base flows
    ovs.add(get_default_drop())
    ovs.add(get_base_flows(bridge))
    ovs.add(get_compute_flows(compute_dom_id))

    # NOTE(jkoelker) If this is a compute vif flush and return
    if compute_dom_id == dom_id:
        return ovs.flush(bridge, exe_func=get_return_code)

    # get mac address for vif
    vif_mac = get_output(XENSTORE_READ,
                         '/local/domain/%s/device/vif/%s/mac' % (dom_id,
                                                                 vif_id))
    vif_mac = ''.join(vif_mac.split(':')).upper()

    # pull xenstore data for this vif
    xenstore_data = get_output(XENSTORE_READ,
                               '/local/domain/%s/vm-data/networking/%s' %
                               (dom_id, vif_mac))
    xenstore_data = json.loads(xenstore_data)

    # only public and snet vifs make it here so we can key off public for now
    if xenstore_data['label'] == 'public':
        phys_dev = 'eth0'
    else:
        phys_dev = 'eth1'

    of_port = get_output(OVS_VSCTL, 'get', 'Interface', vif, 'ofport')
    phys_port = get_output(OVS_VSCTL, 'get', 'Interface', phys_dev, 'ofport')
    mac = xenstore_data['mac'].lower()

    if command == 'offline':
        # Make sure to flush out the base flows
        ovs.flush(bridge, exe_func=execute)
        return ovs.clear_flows(bridge, dom_id, vif_id,
                               exe_func=get_return_code)

    if ('rackconnect' in xenstore_data and
         net_type in ('ipv4', 'all') and
         'ips' in xenstore_data):

        for ip in xenstore_data['ips']:
            snet_gws = get_snet_gws(ip, xenstore_data.get('routes'))
            ovs.add(get_rackconnect_flows(dom_id, vif_id, snet_gws, phys_port,
                                          mac, ip['ip'], of_port))
            ovs.add(get_common_ipv4(dom_id, vif_id, phys_port, mac, ip['ip'],
                                    of_port))

    else:
        if net_type in ('ipv4', 'all') and 'ips' in xenstore_data:
            for ip in xenstore_data['ips']:
                ovs.add(get_common_ipv4(dom_id, vif_id, phys_port, mac,
                                        ip['ip'], of_port))
                ovs.add(get_ipv4_flows(dom_id, vif_id, phys_port, mac,
                                       ip['ip'], of_port))
                ovs.add(get_ipv4_broadcast_flows(dom_id, vif_id, of_port))

        if net_type in ('ipv6', 'all') and 'ip6s' in xenstore_data:
            for ip in xenstore_data['ip6s']:
                link_local = get_ipv6_link_local(mac)

                ovs.add(get_ovs_ipv6_flows(dom_id, vif_id, phys_port, mac,
                                           ip['ip'], link_local, of_port))
                ovs.add(get_ipv6_broadcast_flows(dom_id, vif_id, of_port))

    if command in ('online', 'reset'):
        if command == 'reset':
            ovs.clear_flows(bridge, dom_id, vif_id, exe_func=get_return_code)
        return ovs.flush(bridge, exe_func=get_return_code)

    print(str(ovs))
    return 0


if __name__ == '__main__':
    if len(sys.argv) != 4:
        print(' '.join(['usage: %s' % os.path.basename(sys.argv[0]),
                        '[online|offline|reset]',
                        'vif-domid-idx',
                        '[ipv4|ipv6|all]']))
        sys.exit(1)
    else:
        command, vif_raw, net_type = sys.argv[1:4]
        sys.exit(main(command, vif_raw, net_type))
