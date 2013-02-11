# vim: tabstop=4 shiftwidth=4 softtabstop=4


# Copyright (c) 2013 OpenStack, LLC.
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

"""MySQL conn pool"""


import MySQLdb
from MySQLdb.constants import CLIENT as mysql_client_constants
MySQLdb.threadsafety = 1
import sqlalchemy

from nova.openstack.common import cfg

CONF = cfg.CONF


class ConnPool(object):
    def __init__(self):
        self.conns_available = []
        self.num_conns = 0
        self.max_conns = 50

    def _create_conn(self):
        sql_connection = CONF.sql_connection
        connection_dict = sqlalchemy.engine.url.make_url(sql_connection)
        password = connection_dict.password or ''
        conn_args = {
            'db': connection_dict.database,
            'passwd': password,
            'host': connection_dict.host,
            'user': connection_dict.username,
            'client_flag': mysql_client_constants.FOUND_ROWS}

        print "connecting"
        conn = MySQLdb.connect(**conn_args)
        print "done connecting"
        self.num_conns += 1
        return conn

    def get(self):
        try:
            return self.conns_available.pop()
        except IndexError:
            pass
        if self.num_conns < self.max_conns:
            return self._create_conn()
        assert False

    def put(self, conn):
        self.conns_available.append(conn)
