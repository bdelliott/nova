# Copyright (c) 2011-2012 OpenStack, LLC.
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
Rackspace Near/Far filter.
"""

from nova.cells import filters
from nova.cells import utils as cells_utils
from nova import db
from nova import exception
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)

PATH_CELL_SEP = cells_utils.PATH_CELL_SEP


# NOTE(johannes): The original exception was dropped from the cells patch
# and there isn't another exception that seems suitable. Placing this
# here (instead of nova/exception.py) to reduce the conflict surface area
# of this patch.
class CellsFilterError(exception.NovaException):
    msg_fmt = _("Error in cells filter: %(reason)s")


def cell_name_for_next_hop(dest_cell_name, routing_path):
    """Return the cell for the next routing hop.

    The next hop might be ourselves if this is where the message is
    supposed to go.  None is returned in this case.
    """
    if dest_cell_name == routing_path:
        return None
    current_hops = routing_path.count(PATH_CELL_SEP)
    next_hop_num = current_hops + 1
    dest_hops = dest_cell_name.count(PATH_CELL_SEP)
    if dest_hops < current_hops:
        reason = (_("destination is %(dest_cell_name)s but routing_path "
                    "is %(routing_path)s") %
                  {'dest_cell_name': dest_cell_name,
                   'routing_path': routing_path})
        raise exception.CellRoutingInconsistency(reason=reason)
    dest_name_parts = dest_cell_name.split(PATH_CELL_SEP)
    if PATH_CELL_SEP.join(dest_name_parts[:next_hop_num]) != routing_path:
        reason = (_("destination is %(dest_cell_name)s but routing_path "
                    "is %(routing_path)s") %
                  {'dest_cell_name': dest_cell_name,
                   'routing_path': routing_path})
        raise exception.CellRoutingInconsistency(reason=reason)
    return dest_name_parts[next_hop_num]


class RAXNearFarCellFilter(filters.BaseCellFilter):
    """Rackspace near/far instance filter.
    Check for 'near' or 'far' in the scheduler_hints dict.  Values
    are instance_uuids.

    'near' an instance_uuid needs to target the build for the same
    cell as instance_uuid.

    'far' means to target the build for a different cell than
    instance_uuid.
    """

    @staticmethod
    def _get_cell_name(context, instance_uuid, filter_type):
        try:
            instance = db.instance_get_by_uuid(context,
                    instance_uuid)
        except exception.InstanceNotFound:
            reason = (_("Instance '%(instance_uuid)s' not found for "
                       "'%(filter_type)s' scheduler_hint") %
                      {'instance_uuid': instance_uuid,
                       'filter_type': filter_type})
            raise CellsFilterError(reason=reason)
        cell_name = instance['cell_name']
        if not cell_name:
            reason = (_("Instance '%(instance_uuid)s' is not assigned to a "
                        "cell for '%(filter_type)s' scheduler_hint") %
                      {'instance_uuid': instance_uuid,
                       'filter_type': filter_type})
            raise CellsFilterError(reason=reason)
        return cell_name

    def _find_cell(self, cell_name):
        try:
            next_hop_name = cell_name_for_next_hop(
                    cell_name, self.routing_path)
        except exception.CellRoutingInconsistency:
            return None
        if not next_hop_name:
            return self.state_manager.my_cell_state
        return self.state_manager.child_cells.get(next_hop_name)

    def _standardize_scheduler_hints(self):
        """Standardizes the contents of scheduler_hints, so we just need to
        look for 'same_cell', 'different_cell', and 'different_dczone'

        When we're routing down, we may have some routing-only hops, so they
        will not be able to look up instances.
        """
        # {'near': instance_uuid} becomes {'same_cell': cell_name}
        near_instance_uuid = self.scheduler_hints.pop('near', None)
        if near_instance_uuid:
            cell_name = self._get_cell_name(self.context, near_instance_uuid,
                                            'near')
            self.scheduler_hints['same_cell'] = cell_name
        # {'far': instance_uuid} becomes {'different_cell': cell_name} (and
        # possibly {'different_dczone': dczone}
        far_uuid = self.scheduler_hints.pop('far', None)
        if far_uuid:
            cell_name = self._get_cell_name(self.context, far_uuid, 'far')
            self.scheduler_hints['different_cell'] = cell_name
            cell = self._find_cell(cell_name)
            if cell:
                # We should also try to filter DCZONE if we have it.
                dczone = cell.capabilities.get('DCZONE')
                if dczone:
                    self.scheduler_hints['different_dczone'] = dczone[0]

    def filter_all(self, cells, filter_properties):
        self.context = filter_properties['context']
        self.scheduler_hints = filter_properties.get('scheduler_hints')
        if not self.scheduler_hints:
            return cells
        self.routing_path = filter_properties['routing_path']
        self.state_manager = filter_properties['scheduler'].state_manager

        # First, standardize the scheduler hints so we only need to look for
        # 'same_cell', 'different_cell', and 'different_dczone'
        self._standardize_scheduler_hints()

        # If we find same_cell, we'll filter out all others
        same_cell = self.scheduler_hints.pop('same_cell', None)
        if same_cell:
            LOG.info(_("Forcing direct route to %(same_cell)s because "
                    "of 'same_cell' scheduler hint"), locals())
            scheduler = filter_properties['scheduler']
            scheduler.msg_runner.schedule_run_instance(
                    self.context, same_cell,
                    filter_properties['host_sched_kwargs'])
            # Returning None means to skip further scheduling, because we
            # handled it.
            return

        # If we find 'different_cell' try to avoid it
        different_cell = self.scheduler_hints.get('different_cell')
        if different_cell:
            hops_left = (different_cell.count(cells_utils.PATH_CELL_SEP) -
                         self.routing_path.count(cells_utils.PATH_CELL_SEP))
            cell = self._find_cell(different_cell)
            # If there's only 1 hop left, we need to remove
            # this cell.. otherwise it's okay to include it,
            # because the next cell down can filter.
            #
            # Also, if we're the cell, remove ourselves from
            # the set.  This should be the case if hops_left == 0
            if cell and hops_left <= 1:
                try:
                    LOG.info(_("Removing cell %(cell)s because "
                            "of 'different_cell' scheduler_hint of "
                            "'%(different_cell)s'"), locals())
                    cells.remove(cell)
                except KeyError:
                    pass
                if not cells:
                    return []

        # Try to avoid the dczone of the enemy instance too
        different_dczone = self.scheduler_hints.get('different_dczone')
        if different_dczone:
            result = []
            matching_dczone_cells = []
            for cell in cells:
                if (cell.capabilities.get('DCZONE', [None])[0] ==
                        different_dczone):
                    matching_dczone_cells.append(cell)
                else:
                    result.append(cell)
            # Remove cells that match the DCZONE
            if matching_dczone_cells:
                LOG.info(_("Removing cells %(matching_dczone_cells)s "
                        "because of 'different_dczone' scheduler_hint "
                        "of %(different_dczone)s"), locals())
            return result
        return cells
