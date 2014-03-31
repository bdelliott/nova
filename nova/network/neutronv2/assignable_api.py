# Copyright 2013 OpenStack Foundation
# All Rights Reserved
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
#

import re

from oslo.config import cfg

import netaddr
from neutronclient.common import exceptions as neutron_client_exc

from nova import exception
from nova.network import base_api
from nova.network import model as network_model
from nova.network import neutronv2
from nova.network.neutronv2 import api
from nova.openstack.common.gettextutils import _
from nova.openstack.common import jsonutils
from nova.openstack.common import log as logging

neutron_opts = [
    cfg.ListOpt('network_order',
                default=['public', 'private', '.*'],
                help='Ordered list of network labels, using regex syntax'),
    ]

CONF = cfg.CONF


try:
    CONF.register_opts(neutron_opts)
except cfg.DuplicateOptError:
    # NOTE(jkoelker) These options are verbatim in the old quantum2 manager
    #                this is here to make sure they are registered for our
    #                use until we remove it totally
    pass


LOG = logging.getLogger(__name__)


update_instance_info_cache = base_api.update_instance_cache_with_nw_info


def _order_nw_info_by_label(nw_info):
    if nw_info is None:
        return nw_info

    def get_vif_label_key(vif):
        for i, pattern in enumerate(CONF.network_order):
            if re.match(pattern, vif['network']['label']):
                return i
        else:
            return len(CONF.network_order)
    nw_info.sort(key=get_vif_label_key)
    return nw_info


