#   Copyright 2013 Rackspace Hosting
#
#   Licensed under the Apache License, Version 2.0 (the "License"); you may
#   not use this file except in compliance with the License. You may obtain
#   a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#   WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#   License for the specific language governing permissions and limitations
#   under the License.

import webob

from nova.api.openstack.compute.contrib import migration_reset
from nova.compute import api as compute_api
from nova.compute import vm_states
from nova import exception
from nova import test
from nova.tests.api.openstack import fakes


class MigrationResetTests(test.TestCase):
    def setUp(self):
        super(MigrationResetTests, self).setUp()
        self.instance_id = "1234"
        self.instance = dict(id=1, uuid=self.instance_id,
                            vm_state=vm_states.ACTIVE,
                            locked=False)

        def fake_get(inst, context, instance_id):
            if(self.instance_id == instance_id):
                return self.instance
            raise exception.InstanceNotFound(instance_id=instance_id)

        self.stubs.Set(compute_api.API, 'get', fake_get)
        self.migration_reset_api = migration_reset.\
            MigrationResetController()

        url = '/fake/os-reset-migration-state/%s' % self.instance_id
        self.request = fakes.HTTPRequest.blank(url, use_admin_context=True)
        self.context = self.request.environ["nova.context"]

    def test_no_state(self):
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.migration_reset_api.reset_state,
                          self.request,
                          {"reset-state": {"server-id": self.instance_id}})

    def test_bad_state(self):
        body = {
                "reset-state": {
                    "state": "spam", "server-id": self.instance_id}
                }
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.migration_reset_api.reset_state,
                          self.request,
                          body)

    def test_bad_server_id(self):
        body = {
                "reset-state": {
                    "state": "finished", "server-id": "inst_id"}
                }
        self.assertRaises(webob.exc.HTTPNotFound,
                          self.migration_reset_api.reset_state,
                          self.request,
                          body)

    def test_no_server_id(self):
        self.assertRaises(webob.exc.HTTPBadRequest,
                          self.migration_reset_api.reset_state,
                          self.request,
                          {"reset-state": {"state": "finished"}})

    def test_reset_finished(self):
        self.mox.StubOutWithMock(self.migration_reset_api.compute_api,
                                 'update_migration')
        self.migration_reset_api.compute_api.update_migration(
                                                    self.context,
                                                    self.instance,
                                                    {"status": "finished"})

        self.mox.ReplayAll()
        body = {
                "reset-state": {
                    "state": "finished", "server-id": self.instance_id}
                }

        result = self.migration_reset_api.reset_state(self.request,
                                                            body)
        self.assertEqual(result.status_int, 202)

    def test_reset_error(self):
        self.mox.StubOutWithMock(self.migration_reset_api.compute_api,
                                 'update_migration')
        self.migration_reset_api.compute_api.update_migration(
                                                    self.context,
                                                    self.instance,
                                                    {"status": "error"})
        self.mox.ReplayAll()
        body = {
                "reset-state": {
                    "state": "error", "server-id": self.instance_id}
                }
        result = self.migration_reset_api.reset_state(self.request,
                                                            body)
        self.assertEqual(result.status_int, 202)
