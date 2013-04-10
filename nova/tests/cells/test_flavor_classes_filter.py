# Copyright (c) 2013 Rackspace Hosting
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
Unit tests for cell flavor_classes filter.
"""

from nova.cells.filters import flavor_classes
from nova.cells import state as cells_state
from nova import test

CELL_INFO = [('cell1', {}),
             ('cell2', {'flavor_classes': []}),
             ('cell3', {'flavor_classes': ['class1', 'class2']}),
             ('cell4', {'flavor_classes': ['class2', 'class3']})]


class CellsFlavorClassesFilterTest(test.TestCase):
    """Test that we can filter target cells by their flavor restrictions."""

    def setUp(self):
        super(CellsFlavorClassesFilterTest, self).setUp()
        self.ffilter = flavor_classes.CellsFlavorClassFilter()
        self.flags(capabilities=[], group='cells')
        self.cells = []
        for name, capabs in CELL_INFO:
            cell = cells_state.CellState(name)
            cell.update_capabilities(capabs)
            self.cells.append(cell)

    def _set_flavor_class(self, flavor_class):
        if flavor_class is None:
            extra_specs = {}
        else:
            extra_specs = {'class': flavor_class}
        instance_type = {'extra_specs': extra_specs}
        self.filter_props = {'request_spec': {'instance_type': instance_type}}

    def test_requested_class_of_none(self):
        self._set_flavor_class(None)
        result = self.ffilter.filter_all(self.cells, self.filter_props)
        # Should match all cells no matter what for transition period.
        self.assertEqual(self.cells, result)

    def test_requested_unknown_class(self):
        self._set_flavor_class('unknown')
        result = self.ffilter.filter_all(self.cells, self.filter_props)
        # Should only match cells with no 'flavor_classes' set
        self.assertEqual(self.cells[:1], result)

    def test_requested_matching_class_one_cell(self):
        self._set_flavor_class('class1')
        result = self.ffilter.filter_all(self.cells, self.filter_props)
        # The 2nd and the last one should be dropped.
        expected = [self.cells[0], self.cells[2]]
        self.assertEqual(expected, result)

    def test_requested_matching_class_two_cells(self):
        self._set_flavor_class('class2')
        result = self.ffilter.filter_all(self.cells, self.filter_props)
        # The 2nd should be dropped
        expected = [self.cells[0]] + self.cells[2:]
        self.assertEqual(expected, result)
