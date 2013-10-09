# Copyright 2011 Grid Dynamics
# Copyright 2011 OpenStack LLC.
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


import netaddr
import netaddr.core as netexc
from webob import exc

from oslo.config import cfg
from oslo import messaging

from nova.api.openstack import extensions
from nova import context as nova_context
from nova.db.sqlalchemy import api as db_api
from nova import exception
import nova.network
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging
from nova import quota

opts = [
    cfg.IntOpt('quota_networks',
               default=3,
               help='Number of private networks allowed per project'),
    cfg.BoolOpt("quark_networks", default=False,
                help="Enables or disables handling for Quark networks")
]

CONF = cfg.CONF
CONF.register_opts(opts)


try:
    os_network_v2_opts = [
        cfg.StrOpt('quantum_default_tenant_id',
                   default="default",
                   help=('Default tenant id when creating quantum '
                   'networks'))
    ]
    CONF.register_opts(os_network_v2_opts)
except cfg.DuplicateOptError:
    # NOTE(jkoelker) These options are verbatim in the quantum connection
    #                this is here to make sure they are registered for our
    #                use.
    pass


QUOTAS = quota.QUOTAS
LOG = logging.getLogger(__name__)
authorize = extensions.extension_authorizer('compute', 'os-networksv2')


def network_dict(network):
    if not network:
        return {}
    net = dict(id=network["id"], label=network["label"])
    if "cidr" in network:
        net["cidr"] = network["cidr"]
    return net


def _network_call(func):
    """Call the network api, trying to reraise any exceptions."""
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except messaging.RemoteError as err:
            LOG.error(_("Remote Traceback: %s"), err.traceback)
            e = getattr(exception, err.exc_type, None)
            if e is None:
                raise
            # FIXME(comstud): Work around W602 that still fails in pep 1.0
            # because of '.'
            value = err.value
            raise e, value, None
    return wrapper


class NetworkAPIProxy(object):
    def __init__(self, network_api=None):
        self.api = network_api or nova.network.API()

    def __getattribute__(self, name):
        api = object.__getattribute__(self, 'api')
        return _network_call(object.__getattribute__(api, name))


