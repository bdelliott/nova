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
Cell Permissions Filter

Checks permissions in config file to see which cells should be filtered
"""

from nova.cells import filters
from nova.cells import utils as cells_utils
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class CellPermissionsFilter(filters.BaseCellFilter):

    def filter_all(self, cells, filter_properties):
        context = filter_properties['context']
        routing_path = filter_properties['routing_path']
        scheduler = filter_properties['scheduler']
        cells_config = scheduler.state_manager.cells_config
        result = []
        for cell in cells:
            cell_name = self._name(routing_path, cell)
            if cells_config.cell_has_permission(routing_path, cell_name,
                                                context, 'b'):
                result.append(cell)
        if len(result) < len(cells):
            drop_msg = [str(cell) for cell in set(cells) - set(result)]
            LOG.info(_("Dropping cells '%(drop_msg)s' due to lack of "
                    "permissions"), locals())
        return result

    def _name(self, routing_path, cell):
        cell_name = routing_path
        if not cell.is_me:
            cell_name += cells_utils.PATH_CELL_SEP + cell.name

        return cell_name
