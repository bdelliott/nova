import functools

from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class ServiceStat(object):
    """Track information related to API performance"""

    def __init__(self, api):
        self.api = api

    def __getattr__(self, name):
        attr = getattr(self.api, name)
        if not callable(attr):
            # e.x. RPC_API_VERSION
            return attr

        LOG.warn("Proxying call to: %s" % attr)
        return functools.partial(self._invoke, attr)

    def _invoke(self, service_fn, *args, **kwargs):
        LOG.warn("INVOKING THIS SHIZZLE: %s" % service_fn)

        # TODO run stat driver
        # default to collecting mean, median, standard dev?
        # recent versus all-time?
        return service_fn(*args, **kwargs)
