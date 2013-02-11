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

import sys

from nova.db.mysqldb import pool as db_pool

pool = db_pool.ConnPool()


class API(object):

    # TODO(belliott) mysql raw methods to be implemented here.

    def __getattr__(self, key):
        # forward unimplemented method to sqlalchemy backend:
        return getattr(sqlalchemy_api, key)


# NOTE(belliott) fancy hack borrowed from Guido:
# http://mail.python.org/pipermail/python-ideas/2012-May/014969.html
sys.modules[__name__] = API()

from nova.db.sqlalchemy import api as sqlalchemy_api
