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


class TestExecuteWorkloadStabilizationStrategy(
        base.BaseInfraOptimScenarioTest):
    """Tests for workload_stabilization"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "workload_balancing"
    STRATEGY = "workload_stabilization"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

    @decorators.attr(type=['strategy', 'workload_stabilization'])
    @decorators.idempotent_id('14360d59-4923-49f7-bfe5-31d6a819b6f7')
    def test_execute_workload_stabilization_strategy_cpu(self):
        # This test requires metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)
        host = self.get_enabled_compute_nodes()[0]['host']
        instances = []
        for _ in range(2):
            instance = self._create_instance(host=host)
            instances.append(instance)
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)
        self.make_host_statistic(loaded_hosts=[host])
        for instance in instances:
            self.make_instance_statistic(instance)

        audit_template = self.create_audit_template_for_strategy()

        audit_parameters = {
            "metrics": ["instance_cpu_usage"],
            "thresholds": {"instance_cpu_usage": 0.05},
            "weights": {"instance_cpu_usage_weight": 1.0},
            "periods": {"instance": 400, "compute_node": 300},
            "instance_metrics": {"instance_cpu_usage": "host_cpu_usage"},
            "granularity": 300,
            "aggregation_method": {"instance": "mean", "compute_node": "mean"}}

        audit_kwargs = {"parameters": audit_parameters}

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], expected_action_types=['migrate'])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

    @decorators.attr(type=['strategy', 'workload_stabilization'])
    @decorators.idempotent_id('4988b894-b237-4ebc-9af1-ecf1f9ea734e')
    def test_execute_workload_stabilization_strategy_ram(self):
        # This test requires metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)
        host = self.get_enabled_compute_nodes()[0]['host']
        instances = []
        for _ in range(2):
            instance = self._create_instance(host=host)
            instances.append(instance)

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)
        self.make_host_statistic(loaded_hosts=[host])
        for instance in instances:
            # Inject metrics after the instances are created
            self.make_instance_statistic(instance)

        audit_template = self.create_audit_template_for_strategy()

        audit_parameters = {
            "metrics": ["instance_ram_usage"],
            "thresholds": {"instance_ram_usage": 0.05},
            "periods": {"instance": 400, "compute_node": 300}}
        audit_kwargs = {"parameters": audit_parameters}

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], expected_action_types=['migrate'])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return

        self.execute_action_plan_and_validate_states(action_plan['uuid'])
