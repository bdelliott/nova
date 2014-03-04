# Copyright (c) 2014 Rackspace Hosting
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
import mox

from nova.compute import api as compute_api
from nova.compute import cells_api
from nova.compute import power_state
from nova.compute import task_states
from nova.compute import vm_states
from nova import context
from nova import db
from nova import exception
from nova import notifications
from nova.objects import block_device
from nova.objects import instance as instance_obj
from nova.objects import instance_action
from nova.openstack.common import uuidutils
from nova import quota
from nova.tests import fake_instance
from test_compute import BaseTestCase


class FgMigrationsComputeApiTest(BaseTestCase):
    def setUp(self):
        super(FgMigrationsComputeApiTest, self).setUp()
        self.compute_api = compute_api.API()
        self.compute_task_api = self.compute_api.compute_task_api
        self.ctxt = context.get_admin_context()
        self.instance_type = {}
        self.image = {
            'image_ref': 'c3153cde-2d23-4186-b7da-159adbe2858b',
            'properties': {
                'auto_disk_config': 'False'
            }
        }
        self.reservations = 'quota_reservation'

        self.context.is_admin = True
        self.instance = fake_instance. \
            fake_instance_obj(self.context,
                              project_id='project_id',
                              user_id='user_id',
                              vm_state=vm_states.BUILDING,
                              task_state=task_states.SCHEDULING)

        def _check_requested_image(context, image_id, image, flavor):
            return

        def _migrate_from_fg(context, instance, image, instance_type):
            return "1.2.3.4"

        def _check_and_transform_bdm(base_options, instance_type, image_meta,
                                     min_count, max_count,
                                     block_device_mapping, legacy_bdm):
            pass

        def _validate_bdm(context, instance, instance_type, all_mappings):
            pass

        def _update_block_device_mapping(elevated_context, instance_type,
                                         instance_uuid, block_device_mapping):
            pass

        def _populate_security_groups(instance, security_groups):
            pass

        def _ensure_default(context):
            self.assertEqual(self.base_options['user_id'], context.user_id)
            self.assertEqual(self.base_options['project_id'],
                             context.project_id)

        def _check_num_instances_quota(context, instance_type, min_count,
                                       max_count):
            self.assertEqual(self.base_options['user_id'], context.user_id)
            self.assertEqual(self.base_options['project_id'],
                             context.project_id)
            self.assertEqual(self.instance_type, instance_type)
            self.assertEqual(min_count, 1)
            self.assertEqual(max_count, 1)
            return (1, self.reservations)

        def _commit(context, quota_reservation, project_id=None, user_id=None):
            self.assertEqual(self.base_options['user_id'], context.user_id)
            self.assertEqual(self.base_options['project_id'],
                             context.project_id)
            self.assertEqual(self.reservations, quota_reservation)

        def _create_reservations(context, instance, instance_type_id,
                                 project_id, user_id):
            return 'reservations'

        self.stubs.Set(self.compute_api, '_create_reservations',
                       _create_reservations)

        self.stubs.Set(self.compute_api, '_check_num_instances_quota',
                       _check_num_instances_quota)

        self.stubs.Set(quota.QUOTAS, 'commit', _commit)

        self.stubs.Set(self.compute_api.security_group_api,
                       'populate_security_groups', _populate_security_groups)

        self.stubs.Set(self.compute_api.security_group_api,
                       'ensure_default', _ensure_default)

        self.stubs.Set(self.compute_api, '_check_and_transform_bdm',
                       _check_and_transform_bdm)

        self.stubs.Set(self.compute_api, '_validate_bdm', _validate_bdm)

        self.stubs.Set(self.compute_api, '_update_block_device_mapping',
                       _update_block_device_mapping)

        self.stubs.Set(self.compute_task_api, 'migrate_from_fg',
                       _migrate_from_fg)

        self.stubs.Set(self.compute_api, '_check_requested_image',
                       _check_requested_image)

        self.base_options = {
            'image_ref': 'c3153cde-2d23-4186-b7da-159adbe2858b',
            'power_state': power_state.NOSTATE,
            'vm_state': vm_states.BUILDING,
            'user_id': '98765',
            'project_id': '1234567',
            'instance_type_id': 2,
            'memory_mb': 1024,
            'vcpus': 2,
            'root_gb': 20,
            'ephemeral_gb': 10,
            'display_name': 'test1',
            'display_description': 'test1',
            'metadata': {'foo': 'bar'},
            'access_ip_v4': '111.111.111.111',
            'root_device_name': '/dev/xda',
            'progress': 0,
            'os_type': 'linux',
            'architecture': 'x64',
            'vm_mode': 'xen',
            'hostname': 'test1',
            'cell_name': 'parent!child',
            'auto_disk_config': 0,
            'system_metadata': {
                'instance_type_memory_mb': 1024,
                'instance_type_swap': 10,
                'instance_type_vcpu_weight': 1,
                'instance_type_root_gb': 20,
                'instance_type_id': 2,
                'instance_type_name': 'standard1',
                'instance_type_ephemeral_gb': 10,
                'instance_type_rxtx_factor': 1.1,
                'image_architecture': 'x64',
                'image_vm_mode': 'xen',
                'instance_type_flavorid': 'ST1',
                'instance_type_vcpus': 2,
                'image_min_disk': 20,
                'image_root_device_name': '/dev/xda',
                'image_os_type': 'linux',
                'image_base_image_ref': 'c3153cde-2d23-4186-b7da-159adbe2858b'
            }
        }

    def test_migrate_from_fg(self):
        self.mox.StubOutWithMock(self.compute_task_api, 'migrate_from_fg')
        self.compute_task_api.migrate_from_fg(self.ctxt, mox.IsA(
            instance_obj.Instance), self.image, self.instance_type)
        self.mox.ReplayAll()

        (instance, host_ip) = self.compute_api.migrate_from_fg(self.ctxt,
                                                            self.base_options,
                                                            self.image,
                                                            self.instance_type)

        for key, value in self.base_options.iteritems():
            if key != 'access_ip_v4':
                self.assertEqual(value, instance[key])

        self.assertEqual(self.base_options['access_ip_v4'],
                         str(instance['access_ip_v4']))

        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_derives_auto_disk_config_from_image(self):
        self.image['properties']['auto_disk_config'] = 'True'

        (instance, host_ip) = self.compute_api.migrate_from_fg(self.ctxt,
                                                            self.base_options,
                                                            self.image,
                                                            self.instance_type)

        self.assertEqual(1, instance.auto_disk_config)
        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_should_send_update_with_states_notification(self):
        self.mox.StubOutWithMock(notifications, 'send_update_with_states')
        notifications.send_update_with_states(self.ctxt,
                                              mox.IsA(instance_obj.Instance),
                                              None,
                                              vm_states.BUILDING, None, None,
                                              service="api")
        self.mox.ReplayAll()

        (instance, host_ip) = self.compute_api.migrate_from_fg(self.ctxt,
                                                            self.base_options,
                                                            self.image,
                                                            self.instance_type)
        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_should_update_quotas(self):
        self.mox.StubOutWithMock(self.compute_api,
                                 '_check_num_instances_quota')
        self.compute_api._check_num_instances_quota(
            mox.IsA(context.RequestContext), self.instance_type, 1,
            1).AndReturn((1, self.reservations))

        self.mox.StubOutWithMock(quota.QUOTAS, 'commit')
        quota.QUOTAS.commit(mox.IsA(context.RequestContext), self.reservations)
        self.mox.ReplayAll()

        (instance, host_ip) = self.compute_api.migrate_from_fg(self.ctxt,
                                                            self.base_options,
                                                            self.image,
                                                            self.instance_type)
        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_should_rollback_quotas_in_case_of_exception(self):
        security_group_api = self.compute_api.security_group_api

        self.mox.StubOutWithMock(security_group_api, 'ensure_default')
        security_group_api.ensure_default(mox.IsA(context.RequestContext)) \
            .AndRaise(exception.SecurityGroupNotFound(dict(
            security_group_id=1)))

        self.mox.StubOutWithMock(quota.QUOTAS, 'rollback')
        quota.QUOTAS.rollback(mox.IsA(context.RequestContext),
                              self.reservations)
        self.mox.StubOutWithMock(instance_obj.Instance, 'refresh')
        instance_obj.Instance().refresh()

        self.mox.StubOutWithMock(instance_obj.Instance, 'destroy')
        instance_obj.Instance().destroy()

        self.mox.ReplayAll()

        self.assertRaises(exception.SecurityGroupNotFound,
                          self.compute_api.migrate_from_fg,
                          self.ctxt, self.base_options, self.image,
                          self.instance_type)

    def test_migrate_from_fg_should_create_instance_action(self):
        instance_uuid = 'c3153cde-2d23-4186-b7da-159adbe2858b'
        self.base_options['uuid'] = instance_uuid
        self.mox.StubOutWithMock(instance_action.InstanceAction,
                                 'action_start')
        instance_action.InstanceAction.action_start(self.ctxt,
                                                    instance_uuid,
                                                    'create',
                                                    want_result=False)
        self.mox.ReplayAll()

        (instance, host_ip) = self.compute_api.migrate_from_fg(self.ctxt,
                                                            self.base_options,
                                                            self.image,
                                                            self.instance_type)
        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_should_create_bdms(self):
        mappings = [{'guest_format': None, 'boot_index': 0, 'no_device': None,
                     'connection_info': None, 'snapshot_id': None,
                     'volume_size': None, 'device_name': None,
                     'disk_bus': None,
                     'image_id': u'bc43ba63-c198-44f7-a85d-88218422af69',
                     'source_type': 'image', 'device_type': 'disk',
                     'volume_id': None, 'destination_type': 'local',
                     'delete_on_termination': True}]
        self.mox.StubOutWithMock(self.compute_api, '_check_and_transform_bdm')
        self.compute_api._check_and_transform_bdm(self.base_options,
                                                  self.instance_type,
                                                  self.image, 1,
                                                  1, [], True). \
            AndReturn(mappings)

        called = {}

        def save_instance_uuid(ctxt, inst, inst_type, maps):
            called['instance_uuid'] = inst['uuid']

        self.mox.StubOutWithMock(self.compute_api, '_validate_bdm')
        self.compute_api._validate_bdm(self.ctxt,
                                       mox.IsA(instance_obj.Instance),
                                       self.instance_type,
                                       mappings). \
            WithSideEffects(save_instance_uuid)

        def compare_instance_uuid(ctxt, inst_type, inst_uuid, maps):
            self.assertEqual(called['instance_uuid'], inst_uuid)

        self.mox.StubOutWithMock(self.compute_api,
                                 '_update_block_device_mapping')
        self.compute_api. \
            _update_block_device_mapping(self.ctxt,
                                         self.instance_type,
                                         mox.Func(uuidutils.is_uuid_like),
                                         mappings). \
                 WithSideEffects(compare_instance_uuid)

        self.mox.ReplayAll()

        (instance, host_ip) = self.compute_api.migrate_from_fg(self.ctxt,
                                                            self.base_options,
                                                            self.image,
                                                            self.instance_type)

        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_should_not_generate_uuid_if_present(self):
        instance_uuid = 'c3153cde-2d23-4186-b7da-159adbe2858b'
        self.base_options['uuid'] = instance_uuid
        (instance, host_ip) = self.compute_api. \
            migrate_from_fg(self.ctxt,
                            self.base_options,
                            self.image,
                            self.instance_type)

        self.assertEqual(instance_uuid, instance['uuid'])
        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_should_validate_metadata(self):
        self.mox.StubOutWithMock(self.compute_api,
                                 '_check_metadata_properties_quota')
        self.compute_api._check_metadata_properties_quota(self.ctxt,
                                                          self.base_options[
                                                              'metadata'])
        self.mox.ReplayAll()

        (instance, host_ip) = \
            self.compute_api.migrate_from_fg(self.ctxt, self.base_options,
                                             self.image, self.instance_type)

        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_should_validate_requested_image(self):
        self.mox.StubOutWithMock(self.compute_api, '_check_requested_image')
        self.compute_api._check_requested_image(self.ctxt,
                                                self.base_options['image_ref'],
                                                self.image,
                                                self.instance_type)
        self.mox.ReplayAll()

        (instance, host_ip) = self.compute_api. \
            migrate_from_fg(self.ctxt, self.base_options, self.image,
                            self.instance_type)

        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_migrate_from_fg_should_create_default_security_group(self):
        security_group_api = self.compute_api.security_group_api
        self.mox.StubOutWithMock(security_group_api,
                                 'populate_security_groups')
        security_group_api.populate_security_groups(mox.IsA(
            instance_obj.Instance), ['default'])
        self.mox.ReplayAll()

        (instance, host_ip) = self.compute_api. \
            migrate_from_fg(self.ctxt, self.base_options, self.image,
                            self.instance_type)

        db.instance_destroy(self.ctxt, instance['uuid'])

    def test_revert_fg_migration_here(self):
        self.compute_api._cell_type = 'api'
        self.mox.StubOutWithMock(self.compute_api, '_create_reservations')
        self.compute_api._create_reservations(self.context, self.instance,
                                              self.instance.instance_type_id,
                                              self.instance.project_id,
                                              self.instance.user_id)\
            .AndReturn('reservations')
        self.mox.StubOutWithMock(self.compute_api.compute_rpcapi,
                                 'revert_fg_migration')
        self.compute_api.compute_rpcapi.revert_fg_migration(self.context,
                                                          self.instance)
        self.mox.StubOutWithMock(quota.QUOTAS, 'commit')
        quota.QUOTAS.commit(self.context, 'reservations',
                            project_id=self.instance.project_id,
                            user_id=self.instance.user_id)
        self.mox.ReplayAll()

        self.compute_api.revert_fg_migration(self.context, self.instance)

    def test_revert_fg_migration_on_child_cell(self):
        self.compute_api._cell_type = 'compute'
        self.mox.StubOutWithMock(self.instance, 'destroy')
        self.instance.destroy()
        bdm = block_device.BlockDeviceMapping()
        self.mox.StubOutWithMock(block_device.BlockDeviceMappingList,
                                 'get_by_instance_uuid')
        block_device.BlockDeviceMappingList. \
            get_by_instance_uuid(self.context, self.instance.uuid)\
            .AndReturn([bdm])
        self.mox.StubOutWithMock(bdm, 'destroy')
        bdm.destroy()
        self.mox.StubOutWithMock(quota.QUOTAS, 'commit')
        quota.QUOTAS.commit(self.context, 'reservations',
                            project_id=self.instance.project_id,
                            user_id=self.instance.user_id)
        self.mox.ReplayAll()

        self.compute_api.revert_fg_migration(self.context, self.instance)

    def test_revert_fg_migration_should_verify_instance_vm_state(self):
        self.instance.vm_state = vm_states.ACTIVE

        self.assertRaises(exception.InstanceInvalidState,
                          self.compute_api.revert_fg_migration, self.context,
                          self.instance)

    def test_revert_fg_migration_should_verify_instance_task_state(self):
        self.instance.task_state = None

        self.assertRaises(exception.InstanceInvalidState,
                          self.compute_api.revert_fg_migration, self.context,
                          self.instance)

    def test_revert_fg_migration_should_rollback_quota_on_error(self):
        self.compute_api._cell_type = 'api'
        self.mox.StubOutWithMock(self.compute_api.compute_rpcapi,
                                 'revert_fg_migration')
        self.compute_api.compute_rpcapi.revert_fg_migration(self.context,
                                                          self.instance)\
            .AndRaise(exception.InstanceNotReady(instance_id=123))
        self.mox.StubOutWithMock(quota.QUOTAS, 'rollback')
        quota.QUOTAS.rollback(self.context, 'reservations',
                              project_id=self.instance.project_id,
                              user_id=self.instance.user_id)
        self.mox.ReplayAll()

        self.assertRaises(exception.InstanceNotReady,
                          self.compute_api.revert_fg_migration,
                          self.context, self.instance)


