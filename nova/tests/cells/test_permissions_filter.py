# Copyright (c) 2012 Openstack, LLC
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
Unit tests for cell permissions filter.
"""

from nova.cells import cfg as cells_cfg
from nova.cells.filters import permissions
from nova.cells import state as cells_state
from nova.cells import utils
from nova import context
from nova.openstack.common import log as logging
from nova import test
from oslo.config import cfg


CONF = cfg.CONF
CONF.import_opt('name', 'nova.cells.opts', group='cells')
LOG = logging.getLogger(__name__)

CELL_NAMES = ["c1", "c2", "c3"]


class MockConfig(cells_cfg.CellsConfig):
    def _reload_cells_config(self):
        c1_full_name = utils.PATH_CELL_SEP.join(["US", "East",
            CELL_NAMES[0]])
        cell1_rules = [
            ('privaterole', 'allow', 'b'),
            ('*', 'deny', 'b'),
        ]

        c2_full_name = utils.PATH_CELL_SEP.join(["US", "East",
            CELL_NAMES[1]])
        cell2_rules = [
            ('myrole', 'deny', 'b'),
        ]

        # c3 has no specific config and should fallback to region rules
        region = utils.PATH_CELL_SEP.join(["US", "East"])
        region_rules = [
            ('privaterole', 'deny', 'b'),
            ('*', 'allow', 'b'),
        ]

        config = {
            c1_full_name: {'rules': cell1_rules},
            c2_full_name: {'rules': cell2_rules},
            region: {'rules': region_rules},
        }
        self._cells_config = config


class PermissionsFilterTest(test.TestCase):
    """Test use of cell build permissions to filter list of cells."""

    def setUp(self):
        super(PermissionsFilterTest, self).setUp()

        my_cell_name = utils.PATH_CELL_SEP.join(["US", "East", "c2"])
        self.flags(name=my_cell_name, group='cells')

        self.config = MockConfig()
        self.pfilter = permissions.CellPermissionsFilter()

        self.cells = [cells_state.CellState(name) for name in CELL_NAMES]
        self.ctxt = context.RequestContext('fake', 'fake', roles=['myrole'])

        routing_path = utils.PATH_CELL_SEP.join(["US", "East"])

        scheduler = self.mox.CreateMockAnything()
        scheduler.state_manager = self.mox.CreateMockAnything()
        scheduler.state_manager.cells_config = self.config

        self.filter_properties = {'routing_path': routing_path,
                                  'context': self.ctxt,
                                  'scheduler': scheduler}

    def test_private_cell(self):
        # builds should land only in c1
        self.ctxt.roles = ['privaterole']
        remnant = self.pfilter.filter_all(self.cells, self.filter_properties)
        self.assertEqual(1, len(remnant))
        self.assertEqual('c1', remnant[0].name)

    def test_wildcard_roles(self):
        remnant = self.pfilter.filter_all(self.cells, self.filter_properties)
        self.assertEqual(1, len(remnant))
        self.assertEqual('c3', remnant[0].name)

    def test_another_role(self):
        self.ctxt.roles = ['anotherrole']
        remnant = self.pfilter.filter_all(self.cells, self.filter_properties)

        # gets access to c2 and c3 by region wildcard
        self.assertEqual(2, len(remnant))
        self.assertEqual('c2', remnant[0].name)
        self.assertEqual('c3', remnant[1].name)
