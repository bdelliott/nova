# Copyright (c) 2011-2012 Rackspace Hosting
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

import math

from oslo.config import cfg

from nova.openstack.common import log as logging
from nova.scheduler import filters

filter_opts = [
    cfg.IntOpt('rackspace_max_ios_per_host',
            default=8,
            help=("Ignore hosts that have too many builds/resizes/snaps/"
                    "migrations")),
    cfg.IntOpt('rackspace_max_instances_per_host',
            default=50,
            help="Ignore hosts that have too many instances"),
    cfg.IntOpt('scheduler_spare_host_percentage',
            default=10,
            help='Percentage of hosts that should be reserved as spares'),
    cfg.BoolOpt('rackspace_ram_check_enabled',
            default=False,
            help='Toggle flag for _ram_check_filter memory reserve logic'),
    cfg.IntOpt('rackspace_ram_check_threshold',
            default=2048,
            help='If flavor is smaller than this memory value (in MB), '
                 'add an extra reserve.  (See _ram_check_filter.)'),
    cfg.IntOpt('rackspace_ram_check_reserve',
            default=1024,
            help='Memory reserve (in MB) to add if flavor is less than '
                 'the rackspace_ram_check_threshold.  (See '
                 '_ram_check_filter.)'),

]

CONF = cfg.CONF
CONF.register_opts(filter_opts)

LOG = logging.getLogger(__name__)

OVERHEAD_BASE = 3
OVERHEAD_PER_MB = 0.00781
OVERHEAD_PER_VCPU = 1.5


class RackspaceFilter(filters.BaseHostFilter):
    """Rackspace hard rule filtering."""

    def _io_ops_filter(self, host_state):
        """Only return hosts that don't have too many IO Ops."""
        num_io_ops = host_state.num_io_ops
        max_ios = CONF.rackspace_max_ios_per_host
        passes = num_io_ops < max_ios
        if not passes:
            LOG.debug("%(host_state)s fails IOOps check: "
                    "Max IOs per host is set to %(max_ios)s", locals())
        return passes

    def _num_instances_filter(self, host_state):
        """Only return hosts that don't have too many instances."""
        num_instances = host_state.num_instances
        max_instances = CONF.rackspace_max_instances_per_host
        passes = num_instances < max_instances
        if not passes:
            LOG.debug("%(host_state)s fails num_instances check: "
                    "Max instances per host is set to %(max_instances)s",
                    locals())
        return passes

    def _ram_check_filter(self, host_state, filter_properties):
        """Somewhat duplicates RamFilter, but provides extra 1G reserve
        for instances < `rackspace_ram_check_threshold`G.  This is an
        attempt to reduce issues with racing for resources on hosts that
        are nearly full and the extra overhead that Xen uses per VM.
        In addition we add in the estimated RAM overheads, using the same
        calculation used in the ResourceManager on the compute node.
        """
        instance_type = filter_properties.get('instance_type')
        requested_ram = self._estimate_used_memory_mb(instance_type)
        free_ram_mb = host_state.free_ram_mb
        if requested_ram < CONF.rackspace_ram_check_threshold:
            extra_reserve = CONF.rackspace_ram_check_reserve
        else:
            extra_reserve = 0
        passes = free_ram_mb >= (requested_ram + extra_reserve)
        if not passes:
            LOG.debug("%(host_state)s fails RAM check: "
                    "Need %(requested_ram)sMB + %(extra_reserve)sMB reserve",
                    locals())
        return passes

    def _estimate_used_memory_mb(self, instance_type):
        memory_mb = instance_type['memory_mb']
        vcpus = instance_type.get('vcpus', 1)
        overhead = self._estimate_instance_overhead(memory_mb, vcpus)
        return memory_mb + overhead

    def _estimate_instance_overhead(self, memory_mb, vcpus):
        #TODO(johngarbutt) we need to share code with xenapi/driver.py
        overhead = (OVERHEAD_BASE
                    + (memory_mb * OVERHEAD_PER_MB)
                    + (vcpus * OVERHEAD_PER_VCPU))
        return int(math.ceil(overhead))

    def _host_passes(self, host_state, filter_properties):
        """Rackspace server best match hard rules."""
        if CONF.rackspace_ram_check_enabled and not \
                self._ram_check_filter(host_state, filter_properties):
            return False
        if not self._io_ops_filter(host_state):
            return False
        if not self._num_instances_filter(host_state):
            return False
        return True

    def filter_all(self, host_states, filter_properties):
        """Entrypoint into the filter.  Beware that 'host_states' can
        be an iterator...
        """
        scheduler_hints = filter_properties.get('scheduler_hints') or {}
        target_host = scheduler_hints.get('0z0ne_target_host', None)
        if target_host:
            # Specific target should ignore other checks.
            targeted_hosts = target_host.split(',')
            LOG.debug("Filter forcing target(s): %(target_host)s",
                    locals())
            for host_state in host_states:
                if host_state.host in targeted_hosts:
                    yield host_state
            return

        pct_spare = CONF.scheduler_spare_host_percentage
        if pct_spare:
            tot_num_hosts = filter_properties['total_hosts']
            target_spares = tot_num_hosts / pct_spare
        else:
            target_spares = 0

        # We want to leave 'target_spares' number of hosts as empty,
        # if possible.
        empty_host = None
        num_returned = 0
        for host_state in host_states:
            if not self._host_passes(host_state, filter_properties):
                continue
            if target_spares > 0 and not host_state.num_instances:
                # We still want spares, so ignore this host.
                target_spares -= 1
                # Keep track of at least 1 empty host in the case
                # we have no choice but to use a spare.
                empty_host = host_state
                LOG.debug("%(host_state)s being reserved as spare",
                        locals())
                continue
            num_returned += 1
            yield host_state
        # All choices got filtered.  Return an empty host if we have one
        if empty_host and not num_returned:
            LOG.debug("%(empty_host)s being unreserved as spare",
                    locals())
            yield empty_host
