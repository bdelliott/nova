# vim: tabstop=4 shiftwidth=4 softtabstop=4

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
MySQLdb DB API implementation.

This will fall back to sqlalchemy for methods that are not yet implemented
here.
"""

from nova.db.mysqldb import connection
from nova.db.sqlalchemy import api as sqlalchemy_api

_CONN_POOL = connection.ConnectionPool()


class API(object):
    # TODO(belliott) mysql raw methods to be implemented here.

    def __getattr__(self, key):
        # forward unimplemented method to sqlalchemy backend:
        return getattr(sqlalchemy_api, key)
