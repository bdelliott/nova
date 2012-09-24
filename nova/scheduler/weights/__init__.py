# Copyright (c) 2011 OpenStack Foundation
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
Scheduler host weights
"""

from oslo.config import cfg

from nova import weights

CONF = cfg.CONF


class WeighedHost(weights.WeighedObject):
    def to_dict(self):
        x = dict(weight=self.weight)
        x['host'] = self.obj.host
        return x

    def __repr__(self):
        return "WeighedHost [host: %s, weight: %s]" % (
                self.obj.host, self.weight)


class BaseHostWeigher(weights.BaseWeigher):
    """Base class for host weights."""
    pass


class HostWeightHandler(weights.BaseWeightHandler):
    object_class = WeighedHost

    def __init__(self):
        super(HostWeightHandler, self).__init__(BaseHostWeigher)


class RAXHostWeightHandler(weights.BaseWeightHandler):
    object_class = WeighedHost

    def get_weighed_objects(self, weigher_classes, obj_list,
            weighing_properties):
        """Return a sorted (highest score first) list of WeighedObjects."""

        if not obj_list:
            return []

        weighed_objs = [self.object_class(obj, 0.0) for obj in obj_list]
        for weigher_cls in weigher_classes:
            weigher = weigher_cls()
            weigher.weigh_objects(weighed_objs, weighing_properties)

        return sorted(weighed_objs, key=lambda x: x.weight, reverse=True)

    def __init__(self):
        super(RAXHostWeightHandler, self).__init__(BaseHostWeigher)


def all_weighers():
    """Return a list of weight plugin classes found in this directory."""
    return RAXHostWeightHandler().get_all_classes()
