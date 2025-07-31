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


class TestExecuteStrategies(base.BaseInfraOptimScenarioTest):
    """Tests for strategies"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    @classmethod
    def skip_checks(cls):
        super(TestExecuteStrategies, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(TestExecuteStrategies, cls).resource_setup()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

        cls.wait_for_compute_node_setup()
        enabled_compute_nodes = cls.get_enabled_compute_nodes()
        if len(enabled_compute_nodes) < 2:
            raise cls.skipException(
                "Less than 2 compute nodes are enabled, "
                "skipping multinode tests.")

    @decorators.idempotent_id('62766a61-dfc4-478c-b80b-86d871227e67')
    def test_execute_basic_strategy(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)
        self.make_host_statistic()

        goal_name = "server_consolidation"
        strategy_name = "basic"
        audit_kwargs = {
            "parameters": {
                "granularity": 300,
                "period": 300,
                "aggregation_method": {"instance": "mean",
                                       "compute_node": "mean"}
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    @decorators.idempotent_id('a660e484-da76-478c-b18c-2eff243dde48')
    def test_execute_dummy_strategy(self):
        goal_name = "dummy"
        strategy_name = "dummy"
        audit_kwargs = dict()

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['sleep', 'nop'],
                              **audit_kwargs)

    @decorators.idempotent_id('7e3a9195-acc5-40cf-96da-a0a2883294d3')
    def test_execute_storage_capacity_balance_strategy(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=1)
        audit_parameters = {"volume_threshold": 25}

        goal_name = "workload_balancing"
        strategy_name = "storage_capacity_balance"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    @decorators.idempotent_id('9f3ee978-e033-4c1e-bbf2-9e5a5cb8a365')
    def test_execute_vm_workload_consolidation_strategy(self):
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

        goal_name = "server_consolidation"
        strategy_name = "vm_workload_consolidation"
        audit_kwargs = {
            "parameters": {
                "period": 300,
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    @decorators.idempotent_id('14360d59-4923-49f7-bfe5-31d6a819b6f7')
    def test_execute_workload_stabilization_strategy_cpu(self):
        # This test requires metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
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

        audit_parameters = {
            "metrics": ["instance_cpu_usage"],
            "thresholds": {"instance_cpu_usage": 0.05},
            "weights": {"instance_cpu_usage_weight": 1.0},
            "periods": {"instance": 400, "compute_node": 300},
            "instance_metrics": {"instance_cpu_usage": "host_cpu_usage"},
            "granularity": 300,
            "aggregation_method": {"instance": "mean", "compute_node": "mean"}}

        goal_name = "workload_balancing"
        strategy_name = "workload_stabilization"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'], **audit_kwargs)

    @decorators.idempotent_id('4988b894-b237-4ebc-9af1-ecf1f9ea734e')
    def test_execute_workload_stabilization_strategy_ram(self):
        # This test requires metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
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

        audit_parameters = {
            "metrics": ["instance_ram_usage"],
            "thresholds": {"instance_ram_usage": 0.05},
            "periods": {"instance": 400, "compute_node": 300}}

        goal_name = "workload_balancing"
        strategy_name = "workload_stabilization"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'], **audit_kwargs)

    @decorators.idempotent_id('c0c061e9-4713-4a23-a6e1-5db794add685')
    def test_execute_node_resource_consolidation_strategy_with_auto(self):
        # This test does not require metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        goal_name = "server_consolidation"
        strategy_name = "node_resource_consolidation"
        audit_kwargs = {
            "parameters": {
                "host_choice": 'auto'
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    @decorators.idempotent_id('12312f2b-ff7a-4722-9aa3-0262608e1ef0')
    def test_execute_node_resource_consolidation_strategy_with_specify(self):
        # This test does not require metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        goal_name = "server_consolidation"
        strategy_name = "node_resource_consolidation"
        audit_kwargs = {
            "parameters": {
                "host_choice": 'specify'
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)
