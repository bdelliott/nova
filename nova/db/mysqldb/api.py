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

from MySQLdb import cursors

from nova.db import decorators
from nova.db.mysqldb import pool as db_pool
from nova.db.sqlalchemy import api as sqlalchemy_api
from nova import exception
from nova.openstack.common import uuidutils

pool = db_pool.ConnPool()


class API(object):

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
        conn = pool.get()
        cursor = conn.cursor(cursorclass=cursors.DictCursor)

        try:
            if not uuidutils.is_uuid_like(instance_uuid):
                raise exception.InvalidUUID(instance_uuid)

            instance_ref = self._instance_get_by_uuid(context, instance_uuid,
                                                      cursor)            
            # TODO do the actual updating, hah!
            raise Exception("TODO updating")
            cursor.close()
            conn.commit()
        except Exception:
            cursor.close()
            conn.rollback()
            raise

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
