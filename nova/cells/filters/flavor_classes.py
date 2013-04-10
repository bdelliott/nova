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
Flavor classes filter.

Flavor classes are defined by setting the 'class' key on a flavor's
extra_specs (instance_type['extra_specs']['class']).

Cells can announce that they only support certain flavor classes by setting
the 'capabilities' nova.conf option under the [cells] config section.  The
value of this option should be 'flavor_classes=name1;name2;name3' to
advertise that they support flavor classes 'name1', 'name2', and 'name3'.

Imagine this configuration:

flavor #1 extra_specs['class'] = 'highio'
flavor #2 extra_specs['class'] = 'standard'

Cell #1 nova.conf:

------- 8< -------
[cells]
enable=true
name=cell1  # something unique per child cell
capabilities=flavor_classes=highio;some_other_class,some_other_cap=abc
------- 8< -------

Cell #2 nova.conf:

------- 8< -------
[cells]
enable=true
name=cell1  # something unique per child cell
capabilities=flavor_classes=standard;some_other_class,some_other_cap=abc
------- 8< -------

###
Note the capabilities syntax:
 * '=' to match each key=val pair in a single capability
 * ','  to separate capabilities
 * ';' to separate the list of capability values
###

With this filter, building flavor #1 will go to cell1.  Flavor #2 will go
to cell2.
"""

from nova.cells import filters
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)


class CellsFlavorClassFilter(filters.BaseCellFilter):
    def filter_all(self, cells, filter_properties):
        """Filters out cells that don't advertise support for the requested
        flavor class.

         * A requested flavor that has no configured class can be built in
           any cell.
         * Cells that do not advertise any flavor classes will not be filtered
           out

        This allows us to stage config changes separately for cells and for
        flavors without having to worry about the order they get changed.
        """
        instance_type = filter_properties['request_spec']['instance_type']
        requested_class = instance_type['extra_specs'].get('class')
        if requested_class is None:
            # If we've not configured any class for the instance type,
            # allow it to go to any cell.
            return cells
        result = []
        for cell in cells:
            supported_flavor_classes = cell.capabilities.get(
                    'flavor_classes')
            # If a cell has no flavor_classes configured, assume that
            # any instance_type can be scheduled here.
            if supported_flavor_classes is None:
                result.append(cell)
            elif requested_class in supported_flavor_classes:
                result.append(cell)
        return result
