# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from oslo_log import log
from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = log.getLogger(__name__)


class TestZoneMigrationStrategyBase(base.BaseInfraOptimScenarioTest):
    """Base class for ZoneMigration tests"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "hardware_maintenance"
    STRATEGY = "zone_migration"
    # This test does not require metrics injection
    INJECT_METRICS = False

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")


class TestExecuteZoneMigrationStrategy(TestZoneMigrationStrategyBase):
    """Tests for action plans"""

    @decorators.idempotent_id('2119b69f-1cbd-4874-a82e-fceec093ebbb')
    @decorators.attr(type=['strategy', 'zone_migration'])
    def test_execute_zone_migration_with_destination_host(self):
        # This test requires metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])
        dst_node = self.get_host_other_than(instances[0]['id'])

        audit_parameters = {
            "compute_nodes": [{"src_node": src_node, "dst_node": dst_node}],
            }

        audit_kwargs = {"parameters": audit_parameters}

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

    @decorators.idempotent_id('e4f192ca-26d4-4e38-bb86-4be4aeaabb24')
    @decorators.attr(type=['strategy', 'zone_migration'])
    def test_execute_zone_migration_without_destination_host(self):
        if not CONF.optimize.run_zone_migration_extra_tests:
            raise self.skipException(
                "Extra tests for zone migration are not enabled."
            )
        # This test requires metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])

        audit_parameters = {
            "compute_nodes": [{"src_node": src_node}],
            }

        audit_kwargs = {"parameters": audit_parameters}

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])


class TestExecuteZoneMigrationStrategyVolume(TestZoneMigrationStrategyBase):

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.service_available.cinder:
            raise cls.skipException("Cinder is not available")
        if not CONF.optimize.run_zone_migration_storage_tests:
            raise cls.skipException(
                "Storage tests for zone migration are not enabled."
            )

    def get_host_for_volume(self, volume_id):
        """Gets host of volume"""

        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume_id
            )
        return volume_details['volume']['os-vol-host-attr:host']

    def get_type_for_volume(self, volume_id):
        """Gets volume type"""

        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume_id
            )
        return volume_details['volume']['volume_type']

    def get_pool_names(self):
        """Get the names of the existing cinder pools.

        :returns: A set with the list of cinder pool names
        """
        # use os_admin client since the backend storage pool information is
        # only available as admin
        # https://docs.openstack.org/api-ref/block-storage/v3/index.html?expanded=detach-volume-from-server-detail#back-end-storage-pools
        pools = self.os_admin.volume_scheduler_stats_client_latest.list_pools()
        # pool['name'] follows the full qualified backend name,
        # host@backend@pool
        return {pool['name'] for pool in pools['pools']}

    def check_multiple_pools(self):
        """Checks if there is more than one cinder pool.

        Get the list of pool names from cinder scheduler stats API. If there
        aren't at least two pools, raises an skipException.
        """
        pools = self.get_pool_names()
        if len(pools) < 2:
            raise self.skipException(
                "Need at least one backend with multiple pools to "
                f"test volume migration, {len(pools)} found"
            )

    @decorators.attr(type=['strategy', 'zone_migration', 'volume_migration'])
    @decorators.idempotent_id('f8f4d551-d892-4111-ab92-5b6b5523e5dc')
    def test_execute_zone_migration_volume_retype(self):
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)

        # create second volume type
        volume_type = self.create_volume_type()

        # create a free volume
        free_volume = self.create_volume(
            name="free_volume_retype",
        )
        src_type = free_volume['volume_type']

        # create a volume and attach it to an instance
        instance = self.create_server(
            image_id=CONF.compute.image_ref,
            wait_until='SSHABLE',
            clients=self.os_primary,
        )
        vm_volume = self.create_volume(
            name="attached_volume_retype",
            )
        self.nova_volume_attach(
            instance, vm_volume, servers_client=self.os_primary.servers_client
        )
        # wait for compute model updates
        self.wait_for_instances_in_model([instance])

        src_pools = {
            self.get_host_for_volume(vol['id'])
            for vol in [free_volume, vm_volume]
        }

        audit_parameters = {
            "storage_pools": [
                {"src_pool": src_pool, "src_type": src_type,
                 "dst_type": volume_type['name']}
                for src_pool in src_pools
                ]
            }

        audit_kwargs = {"parameters": audit_parameters}

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['volume_migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

        # check that the available volume was retyped
        self.assertEqual(
            self.get_type_for_volume(free_volume['id']), volume_type['name']
        )
        self.assertEqual(
            self.get_type_for_volume(vm_volume['id']), volume_type['name']
        )

    @decorators.attr(type=['strategy', 'zone_migration', 'volume_migration'])
    @decorators.idempotent_id('2287000d-6f0e-4275-8741-cfeb38090307')
    def test_execute_zone_migration_volume_migrate(self):
        # check that there are multiple cinder pools configured
        # to be able to test migrations between them
        self.check_multiple_pools()

        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)

        volume_type = self.create_volume_type()

        # create a free volume
        free_volume = self.create_volume(
            name='free_volume_migrate', volume_type=volume_type['name']
        )

        # create a volume and attach it to an instance
        instance = self.create_server(
            image_id=CONF.compute.image_ref,
            wait_until='SSHABLE',
            clients=self.os_primary,
        )

        vm_volume = self.create_volume(
            name='attached_volume_migrate', volume_type=volume_type['name']
        )
        self.nova_volume_attach(
            instance, vm_volume, servers_client=self.os_primary.servers_client
        )
        # wait for compute model updates
        self.wait_for_instances_in_model([instance])

        src_pool_free_volume = self.get_host_for_volume(free_volume['id'])
        src_pool_vm_volume = self.get_host_for_volume(vm_volume['id'])
        if src_pool_free_volume == src_pool_vm_volume:
            # if both volumes are scheduled in the same storage host we only
            # need one entry in the input parameters, it's enough picking one
            # pool that is different than the source pool
            all_pools = self.get_pool_names()
            other_pools = all_pools - {src_pool_free_volume}
            if not other_pools:
                self.fail(
                    "could not find a destination pool for volumes "
                    f"in {src_pool_free_volume}"
                )
            dst_pool_free_volume = dst_pool_vm_volume = other_pools.pop()
            audit_parameters = {
                'storage_pools': [
                    {
                        'src_pool': src_pool_free_volume,
                        'src_type': volume_type['name'],
                        'dst_pool': dst_pool_free_volume
                    }
                ]
            }
        else:
            # if the two volumes are scheduled in different hosts, we need to
            # add both source hosts to the input parameters. Each volume is
            # then migrated to the other's source pool and the 'src_type'
            # parameter is set to the volume type created in the test to ensure
            # no other volumes are migrated
            dst_pool_free_volume = src_pool_vm_volume
            dst_pool_vm_volume = src_pool_free_volume
            audit_parameters = {
                'storage_pools': [
                    {
                        'src_pool': src_pool_free_volume,
                        'src_type': volume_type['name'],
                        'dst_pool': dst_pool_free_volume
                    },
                    {
                        'src_pool': src_pool_vm_volume,
                        'src_type': volume_type['name'],
                        'dst_pool': dst_pool_vm_volume
                    }
                ]
            }

        audit_kwargs = {'parameters': audit_parameters}

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['volume_migrate'])

        self.assertEqual('RECOMMENDED', action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

        free_volume_host = self.get_host_for_volume(free_volume['id'])
        self.assertEqual(free_volume_host, dst_pool_free_volume)
        self.assertNotEqual(free_volume_host, src_pool_free_volume)

        vm_volume_host = self.get_host_for_volume(vm_volume['id'])
        self.assertEqual(vm_volume_host, dst_pool_vm_volume)
        self.assertNotEqual(vm_volume_host, src_pool_vm_volume)
