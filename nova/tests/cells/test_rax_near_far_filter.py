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
"""
Unit tests for cell rax_near_far filter.
"""

import uuid

from nova.cells import cfg as cells_cfg
from nova.cells.filters import rax_near_far
from nova.cells import state as cells_state
from nova import context
from nova import test


class MockConfig(cells_cfg.CellsConfig):
    def _reload_cells_config(self):
        config = {
            'global': {},
            'global!cell0': {},
            'global!cell1': {},
            'global!cell2': {},
        }
        self._cells_config = config


class CellsRAXNearFarFilterTest(test.TestCase):
    """Test that we can filter target cells by how near or far they are
    compared to an instance.
    """

    def setUp(self):
        super(CellsRAXNearFarFilterTest, self).setUp()

        self.flags(name='global', group='cells')

        self.config = MockConfig()
        self.filter = rax_near_far.RAXNearFarCellFilter()

        self.cells = [cells_state.CellState('cell%d' % i) for i in xrange(3)]
        child_cells = dict((c.name, c) for c in self.cells)
        self.context = context.RequestContext('fake', 'fake')

        routing_path = 'global'

        scheduler = self.mox.CreateMockAnything()
        scheduler.state_manager = self.mox.CreateMockAnything()
        scheduler.state_manager.cells_config = self.config
        scheduler.state_manager.child_cells = child_cells

        self.scheduler = scheduler

        self.filter_props = {'routing_path': routing_path,
                             'context': self.context,
                             'scheduler': scheduler,
                             'host_sched_kwargs': {}}

        self.instance = {'uuid': str(uuid.uuid4()),
                         'cell_name': 'global!cell0'}
        self.mox.StubOutWithMock(rax_near_far.db,
                                 'instance_get_by_uuid')
        rax_near_far.db.instance_get_by_uuid(self.context,
                self.instance['uuid']).AndReturn(self.instance)

    def test_near_filter(self):
        self.scheduler.msg_runner = self.mox.CreateMockAnything()
        self.mox.StubOutWithMock(self.scheduler.msg_runner,
                                 'schedule_run_instance')
        self.scheduler.msg_runner.schedule_run_instance(self.context,
                self.instance['cell_name'],
                self.filter_props['host_sched_kwargs'])

        self.mox.ReplayAll()

        self.filter_props['scheduler_hints'] = {'near': self.instance['uuid']}
        # Force copy because filter_all can/will modify it
        cells = list(self.cells)
        result = self.filter.filter_all(cells, self.filter_props)
        # We expect it will call schedule_run_instance and return back None
        self.assertIsNone(result)

    def test_far_filter(self):
        self.mox.ReplayAll()

        self.filter_props['scheduler_hints'] = {'far': self.instance['uuid']}
        # Force copy because filter_all can/will modify it
        cells = list(self.cells)
        result = self.filter.filter_all(cells, self.filter_props)
        expected = [self.cells[1], self.cells[2]]
        self.assertEqual(expected, result)
