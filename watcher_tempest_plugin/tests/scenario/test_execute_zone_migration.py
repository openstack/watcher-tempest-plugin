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


class TestExecuteZoneMigrationStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for action plans"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "hardware_maintenance"
    # This test does not require metrics injection
    INJECT_METRICS = False

    @classmethod
    def skip_checks(cls):
        super(TestExecuteZoneMigrationStrategy, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(TestExecuteZoneMigrationStrategy, cls).resource_setup()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

        enabled_compute_nodes = cls.get_enabled_compute_nodes()
        cls.wait_for_compute_node_setup()

        if len(enabled_compute_nodes) < 2:
            raise cls.skipException(
                "Less than 2 compute nodes are enabled, "
                "skipping multinode tests.")

    @decorators.idempotent_id('2119b69f-1cbd-4874-a82e-fceec093ebbb')
    @decorators.attr(type=['strategy', 'zone_migration'])
    def test_execute_zone_migration_with_destination_host(self):
        # This test requires metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])
        dst_node = self.get_host_other_than(instances[0]['id'])

        audit_parameters = {
            "compute_nodes": [{"src_node": src_node, "dst_node": dst_node}],
            }

        goal_name = "hardware_maintenance"
        strategy_name = "zone_migration"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'],
                              **audit_kwargs)

    @decorators.idempotent_id('e4f192ca-26d4-4e38-bb86-4be4aeaabb24')
    @decorators.attr(type=['strategy', 'zone_migration'])
    def test_execute_zone_migration_without_destination_host(self):
        # This test requires metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])

        audit_parameters = {
            "compute_nodes": [{"src_node": src_node}],
            }

        goal_name = "hardware_maintenance"
        strategy_name = "zone_migration"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'],
                              **audit_kwargs)
