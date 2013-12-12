# Copyright (c) 2013 Hewlett-Packard Development Company, L.P.
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

from nova import loadables
from nova.openstack.common import log as logging

LOG = logging.getLogger(__name__)

class BaseConsumer(object):
    """Base class for all consumer classes"""

    def consume_from_instance(self, host_state, instance, instance_type):
        """Consume resources according to host requirements"""
        pass

class BaseConsumerHandler(loadables.BaseLoader):
    """Base class to handle loading consumer classes"""

    def consume_from_instance(self, consumer_classes,
                              host_state, instance, instance_type):
        """Each class is called to update host state to reflect
        the effect of allocating this instance to this host"""
        for consumer_cls in consumer_classes:
            consumer = consumer_cls()
            consumer.consumer_from_instance(host_state, instance, instance_type)