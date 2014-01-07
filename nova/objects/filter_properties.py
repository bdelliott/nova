#    Copyright 2014 Rackspace Hosting.
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


from nova.objects import base
from nova.objects import fields


class FilterProperties(base.NovaObject):

    VERSION = '1.0'

    fields = {
        'scheduler_hints': fields.DictOfStringsField(nullable=True),
        'force_hosts': fields.ListOfStringsField(nullable=True),
        'force_nodes': fields.ListOfStringsField(nullable=True),
        'instance_type': fields.ObjectField('Flavor'),
    }

    def __init__(self, scheduler_hints, forced_host, forced_node,
                 instance_type):
        super(FilterProperties, self).__init__()

        self.scheduler_hints = scheduler_hints
        self.instance_type = instance_type

        if forced_host:
            self.force_hosts = [forced_host]

        if forced_node:
            self.force_nodes = [forced_node]

        self.obj_reset_changes()
