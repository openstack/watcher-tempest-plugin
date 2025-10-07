# -*- encoding: utf-8 -*-
# Copyright (c) 2019 ZTE Corporation
#
#
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

from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF


class TestExecuteVmWorkloadBalanceStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for action plans"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "server_consolidation"
    STRATEGY = "vm_workload_consolidation"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

    @classmethod
    def resource_setup(cls):
        super().resource_setup()

        enabled_compute_nodes = cls.get_enabled_compute_nodes()

        cls.wait_for_compute_node_setup()

        if len(enabled_compute_nodes) < 2:
            raise cls.skipException(
                "Less than 2 compute nodes are enabled, "
                "skipping multinode tests.")

    @decorators.attr(type=['strategy', 'vm_workload_consolidation'])
    @decorators.idempotent_id('9f3ee978-e033-4c1e-bbf2-9e5a5cb8a365')
    def test_execute_vm_workload_consolidation_strategy(self):
        """Execute an action plan of vm_workload_consolidation strategy

        - create an audit template with vm_workload_consolidation strategy
        - run the audit to create an action plan
        - get the action plan
        - run the action plan
        - get results and make sure it succeeded
        """
        # This test requires metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)
        metrics = {
            'instance_cpu_usage': {},
            'instance_ram_usage': {},
            'instance_ram_allocated': {},
            'instance_root_disk_size': {},
        }
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)
        self.make_host_statistic()
        for instance in instances:
            self.make_instance_statistic(instance, metrics=metrics)

        audit_template = self.create_audit_template_for_strategy()

        audit_kwargs = {
            "parameters": {
                "period": 300,
            }
        }

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return

        self.execute_action_plan_and_validate_states(action_plan['uuid'])
