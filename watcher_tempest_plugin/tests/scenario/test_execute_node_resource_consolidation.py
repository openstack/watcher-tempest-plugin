# Copyright 2025 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF


class TestExecuteNodeResourceConsolidationStrategy(
        base.BaseInfraOptimScenarioTest):
    """Tests for node_resource_consolidation"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "server_consolidation"
    STRATEGY = "node_resource_consolidation"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()

        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")

        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

    @decorators.attr(type=['strategy', 'node_resource_consolidation'])
    @decorators.idempotent_id('c0c061e9-4713-4a23-a6e1-5db794add685')
    def test_execute_node_resource_consolidation_strategy_with_auto(self):
        # This test does not require metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        audit_template = self.create_audit_template_for_strategy()

        audit_kwargs = {
            "parameters": {
                "host_choice": 'auto'
            }
        }

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['change_nova_service_state', 'migrate'])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

    @decorators.attr(type=['strategy', 'node_resource_consolidation'])
    @decorators.idempotent_id('12312f2b-ff7a-4722-9aa3-0262608e1ef0')
    def test_execute_node_resource_consolidation_strategy_with_specify(self):
        # This test does not require metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        audit_template = self.create_audit_template_for_strategy()

        audit_kwargs = {
            "parameters": {
                "host_choice": 'specify'
            }
        }

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['migrate'])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return

        self.execute_action_plan_and_validate_states(action_plan['uuid'])