class FgMigrationsCellsApiTest(FgMigrationsComputeApiTest):
    def setUp(self):
        super(FgMigrationsCellsApiTest, self).setUp()
        self.compute_api = cells_api.ComputeCellsAPI()
        self.compute_task_api = self.compute_api._compute_task_api

        def _check_requested_image(context, image_id, image, flavor):
            return

        def _migrate_from_fg(context, instance, image, instance_type):
            return "1.2.3.4"

        def _check_and_transform_bdm(base_options, instance_type, image_meta,
                                     min_count, max_count,
                                     block_device_mapping, legacy_bdm):
            pass

        def _validate_bdm(context, instance, instance_type, all_mappings):
            pass

        def _update_block_device_mapping(elevated_context, instance_type,
                                         instance_uuid, block_device_mapping):
            pass

        def _populate_security_groups(instance, security_groups):
            pass

        def _ensure_default(context):
            pass

        def _check_num_instances_quota(context, instance_type, min_count,
                                       max_count):
            self.assertEqual(self.base_options['user_id'], context.user_id)
            self.assertEqual(self.base_options['project_id'],
                             context.project_id)
            self.assertEqual(self.instance_type, instance_type)
            self.assertEqual(min_count, 1)
            self.assertEqual(max_count, 1)
            return (1, self.reservations)

        def _commit(context, quota_reservation, project_id=None, user_id=None):
            self.assertEqual(self.base_options['user_id'], context.user_id)
            self.assertEqual(self.base_options['project_id'],
                             context.project_id)
            self.assertEqual(self.reservations, quota_reservation)

        def _create_reservations(context, instance, instance_type_id,
                         project_id, user_id):
            return 'reservations'

        self.stubs.Set(self.compute_api, '_create_reservations',
                       _create_reservations)

        self.stubs.Set(self.compute_api, '_check_num_instances_quota',
                       _check_num_instances_quota)

        self.stubs.Set(quota.QUOTAS, 'commit', _commit)

        self.stubs.Set(self.compute_api.security_group_api,
                       'populate_security_groups', _populate_security_groups)

        self.stubs.Set(self.compute_api.security_group_api,
                       'ensure_default', _ensure_default)

        self.stubs.Set(self.compute_api, '_check_and_transform_bdm',
                       _check_and_transform_bdm)

        self.stubs.Set(self.compute_api, '_validate_bdm', _validate_bdm)

        self.stubs.Set(self.compute_api, '_update_block_device_mapping',
                       _update_block_device_mapping)

        self.stubs.Set(self.compute_task_api, 'migrate_from_fg',
                       _migrate_from_fg)

        self.stubs.Set(self.compute_api, '_check_requested_image',
                       _check_requested_image)