class API(api.API):
    """API for interacting with the neutron 2.x API."""

    def _get_available_networks(self, context, project_id,
                                net_ids=None, neutron=None, **kwargs):
        """Return a network list available for the tenant.
        The list contains networks owned by the tenant and public networks.
        If net_ids specified, it searches networks with requested IDs only.
        """
        if not neutron:
            neutron = neutronv2.get_client(context)

        search_opts = {}

        if net_ids is None:
            # NOTE(tr3buchet): no netids passed in, search shared networks
            # Retrieve assignable network list.
            search_opts = {'shared': True}
        elif len(net_ids) == 0:
            # NOTE(tr3buchet): empty list of netids passed in,
            #                  no sense looking up anything, return []
            return []
        else:
            # NOTE(tr3buchet): populated list of netids passed in,
            #                  search for these ids
            # If user has specified to attach instance only to specific
            # networks then only add these to **search_opts. This search will
            # also include 'shared' networks.
            search_opts = {'id': net_ids}
        nets = neutron.list_networks(**search_opts).get('networks', [])

        api._ensure_requested_network_ordering(
            lambda x: x['id'],
            nets,
            net_ids)

        return nets

    def _build_network_info_model(self, context, instance, networks=None,
                                  port_ids=None, **kwargs):
        search_opts = {'tenant_id': instance['project_id'],
                       'device_id': instance['uuid'], }
        client = neutronv2.get_client(context, admin=True)
        data = client.list_ports(**search_opts)
        ports = data.get('ports', [])
        if networks is None:
            # retrieve networks from info_cache to get correct nic order
            network_cache = self.conductor_api.instance_get_by_uuid(
                context, instance['uuid'])['info_cache']['network_info']
            network_cache = jsonutils.loads(network_cache)
            net_ids = [iface['network']['id'] for iface in network_cache]
            networks = self._get_available_networks(context,
                                                    instance['project_id'],
                                                    net_ids=net_ids)
        # ensure ports are in preferred network order, and filter out
        # those not attached to one of the provided list of networks
        else:
            net_ids = [n['id'] for n in networks]
        ports = [port for port in ports if port['network_id'] in net_ids]
        api._ensure_requested_network_ordering(lambda x: x['network_id'],
                                               ports, net_ids)

        nw_info = network_model.NetworkInfo()
        for port in ports:
            network_IPs = self._nw_info_get_ips(client, port)
            subnets = self._nw_info_get_subnets(context, port, network_IPs)

            devname = "tap" + port['id']
            devname = devname[:network_model.NIC_NAME_LEN]

            network, ovs_interfaceid = self._nw_info_build_network(port,
                                                                   networks,
                                                                   subnets)

            vif = network_model.VIF(id=port['id'],
                                    address=port['mac_address'],
                                    network=network,
                                    type=port.get('binding:vif_type'),
                                    ovs_interfaceid=ovs_interfaceid,
                                    devname=devname)
            # NOTE(mpath): rc is True if context.roles contains substring
            # 'rack_connect' or 'rackconnect:v3-', otherwise False. This is
            # needed to cover cases for rackconnect version 2 and 3.
            # NOTE(jkoelker) remove the RCv2 role due to flows not being tested
            #                (and not working) on master-split
            rc = any(k in ' '.join([r for r in context.roles if r])
                     for k in ['rackconnect:v3-'])
            network_model.VIF._set_meta(vif, {"rackconnect": rc})
            nw_info.append(vif)
        return nw_info

    def _nw_info_build_network(self, port, networks, subnets):
        # NOTE(danms): This loop can't fail to find a network since we
        # filtered ports to only the ones matching networks in our parent
        found_net = None
        for net in networks:
            if port['network_id'] == net['id']:
                network_name = net['name']
                found_net = net
                break

        bridge = port.get("bridge")

        network = network_model.Network(
            id=port['network_id'],
            bridge=bridge,
            injected=CONF.flat_injected,
            label=network_name,
            tenant_id=net['tenant_id'],
            nvp_managed=not found_net["shared"]
            )
        network['subnets'] = subnets
        port_profile = port.get('binding:profile')
        if port_profile:
            physical_network = port_profile.get('physical_network')
            if physical_network:
                network['physical_network'] = physical_network

        return network, None

    def _create_port(self, port_client, instance, network_id, port_req_body,
                     fixed_ip=None, security_group_ids=None,
                     available_macs=None, dhcp_opts=None):
        """Attempts to create a port for the instance on the given network.

        :param port_client: The client to use to create the port.
        :param instance: Create the port for the given instance.
        :param network_id: Create the port on the given network.
        :param port_req_body: Pre-populated port request. Should have the
            device_id and any required neutron extension values.
        :param fixed_ip: Optional fixed IP to use from the given network.
        :param security_group_ids: Optional list of security group IDs to
            apply to the port.
        :param available_macs: Optional set of available MAC addresses to use.
        :param dhcp_opts: Optional DHCP options.
        :returns: ID of the created port.
        :raises PortLimitExceeded: If neutron fails with an OverQuota error.
        """
        try:
            if fixed_ip:
                port_req_body['port']['fixed_ips'] = [{'ip_address': fixed_ip}]

            segment_id = CONF.quantum_default_tenant_id
            port_req_body['port']['network_id'] = network_id
            port_req_body['port']['admin_state_up'] = True
            port_req_body['port']['tenant_id'] = instance['project_id']
            port_req_body['port']['segment_id'] = segment_id

            if security_group_ids:
                port_req_body['port']['security_groups'] = security_group_ids
            if available_macs is not None:
                if not available_macs:
                    raise exception.PortNotFree(
                        instance=instance['display_name'])
                mac_address = available_macs.pop()
                port_req_body['port']['mac_address'] = mac_address
            if dhcp_opts is not None:
                port_req_body['port']['extra_dhcp_opts'] = dhcp_opts
            port_id = port_client.create_port(port_req_body)['port']['id']
            LOG.debug('Successfully created port: %s' % port_id,
                      instance=instance)
            return port_id
        except neutron_client_exc.NeutronClientException as e:
            LOG.exception(_('Neutron error creating port on network %s') %
                          network_id, instance=instance)
            # NOTE(mriedem): OverQuota in neutron is a 409
            if e.status_code == 409:
                raise exception.PortLimitExceeded()
            raise

    def _get_instance_nw_info(self, *args, **kwargs):
        nw_info = super(API, self)._get_instance_nw_info(*args, **kwargs)
        return _order_nw_info_by_label(nw_info)

    def get(self, context, network_uuid):
        """Get specific network for client."""
        client = neutronv2.get_client(context)
        try:
            network = client.show_network(network_uuid).get('network') or {}
            if network["tenant_id"] != context.project_id:
                raise exception.NetworkNotFound(network_id=network_uuid)

            subnets = client.list_subnets(id=network["subnets"]).get("subnets")
            cidrs = ", ".join([s["cidr"] for s in subnets])
            net = {"label": network["name"],
                   "cidr": cidrs,
                   "tenant_id": context.project_id,
                   "id": network["id"]}
        except neutron_client_exc.NetworkNotFoundClient:
            raise exception.NetworkNotFound(network_id=network_uuid)
        return net

    def validate_networks(self, context, requested_networks, num_instances,
                          *args, **kwargs):
        return num_instances

    def get_all(self, context, shared=False):
        """Get all networks for client."""
        client = neutronv2.get_client(context)
        kwargs = {}
        if shared:
            kwargs["shared"] = shared
        else:
            kwargs["tenant_id"] = context.project_id

        networks = client.list_networks(**kwargs).get('networks')
        ids = []
        for network in networks:
            network['label'] = network['name']
            ids.append(network["id"])
        subnets = client.list_subnets(
            network_id=ids, tenant_id=context.project_id).get("subnets")
        net_ids = {}

        for sub in subnets:
            net_ids[sub["network_id"]] = sub
        for network in networks:
            if network and network["id"] in net_ids:
                network["cidr"] = net_ids[network["id"]]["cidr"]
        return networks

    def create(self, context, **kwargs):
        neutron = neutronv2.get_client(context)
        body = {"network": {"name": kwargs["label"],
                            "tenant_id": context.project_id}}
        network = neutron.create_network(body=body)
        ip_version = netaddr.IPNetwork(kwargs["cidr"]).version
        subnet_body = {"subnet": {"network_id": network["network"]["id"],
                                  "cidr": kwargs["cidr"],
                                  "tenant_id": context.project_id,
                                  "gateway_ip": None,
                                  "ip_version": ip_version}}
        subnet = neutron.create_subnet(body=subnet_body)
        return [{"id": network["network"]["id"],
                 "cidr": subnet["subnet"]["cidr"],
                 "label": network["network"]["name"]}]

    def delete(self, context, id):
        neutron = neutronv2.get_client(context)
        try:
            neutron.delete_network(network=id)
        except neutron_client_exc.NetworkInUseClient:
            raise exception.NetworkBusy(network=id)
        except neutron_client_exc.NetworkNotFoundClient:
            raise exception.NetworkNotFound(network_id=id)

    def allocate_interface_for_instance(self, context, instance,
                                        network_id, **kwargs):
        client = neutronv2.get_client(context)
        try:
            net = client.show_network(network_id)["network"]
        except neutron_client_exc.NetworkNotFoundClient:
            raise exception.NetworkNotFound(network_id=network_id)

        instance_ports = client.list_ports(device_id=instance["uuid"])
        for p in instance_ports["ports"]:
            if p["network_id"] == network_id:
                raise exception.AlreadyAttachedToNetwork()

        segment_id = CONF.quantum_default_tenant_id
        zone = "compute:%s" % instance["availability_zone"]
        port_req_body = {"port": {"device_id": instance["uuid"],
                                  "device_owner": zone,
                                  "network_id": network_id,
                                  "segment_id": segment_id,
                                  "tenant_id": context.project_id,
                                  "admin_state_up": True}}
        port = client.create_port(port_req_body)["port"]
        network = network_model.Network(id=network_id, label=net["name"],
                                        bridge=port.get("bridge"),
                                        nvp_managed=not net["shared"])

        subnets = {}
        for fixed_ip in port["fixed_ips"]:
            subnet_id = fixed_ip["subnet_id"]
            if subnet_id not in subnets:
                subnets[subnet_id] = network_model.Subnet(id=subnet_id)
            subnets[subnet_id].add_ip(
                network_model.FixedIP(address=fixed_ip["ip_address"]))

        port_subnets = client.list_subnets(id=subnets.keys()).get("subnets")
        for port_sub in port_subnets:
            subnets[port_sub["id"]]["cidr"] = port_sub["cidr"]

        for sub_id, sub in subnets.iteritems():
            network.add_subnet(sub)

        nw_info = network_model.VIF(id=port["id"], network=network,
                                    address=port["mac_address"])

        # Compile a list of existing networks + new VIF network and update
        # the cache
        network_cache = self.conductor_api.instance_get_by_uuid(
                  context, instance['uuid'])['info_cache']['network_info']
        network_cache = jsonutils.loads(network_cache)
        net_ids = [iface['network']['id'] for iface in network_cache]
        net_ids.append(network_id)
        networks = self._get_available_networks(context,
                                                instance['project_id'],
                                                net_ids=net_ids)
        self.get_instance_nw_info(context, instance, networks=networks)
        return [nw_info]

    def deallocate_interface_for_instance(self, context, instance,
                                          interface_id, **kwargs):
        client = neutronv2.get_client(context)
        vifs = []
        try:
            port = client.show_port(interface_id).get("port")
            client.delete_port(interface_id)
            vif = network_model.VIF(id=port["id"],
                                    address=port["mac_address"])
            vifs.append(vif)
        except Exception:
            # This is really expected to be ignored
            pass
        self.get_instance_nw_info(context, instance)
        return vifs

    @base_api.refresh_cache
    def add_fixed_ip_to_instance(self, context, instance, network_id):
        """Add a fixed ip to the instance from specified network."""
        search_opts = {'network_id': network_id,
                       'segment_id': CONF.quantum_default_tenant_id}
        data = neutronv2.get_client(context).list_subnets(**search_opts)
        ipam_subnets = data.get('subnets', [])

        if not ipam_subnets:
            search_opts.pop("segment_id")
            data = neutronv2.get_client(context).list_subnets(**search_opts)
            ipam_subnets = data.get('subnets', [])

            if not ipam_subnets:
                raise exception.NetworkNotFoundForInstance(
                    instance_id=instance['uuid'])

        search_opts = {'device_id': instance['uuid'],
                       'network_id': network_id}
        data = neutronv2.get_client(context).list_ports(**search_opts)
        ports = data['ports']
        for p in ports:
            fixed_ips = p['fixed_ips']
            for subnet in ipam_subnets:
                if subnet["ip_version"] == 4:
                    fixed_ips.append({'subnet_id': subnet['id']})

            port_req_body = {'port': {'fixed_ips': fixed_ips}}
            try:
                neutronv2.get_client(context).update_port(p['id'],
                                                          port_req_body)
                return
            except Exception as ex:
                msg = _("Unable to update port %(portid)s on subnet "
                        "%(subnet_id)s with failure: %(exception)s")
                LOG.debug(msg, {'portid': p['id'],
                                'subnet_id': subnet['id'],
                                'exception': ex})

        raise exception.NetworkNotFoundForInstance(
            instance_id=instance['uuid'])

    @base_api.refresh_cache
    def remove_fixed_ip_from_instance(self, context, instance, address):
        """Remove a fixed ip from the instance."""
        search_opts = {'device_id': instance['uuid'],
                       'fixed_ips': 'ip_address=%s' % address}
        data = neutronv2.get_client(context).list_ports(**search_opts)
        ports = data['ports']
        address_found = False
        for p in ports:
            fixed_ips = p['fixed_ips']
            new_fixed_ips = []
            for fixed_ip in fixed_ips:
                if fixed_ip['ip_address'] != address:
                    new_fixed_ips.append(fixed_ip)
                else:
                    address_found = True

            if not address_found:
                continue

            port_req_body = {'port': {'fixed_ips': new_fixed_ips}}
            try:
                neutronv2.get_client(context).update_port(p['id'],
                                                          port_req_body)
                return
            except Exception as ex:
                LOG.debug("Unable to update port %(portid)s with"
                          " failure: %(exception)s",
                          {'portid': p['id'], 'exception': ex})

        raise exception.FixedIpNotFoundForSpecificInstance(
                instance_uuid=instance['uuid'], ip=address)

    def _get_floating_ips_by_fixed_and_port(self, client, fixed_ip, port):
        """Get floatingips from fixed ip and port."""
        return []

    def _get_subnets_from_port(self, context, port):
        """Return the subnets for a given port.

        Forked because we need the subnet routes at the end.
        """

        fixed_ips = port['fixed_ips']
        # No fixed_ips for the port means there is no subnet associated
        # with the network the port is created on.
        # Since list_subnets(id=[]) returns all subnets visible for the
        # current tenant, returned subnets may contain subnets which is not
        # related to the port. To avoid this, the method returns here.
        if not fixed_ips:
            return []
        search_opts = {'id': [ip['subnet_id'] for ip in fixed_ips]}
        data = neutronv2.get_client(context).list_subnets(**search_opts)
        ipam_subnets = data.get('subnets', [])
        subnets = []

        for subnet in ipam_subnets:
            subnet_dict = {'cidr': subnet['cidr'],
                           'gateway': network_model.IP(
                                address=subnet['gateway_ip'],
                                type='gateway'),
            }

            subnet_object = network_model.Subnet(**subnet_dict)
            for dns in subnet.get('dns_nameservers', []):
                subnet_object.add_dns(
                    network_model.IP(address=dns, type='dns'))

            # NOTE(tr3buchet): the following paragraph is our fork change
            # TODO(tr3buchet): remove this function once they add route code
            #                  upstream
            # NOTE(from koelker): this get business is all jank like for tests
            if subnet.get('ip_version', 6) == 4:
                for route in subnet.get('host_routes', []):
                    next_hop = network_model.IP(address=route['nexthop'],
                                                type='nexthop')
                    dest = route['destination']
                    route_object = network_model.Route(cidr=dest,
                                                       gateway=next_hop)
                    subnet_object.add_route(route_object)

            subnets.append(subnet_object)
        return subnets
