# vim: tabstop=4 shiftwidth=4 softtabstop=4

# Copyright 2010-2011 OpenStack LLC.
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

import itertools

from nova.api.openstack import common
from nova.api.openstack.compute.views import addresses
from nova.openstack.common import log as logging


LOG = logging.getLogger(__name__)


class AddressWithUUID(addresses.ViewBuilder):
    """Models server addresses as a dictionary."""

    def basic_uuid(self, ip, id):
        return {
            "version": ip["version"],
            "addr": ip["address"],
            "id": id
        }

    def show(self, network, label):
        """Returns a dictionary describing a network."""
        all_ips = itertools.chain(network["ips"], network["floating_ips"])

        return {label: [self.basic_uuid(ip, network["id"]) for ip in all_ips]}

    def index(self, networks):
        """Return a dictionary describing a list of networks."""
        addresses = {}
        for label, network in networks.items():
            network_dict = self.show(network, label)
            addresses[label] = network_dict[label]

        return dict(addresses=addresses)
