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

from nova.db import decorators
from nova.db.mysqldb import connection
from nova.db.sqlalchemy import api as sqlalchemy_api
from nova import exception
from nova.openstack.common import uuidutils

is_user_context = sqlalchemy_api.is_user_context


class API(object):

    def __init__(self):
        self.pool = connection.ConnectionPool()

    def _instance_get_by_uuid(self, context, uuid, cursor):

        # TODO full impl of the read_deleted feature
        read_deleted = context.read_deleted == 'yes'

        # TODO project_only

        # TODO security_group_rules join
        sql = """SELECT * from instances
            LEFT OUTER JOIN instance_info_caches on
                instance_info_caches.instance_uuid = instances.uuid
            LEFT OUTER JOIN instance_metadata on
                instance_metadata.instance_uuid = %(uuid)s and
                instance_metadata.deleted = %(deleted)s
            LEFT OUTER JOIN instance_system_metadata on
                instance_system_metadata.instance_uuid = %(uuid)s and
                instance_system_metadata.deleted = %(deleted)s
            LEFT OUTER JOIN instance_types on
                instances.instance_type_id = instance_types.id
            WHERE instances.uuid = %(uuid)s
              AND instances.deleted = %(deleted)s"""


        args = {'uuid': uuid,
                'deleted': read_deleted}
        cursor.execute(sql, args)

        row = cursor.fetchone()

        if not row:
            raise exception.InstanceNotFound(instance_id=uuid)

        return self._make_sqlalchemy_like_dict(row)

    def _instance_update(self, context, instance_uuid, values,
                         copy_old_instance=False):
        with self.pool.get() as conn:
            cursor = conn.cursor()

            if not uuidutils.is_uuid_like(instance_uuid):
                raise exception.InvalidUUID(instance_uuid)

            instance_ref = self._instance_get_by_uuid(context, instance_uuid,
                                                      cursor)            
            # TODO do the actual updating, hah!
            raise Exception("TODO updating")

    def _make_sqlalchemy_like_dict(self, row):
        """Make a SQLAlchemy-like dictionary, where each join gets namespaced as
        dictionary within the top-level dictionary.
        """
        result = {}
        for key, value in row.iteritems():
            # find keys like join_table_name.column and dump them into a
            # sub-dict
            tok = key.split(".")
            if len(tok) == 2:
                tbl, col = tok
                join_dict = result.setdefault(tbl, {})
                join_dict[col] = value
            else:
                result[key] = value
            
        self._pretty_print_result(result)
        return result

    def _pretty_print_result(self, result):
        import pprint
        pprint.pprint(result, indent=4)

    @decorators.require_context
    def instance_update(self, context, instance_uuid, values):
        instance_ref = self._instance_update(context, instance_uuid, values)[1]
        return instance_ref

    def __getattr__(self, key):
        # forward unimplemented method to sqlalchemy backend:
        return getattr(sqlalchemy_api, key)

    @decorators.require_context
    def bw_usage_update(self, context, uuid, mac, start_period, bw_in, bw_out,
                        last_ctr_in, last_ctr_out, last_refreshed=None):
        # kick this shit raw sql style:
        with self.pool.get() as conn:
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
        with self.pool.get() as conn:
            sql = """INSERT INTO bw_usage_cache
                     (created_at, updated_at, deleted_at, deleted, uuid, mac,
                      start_period, last_refreshed, bw_in, bw_out, last_ctr_in, last_ctr_out) VALUES
                     (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"""

            args = (_datestr(datetime.datetime.utcnow()), None, None, 0, uuid, mac,
                    _datestr(start_period), None, bw_in, bw_out, last_ctr_in,
                    last_ctr_out)
            conn.execute(sql, args)
