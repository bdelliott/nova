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
import datetime

from nova.db.mysqldb import connection
from nova.db.sqlalchemy import api as sqlalchemy_api
from nova import exception

_CONN_POOL = connection.ConnectionPool()

is_user_context = sqlalchemy_api.is_user_context

def require_context(f):
    def wrapper(*args, **kwargs):
        context = args[1]
        if not context.is_admin and not is_user_context(context):
            raise exception.NotAuthorized()
        return f(*args, **kwargs)
    wrapper.__name__ = f.__name__
    return wrapper


class API(object):
    # TODO(belliott) mysql raw methods to be implemented here.

    def __getattr__(self, key):
        # forward unimplemented method to sqlalchemy backend:
        return getattr(sqlalchemy_api, key)

    @require_context
    def bw_usage_update(self, context, uuid, mac, start_period, bw_in, bw_out,
                        last_ctr_in, last_ctr_out, last_refreshed=None):
        # kick this shit raw sql style:
        with _CONN_POOL.get() as conn:
            def _datestr(dt):
                return dt.strftime('%Y-%m-%d %H:%M:%S')
    
            sql = """UPDATE bw_usage_cache SET bw_in=%s, bw_out=%s, last_ctr_in=%s, last_ctr_out=%s
                     WHERE bw_usage_cache.start_period = %s AND
                        bw_usage_cache.uuid = %s AND bw_usage_cache.mac = %s"""
    
            args = (bw_in, bw_out, last_ctr_in, last_ctr_out, _datestr(start_period), uuid, mac)
            num_rows_affected = conn.execute(sql, args)
            if num_rows_affected > 0:
                return
        # Start a new transaction
        with _CONN_POOL.get() as conn:
            sql = """INSERT INTO bw_usage_cache
                     (created_at, updated_at, deleted_at, deleted, uuid, mac,
                      start_period, last_refreshed, bw_in, bw_out, last_ctr_in, last_ctr_out) VALUES
                     (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

            args = (_datestr(datetime.datetime.utcnow()), None, None, 0, uuid, mac,
                    _datestr(start_period), None, bw_in, bw_out, last_ctr_in,
                    last_ctr_out)
            conn.execute(sql, args)
