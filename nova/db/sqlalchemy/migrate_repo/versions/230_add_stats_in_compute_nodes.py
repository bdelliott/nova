# Copyright (c) 2014 Rackspace Hosting
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


from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Index
from sqlalchemy import Integer
from sqlalchemy import MetaData
from sqlalchemy import String
from sqlalchemy import Table
from sqlalchemy import Text

from nova.openstack.common import timeutils


def upgrade(engine):
    meta = MetaData()
    meta.bind = engine

    # Drop the compute_node_stats table and add a 'stats' column to
    # compute_nodes directly.  The data itself is transient and doesn't
    # need to be copied over.
    table_names = ('compute_node_stats', 'shadow_compute_node_stats')
    for table_name in table_names:
        table = Table(table_name, meta, autoload=True)
        table.drop()

    # Add a new stats column to compute nodes
    table_names = ('compute_nodes', 'shadow_compute_nodes')
    for table_name in table_names:
        table = Table(table_name, meta, autoload=True)
        stats = Column('stats', Text, nullable=True)
        table.create_column(stats)


def downgrade(engine):
    meta = MetaData()
    meta.bind = engine

    table_names = ('compute_nodes', 'shadow_compute_nodes')
    for table_name in table_names:
        table = Table(table_name, meta, autoload=True)
        table.drop_column('stats')

    table_names = ('compute_node_stats', 'shadow_compute_node_stats')
    for table_name in table_names:
        table = Table(table_name, meta,
                Column('created_at', DateTime, default=timeutils.utcnow),
                Column('updated_at', DateTime, onupdate=timeutils.utcnow),
                Column('deleted_at', DateTime),
                Column('deleted', Integer, default=0),
                Column('id', Integer, primary_key=True),
                Column('key', String(255), nullable=False),
                Column('value', String(255), nullable=False),
                Column('compute_node_id', Integer, ForeignKey('compute_nodes.id'),
                       nullable=False, index=True),
                Index('compute_node_stats_node_id_and_deleted_idx', 'compute_node_id',
                      'deleted')
        )
        table.create()