class NetworkController(object):
    def __init__(self, network_api=None):
        self.network_api = NetworkAPIProxy(network_api)
        self._default_networks = []

    def _refresh_default_networks(self):
        try:
            self._default_networks = self._get_default_networks()
        except Exception:
            LOG.exception(_("Failed to get default networks"))
            # NOTE(jkoelker) if the network service isn't availible
            #                don't bomb out
            self._default_networks = []

    def _get_default_networks(self):
        project_id = CONF.quantum_default_tenant_id
        ctx = nova_context.RequestContext(user_id=None,
                                          project_id=project_id)
        ctx = ctx.elevated()

        networks = {}
        net_list = None
        if CONF.quark_networks:
            net_list = self.network_api.get_all(ctx, shared=True)
        else:
            net_list = self.network_api.get_all(ctx)

        for n in net_list:
            networks[n['id']] = n['label']
        return [{'id': k, 'label': v} for k, v in networks.iteritems()]

    def index(self, req):
        context = req.environ['nova.context']
        authorize(context, action='index')
        networks = self.network_api.get_all(context)
        if not self._default_networks:
            self._refresh_default_networks()
        networks.extend(self._default_networks)
        networks = [network_dict(net) for net in networks]
        return {'networks': networks}

    def show(self, req, id):
        context = req.environ['nova.context']
        authorize(context, action='show')
        LOG.debug("Showing network with id %s", id)
        try:
            network = self.network_api.get(context, id)
        except exception.NetworkNotFound:
            raise exc.HTTPNotFound(_("Network not found"))
        except exception.NetworkFoundMultipleTimes:
            raise exc.HTTPNotFound(_("Network matched multiple items"))
        return {'network': network_dict(network)}

    def delete(self, req, id):
        context = req.environ['nova.context']
        authorize(context, action='delete')
        try:
            reservation = QUOTAS.reserve(context, networks=-1)
        except Exception:
            reservation = None
            LOG.exception(_("Failed to update usages deallocating "
                            "network."))

        LOG.info(_("Deleting network with id %s") % id)

        try:
            self.network_api.delete(context, id)
            if reservation:
                QUOTAS.commit(context, reservation)
            response = exc.HTTPAccepted()
        except exception.NetworkNotFound:
            response = exc.HTTPNotFound(_("Network not found"))
        except exception.NetworkFoundMultipleTimes:
            response = exc.HTTPNotFound(_("Network matched multiple items"))
        except exception.NetworkBusy:
            response = exc.HTTPForbidden(_("Network has active ports"))

        return response

    def create(self, req, body):
        if not body:
            raise exc.HTTPUnprocessableEntity()

        context = req.environ['nova.context']
        authorize(context, action='create')

        network = body['network']
        label = network['label']
        cidr = network['cidr']
        if not cidr:
            msg = _("No CIDR requested")
            raise exc.HTTPBadRequest(explanation=msg)
        try:
            net = netaddr.IPNetwork(cidr)
            if net.size < 4:
                msg = _("Requested network does not contain "
                        "enough (2+) usable hosts")
                raise exc.HTTPBadRequest(explanation=msg)
            net_cidr = str(net.cidr)
            msg_kwargs = {"net_cidr": net_cidr, "cidr": cidr}
            if (cidr != net_cidr):
                msg = _("'%(cidr)s' isn't a recognized IP subnet cidr,"
                        " '%(net_cidr)s' is recommended") % msg_kwargs
                raise exc.HTTPBadRequest(explanation=msg)

            if net.version == 6 and net.prefixlen > 64:
                msg = _("Requested cidr: %s is too small, must be a "
                        "larger subnet. A prefix less than /65 is "
                        "required.") % (net_cidr)
                raise exc.HTTPBadRequest(explanation=msg)

        except netexc.AddrFormatError:
            msg = _("CIDR is malformed.")
            raise exc.HTTPBadRequest(explanation=msg)
        except netexc.AddrConversionError:
            msg = _("Address could not be converted.")
            raise exc.HTTPBadRequest(explanation=msg)
        except ValueError:
            msg = _("CIDR is malformed.")
            raise exc.HTTPBadRequest(explanation=msg)

        try:
            reservation = QUOTAS.reserve(context, networks=1)
        except exception.OverQuota:
            msg = _("Quota exceeded, too many networks.")
            raise exc.HTTPBadRequest(explanation=msg)

        try:
            network = self.network_api.create(context, label=label, cidr=cidr)
            QUOTAS.commit(context, reservation)
        except Exception:
            QUOTAS.rollback(context, reservation)
            msg = _("Create networks failed")
            LOG.exception(msg, extra=network)
            raise exc.HTTPServiceUnavailable(explanation=msg)

        return {'network': network_dict(network[0])}


class Os_networksv2(extensions.ExtensionDescriptor):
    """Admin-only Network Management Extension."""

    name = "OSNetworksV2"
    alias = "os-networksv2"
    namespace = "http://docs.openstack.org/ext/services/api/v1.1"
    updated = "2012-03-07T14:46:43Z"

    def get_resources(self):
        ext = extensions.ResourceExtension('os-networksv2',
                                           NetworkController())
        return [ext]


def _sync_networks(context, project_id, user_id, session):
    # NOTE(jkoelker) The duece only cares about the project_id
    networks = NetworkAPIProxy().get_all(context)
    return dict(networks=len(networks))


db_api.QUOTA_SYNC_FUNCTIONS["_sync_networks"] = _sync_networks

QUOTAS.register_resource(quota.ReservableResource('networks',
                                                  '_sync_networks',
                                                  'quota_networks'))
