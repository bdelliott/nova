# Copyright (c) 2014 Rackspace Hosting
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

"""Utilities and helper functions."""

import functools
import resource

from nova.openstack.common import lockutils
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)


def maxmem():
    # return the peak RSS memory usage of the process
    # this value is in KB on linux
    usage = resource.getrusage(resource.RUSAGE_SELF)
    return usage.ru_maxrss


class MemWrap(object):
    # wrap all the functions in the given api

    def __init__(self, api):
        self.api = api

    def __getattr__(self, key):
        attr = getattr(self.api, key)
        if callable(attr):
            return self._wrap(attr)
        else:
            return attr

    def _wrap(self, f):
        """Report differences in *maximum* RSS memory for the process when a
        function is executed.  This can be used to figure out where there was a
        a large allocation that initially grew the size of the process.

        Also, enforce serial access to DB API methods -  They are essentially
        already serial because the MySQL C driver blocks the process, so this
        should not negatively affect performance (much).
        memory got allocated.
        """
        @lockutils.synchronized('db-api-lock')
        @functools.wraps(f)
        def inner(*args, **kwargs):
            x = maxmem()
            rv = f(*args, **kwargs)
            y = maxmem()

            memdiff = y - x
            if memdiff > 0:
                # don't bother logging until we see an increase
                LOG.debug("Memory difference: %(name)s %(memdiff)d KB",
                          {'name': f.__name__, 'memdiff': memdiff})

            return rv

        return inner
