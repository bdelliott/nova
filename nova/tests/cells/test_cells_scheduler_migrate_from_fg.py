# Copyright (c) 2014 Rackspace Hosting
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

from nova.cells.filters import target_cell
from nova.cells import messaging
from nova.cells import state
from nova import context
from nova import exception
from nova.scheduler import utils as scheduler_utils
from nova import test
from nova.tests.cells import fakes


class CellsSchedulerTestCase(test.TestCase):
    """Test case for CellsScheduler class migrate_from_fg method."""

    def setUp(self):
        super(CellsSchedulerTestCase, self).setUp()
        self.flags(scheduler_filter_classes=[], scheduler_weight_classes=[],
                   group='cells')
        self._init_cells_scheduler()

    def _init_cells_scheduler(self):
        fakes.init(self)
        self.msg_runner = fakes.get_message_runner('api-cell')
        self.scheduler = self.msg_runner.scheduler
        self.state_manager = self.msg_runner.state_manager
        self.my_cell_state = self.state_manager.get_my_state()
        self.ctxt = context.RequestContext('fake', 'fake')
        self.instance = {
            'uuid': 1,
            'cell_name': 'api-cell!child-cell1',
            'info_cache': {},
            'name': '',
            'id': '',
            'security_groups': ''}
        self.kwargs = {
            'instance': self.instance,
            'image': 'fake_image',
            'flavor': 'fake_flavor'}
        self.filter_properties = {
            'context': self.ctxt,
            'scheduler': self.scheduler,
            'routing_path': 'api-cell!child-cell1',
            'host_sched_kwargs': self.kwargs,
            'cell_scheduler_method': 'migrate_from_fg',
            'scheduler_hints': {
                'target_cell': 'api-cell!child-cell1'},
            'request_spec': {
                'image': 'fake_image',
                'instance_uuids': [1]}}

    def test_migrate_from_fg_should_build_an_instance_here(self):
        cell = self.state_manager.get_my_state()

        self.mox.StubOutWithMock(scheduler_utils, 'build_request_spec')
        self.filter_properties['routing_path'] = 'api-cell'
        scheduler_utils.build_request_spec(self.ctxt, 'fake_image',
                                           [self.instance],
                                           'fake_flavor') \
            .AndReturn({'image': 'fake_image', 'instance_uuids': [1]})

        self.mox.StubOutWithMock(self.scheduler, '_grab_target_cells')
        self.scheduler._grab_target_cells(self.filter_properties). \
            AndReturn([cell])
        self.mox.StubOutWithMock(self.scheduler.compute_api,
                                 'migrate_from_fg')
        self.scheduler.compute_api.migrate_from_fg(self.ctxt, self.instance,
                                                   'fake_image',
                                                   'fake_flavor'). \
            AndReturn((self.instance, '1.2.3.4'))

        self.mox.ReplayAll()

        res = self.msg_runner.migrate_from_fg(self.ctxt,
                                              self.my_cell_state,
                                              self.instance,
                                              'fake_image',
                                              'fake_flavor')
        self.assertEqual('1.2.3.4', res.value)

    def test_migrate_from_fg_schedules_on_child_cell(self):
        fake_response = messaging.Response('fake', "1.2.3.4", False)

        class FakeMessage(object):
            pass

        message = FakeMessage()
        message.ctxt = self.ctxt
        message.routing_path = 'api-cell!child-cell1'

        child_cell = self.state_manager.get_child_cells()[0]

        self.mox.StubOutWithMock(scheduler_utils, 'build_request_spec')
        scheduler_utils.build_request_spec(self.ctxt, 'fake_image',
                                           [self.instance],
                                           'fake_flavor') \
            .AndReturn({'image': 'fake_image', 'instance_uuids': [1]})

        self.mox.StubOutWithMock(self.scheduler, '_grab_target_cells')
        self.scheduler._grab_target_cells(self.filter_properties).AndReturn(
            [child_cell])

        self.mox.StubOutWithMock(self.msg_runner, 'migrate_from_fg')
        self.msg_runner.migrate_from_fg(self.ctxt, child_cell, self.instance,
                                        'fake_image', 'fake_flavor') \
            .AndReturn(fake_response)
        self.mox.ReplayAll()

        self.scheduler.migrate_from_fg(message, self.kwargs)

    def test_migrate_from_fg_throws_exception_when_cells_not_found(self):
        self.mox.StubOutWithMock(scheduler_utils, 'build_request_spec')
        self.filter_properties['routing_path'] = 'api-cell'
        scheduler_utils.build_request_spec(self.ctxt, 'fake_image',
                                           [self.instance],
                                           'fake_flavor') \
            .AndReturn({'image': 'fake_image', 'instance_uuids': [1]})

        self.mox.StubOutWithMock(self.scheduler, '_grab_target_cells')
        self.scheduler._grab_target_cells(self.filter_properties). \
            AndRaise(exception.NoCellsAvailable())

        self.mox.ReplayAll()

        response = self.msg_runner.migrate_from_fg(self.ctxt,
                                                   self.my_cell_state,
                                                   self.instance,
                                                   'fake_image', 'fake_flavor')
        self.assertEqual(True, response.failure)


class TargetCellMigrateFromFgTestCase(test.TestCase):
    """Test case for TargetCell Migrate from FG scenarios."""

    def setUp(self):
        super(TargetCellMigrateFromFgTestCase, self).setUp()
        fakes.init(self)
        self.msg_runner = fakes.get_message_runner('api-cell')
        self.scheduler = self.msg_runner.scheduler
        self.ctxt = context.RequestContext('fake', 'fake')
        self.parent = state.CellState('api-cell', True)
        self.child_cell1 = state.CellState('child-cell1')
        self.child_cell2 = state.CellState('child-cell2')
        self.child_cell3 = state.CellState('child-cell3')
        self.cells = [self.parent, self.child_cell1, self.child_cell2,
                      self.child_cell3]
        self.target_cell = target_cell.TargetCellFilter()

    def test_filter_all_should_return_the_matching_child_cell(self):
        filter_properties = {
            'context': self.ctxt,
            'scheduler': self.scheduler,
            'routing_path': 'parent!child-cell2',
            'cell_scheduler_method': 'migrate_from_fg',
            'scheduler_hints': {
                'target_cell': 'child-cell2'}
        }

        self.mox.StubOutWithMock(self.target_cell, 'authorized')
        self.target_cell.authorized(self.ctxt).AndReturn(True)
        self.mox.ReplayAll()

        cells = self.target_cell.filter_all(self.cells, filter_properties)

        self.assertEqual(cells[0], self.child_cell2)

    def test_filter_all_should_return_empty_list_if_no_cells_match(self):
        filter_properties = {
            'context': self.ctxt,
            'scheduler': self.scheduler,
            'routing_path': 'parent!child-cell2',
            'cell_scheduler_method': 'migrate_from_fg',
            'scheduler_hints': {
                'target_cell': 'child-cell4'}
        }

        self.mox.StubOutWithMock(self.target_cell, 'authorized')
        self.target_cell.authorized(self.ctxt).AndReturn(True)
        self.mox.ReplayAll()

        cells = self.target_cell.filter_all(self.cells, filter_properties)

        self.assertEqual(0, len(cells))
