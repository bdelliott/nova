# Copyright 2011 Nicira Networks
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

from oslo.config import cfg

from nova.network.quantum2 import quantum_client
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging


LOG = logging.getLogger(__name__)

quantum_opts = [
    cfg.StrOpt('quantum_connection_host',
               default='127.0.0.1',
               help='HOST for connecting to quantum'),
    cfg.IntOpt('quantum_connection_port',
               default=9696,
               help='PORT for connecting to quantum'),
    cfg.StrOpt('quantum_default_tenant_id',
               default="default",
               help='Default tenant id when creating quantum networks'),
    cfg.IntOpt('quantum_request_timeout',
               default=20,
               help='Maximum amount of time to wait for quantum request'),
    ]

CONF = cfg.CONF

for opt in quantum_opts:
    try:
        CONF.register_opt(opt)
    except cfg.DuplicateOptError:
        pass


class QuantumClientConnection(object):
    """Abstracts connection to Quantum service into higher level
       operations performed by the QuantumManager.

       Separating this out as a class also let's us create a 'fake'
       version of this class for unit tests.
    """

    def __init__(self, client=None):
        """Initialize Quantum client class based on config."""
        if client:
            self.client = client
        else:
            self.client = quantum_client.Client(CONF.quantum_connection_host,
                                        CONF.quantum_connection_port,
                                        timeout=CONF.quantum_request_timeout,
                                        format="json",
                                        logger=LOG)

    def create_network(self, tenant_id, network_name, **kwargs):
        """Create network using specified name, return Quantum
           network UUID.
        """
        data = {'network': {'name': network_name}}
        for kw in kwargs:
            data['network'][kw] = kwargs[kw]
        resdict = self.client.create_network(data, tenant=tenant_id)
        return resdict["network"]["id"]

    def get_network_name(self, tenant_id, network_id):
        net = self.client.show_network_details(network_id, tenant=tenant_id)
        return net["network"]["name"]

    def delete_network(self, tenant_id, net_id):
        """Deletes Quantum network with specified UUID."""
        self.client.delete_network(net_id, tenant=tenant_id)

    def network_exists(self, tenant_id, net_id):
        """Determine if a Quantum network exists for the
           specified tenant.
        """
        try:
            self.client.show_network_details(net_id, tenant=tenant_id)
            return True
        except quantum_client.QuantumNotFoundException:
            # Not really an error.  Real errors will be propogated to caller
            return False

    def get_networks(self, tenant_id):
        """Retrieve all networks for this tenant."""
        return self.client.list_networks(tenant=tenant_id)

    def create_and_attach_port(self, tenant_id, net_id, interface_id,
                               **kwargs):
        """Creates a Quantum port on the specified network, sets
           status to ACTIVE to enable traffic, and attaches the
           vNIC with the specified interface-id.
        """
        LOG.debug("Connecting interface %(interface_id)s to "
                    "net %(net_id)s for %(tenant_id)s",
                  {'interface_id': interface_id, 'net_id': net_id,
                   'tenant_id': tenant_id})
        port_data = {'port': {'state': 'ACTIVE'}}
        for kw in kwargs:
            port_data['port'][kw] = kwargs[kw]
        resdict = self.client.create_port(net_id, port_data, tenant=tenant_id)
        port_id = resdict["port"]["id"]

        attach_data = {'attachment': {'id': interface_id}}
        self.client.attach_resource(net_id, port_id, attach_data,
                                    tenant=tenant_id)
        return port_id

    def update_port(self, tenant_id, net_id, port_id, **kwargs):
        """Updates a port with the specified kwargs."""
        LOG.debug('Updating port |%(port_id)s| on network |%(net_id)s| '
                  'with |%(kwargs)s| for tenant id |%(tenant_id)s|',
                  {'port_id': port_id, 'net_id': net_id,
                   'kwargs': kwargs, 'tenant_id': tenant_id})
        port_data = {'port': kwargs}

        self.client.update_port(tenant=tenant_id, network=net_id,
                                port=port_id, body=port_data)

    def update_rxtx_factor_on_port(self, tenant_id, net_id, port_id,
                                   rxtx_factor):
        """Updates the rxtx_factor on a Quantum port on the specified
           network.
        """
        self.update_port(tenant_id, net_id, port_id, rxtx_factor=rxtx_factor)

    def update_allowed_address_pairs_on_port(self, tenant_id, net_id, port_id,
                                             allowed_address_pairs):
        """Updates the allowed address pairs on a Quantum port on the specified
           network.
        """
        self.update_port(tenant_id, net_id, port_id,
                         allowed_address_pairs=allowed_address_pairs)

    def detach_and_delete_port(self, tenant_id, net_id, port_id):
        """Detach and delete the specified Quantum port."""
        LOG.debug("Deleting port %(port_id)s on net %(net_id)s"
                    " for %(tenant_id)s",
                  {'port_id': port_id, 'net_id': net_id,
                   'tenant_id': tenant_id})

        self.client.detach_resource(net_id, port_id, tenant=tenant_id)
        self.client.delete_port(net_id, port_id, tenant=tenant_id)

    def get_port_by_attachment(self, tenant_id, net_id, attachment_id):
        """Given a tenant and network, search for the port UUID that
           has the specified interface-id attachment.
        """
        port_list = []
        try:
            port_list_resdict = self.client.list_ports(net_id,
                tenant=tenant_id,
                filter_ops={'attachment': attachment_id})
            port_list = port_list_resdict["ports"]
        except quantum_client.QuantumNotFoundException:
            return None

        port_list_len = len(port_list)
        if port_list_len == 1:
            return port_list[0]['id']
        elif port_list_len > 1:
            msg = (_("Expected single port with attachment "
                     "%(attachment_id)s, found %(port_list_len)s") %
                   {'attachment_id': attachment_id,
                    'port_list_len': port_list_len})
            raise Exception(msg)
        return None

    def get_attached_ports(self, tenant_id, network_id):
        rv = []
        port_list = self.client.list_ports(network_id, tenant=tenant_id)
        for p in port_list["ports"]:
            try:
                port_id = p["id"]
                port = self.client.show_port_attachment(network_id,
                                port_id, tenant=tenant_id)
                # Skip ports without an attachment
                if "id" not in port["attachment"]:
                    continue
                rv.append({'port-id': port_id,
                           'attachment': port["attachment"]["id"]})
            except quantum_client.QuantumNotFoundException:
                pass
        return rv
