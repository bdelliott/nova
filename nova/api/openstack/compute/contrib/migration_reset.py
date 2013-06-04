# Copyright 2013 Rackspace Hosting
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

import webob
from webob import exc

from nova.api.openstack import extensions
from nova import compute
from nova import exception
from nova.openstack.common.gettextutils import _

XMLNS = "http://docs.openstack.org/compute/ext/migration-reset/api/v2.0"
ALIAS = "os-migration-reset"


authorize = extensions.extension_authorizer('compute', 'migration_reset')

state_map = dict(finished='finished', error='error')


class MigrationResetController(object):
    """Controller for resetting migration state."""
    def __init__(self):
        self.compute_api = compute.API()

    def reset_state(self, req, body):
        """Permit admins to reset the state of a migration."""
        context = req.environ["nova.context"]
        authorize(context)

        try:
            # Identify the desired state from the body
            state = state_map[body["reset-state"]["state"]]
            instance_id = body["reset-state"]["server-id"]
        except (TypeError, KeyError):
            msg = _("Server id and the desired state must be specified. Valid "
                    "states are: %s") % ', '.join(sorted(state_map.keys()))
            raise exc.HTTPBadRequest(explanation=msg)

        try:
            instance = self.compute_api.get(context, instance_id)
        except exception.InstanceNotFound:
            raise exc.HTTPNotFound(_("Server not found"))

        self.compute_api.update_migration(context, instance,
                                          {"status": state})

        return webob.Response(status_int=202)


class Migration_reset(extensions.ExtensionDescriptor):
    """Ability to reset the state of migrations."""

    name = "MigrationReset"
    alias = ALIAS
    namespace = XMLNS
    updated = "2013-06-13T00:00:00Z"

    def get_resources(self):
        resource = extensions.ResourceExtension('os-migration-reset',
                                                MigrationResetController(),
                                                collection_actions={
                                                    'reset_state': 'POST'
                                                 }
        )
        return [resource]
