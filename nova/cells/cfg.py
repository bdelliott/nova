# Copyright (c) 2012 Openstack, LLC.
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

"""Cells Configuration."""

from oslo.config import cfg

from nova.cells import utils as cells_utils
from nova.openstack.common.gettextutils import _
from nova.openstack.common import jsonutils
from nova.openstack.common import log as logging
from nova import utils

cells_opts = [
        cfg.StrOpt('config_file',
                   default='cells_config.json',
                   help="Configuration file for cells")
]

CONF = cfg.CONF
CONF.register_opts(cells_opts, group='cells')
LOG = logging.getLogger(__name__)


class CellsConfig(object):
    def __init__(self):
        cells_config_file = CONF.cells.config_file
        if cells_config_file:
            self._cells_config_file = CONF.find_file(cells_config_file)
            if not self._cells_config_file:
                LOG.warn(_("No cells config file found. (%s)"),
                         CONF.cells.config_file)
        else:
            self._cells_config_file = None
        self._cells_config_cacheinfo = {}
        self._cells_config = {}
        self._reload_cells_config()

    def _reload_cells_config(self):
        def _reload(data):
            self._cells_config = jsonutils.loads(data)

        if not self._cells_config_file:
            cells_config_file = CONF.cells.config_file
            if cells_config_file:
                # See if it exists now
                self._cells_config_file = CONF.find_file(cells_config_file)

        if self._cells_config_file:
            utils.read_cached_file(self._cells_config_file,
                    self._cells_config_cacheinfo, reload_func=_reload)

    def get_cell_dict(self, cell_name):
        self._reload_cells_config()
        return self._cells_config.get(cell_name, {})

    def get_value(self, cell_name, key, default=None):
        cell_info = self.get_cell_dict(cell_name)
        return cell_info.get(key, default)

    def cell_has_permission(self, routing_path, cell_name, context,
                            permission):
        # test user's roles against configured rules to see if they have the
        # requested permission for the given cell
        roles = set(context.roles)

        # test cell specific rules
        allowed = self._test(cell_name, roles, permission)
        if allowed is not None:
            return allowed

        # test generic rules for this routing path
        allowed = self._test(routing_path, roles, permission)
        if allowed is not None:
            return allowed

        return False  # default to deny if no rules match

    def _test(self, path, roles, permission):
        # test rules for the given cell path
        rules = self.get_value(path, 'rules', default=[])

        for rule in rules:
            allowed = self._run_rule(roles, rule, permission)
            if allowed is not None:
                # short-circuit rule matching
                return allowed

        return None  # no matching rules

    def _run_rule(self, roles, rule, permission):
        """Test the given rule for the requested permission

        :params roles: user's roles
        :rule: 3-tuple of (role, action, permissions)
        :params action: Either 'allow' or 'deny'
        :permission: single character permission to check
        :returns: True if permission is allowed, False if denied, or None if
                  the rule doesn't apply to the user's roles
        """
        role, action, perm_chars = rule
        action = action.lower()

        if role not in roles and role != "*":
            return None

        # Found a matching role override
        if '*' in perm_chars or permission in perm_chars:
            return "allow" == action

        return None

    def cell_read_only(self, cell_name, context):
        ro = self.get_value(cell_name, 'read_only', False)
        if ro or context is None:
            return ro

        x = cell_name.rfind(cells_utils.PATH_CELL_SEP)
        routing_path = cell_name[:x]

        return self.cell_has_permission(routing_path, cell_name, context, 'r')
