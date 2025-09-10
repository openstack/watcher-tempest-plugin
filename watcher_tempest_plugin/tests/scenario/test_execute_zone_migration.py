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

    @decorators.attr(type=['strategy', 'zone_migration', 'volume_migration'])
    @decorators.idempotent_id('f8f4d551-d892-4111-ab92-5b6b5523e5dc')
    def test_execute_zone_migration_volume_retype(self):
        self.addCleanup(self.wait_delete_instances_from_model)

        # create second volume type
        volume_type = self.create_volume_type()

        # create a free volume
        volume = self.create_volume(
            name="free_volume_retype",
        )
        src_type = volume['volume_type']

        # create a volume and attach it to an instance
        instance = self.create_server(
            image_id=CONF.compute.image_ref, wait_until='ACTIVE',
            clients=self.os_admin)
        volume2 = self.create_volume(
            name="attached_volume_retype",
            )
        self.nova_volume_attach(
            instance, volume2,
            servers_client=self.os_admin.servers_client)
        # wait for compute model updates
        self.wait_for_instances_in_model([instance])

        src_pools = {
            self.get_host_for_volume(vol['id']) for vol in [volume, volume2]
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
            self.get_type_for_volume(volume['id']),
            volume_type['name']
        )
        self.assertEqual(
            self.get_type_for_volume(volume2['id']),
            volume_type['name']
        )
