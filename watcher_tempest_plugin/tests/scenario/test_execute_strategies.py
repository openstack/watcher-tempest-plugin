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
        cls.initial_compute_nodes_setup = cls.get_compute_nodes_setup()
        enabled_compute_nodes = [cn for cn in cls.initial_compute_nodes_setup
                                 if cn.get('status') == 'enabled']
        if len(enabled_compute_nodes) < 2:
            raise cls.skipException(
                "Less than 2 compute nodes are enabled, "
                "skipping multinode tests.")

    @decorators.idempotent_id('62766a61-dfc4-478c-b80b-86d871227e67')
    def test_execute_basic_strategy(self):
        # This test does not require metrics injection
        INJECT_METRICS = False

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host_with_statistic(
            inject=INJECT_METRICS)
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

    @decorators.idempotent_id('17afd352-1929-46dd-a10a-63c90bb9255d')
    def test_execute_host_maintenance_strategy(self):
        # This test does not require metrics injection
        INJECT_METRICS = False

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host_with_statistic(
            inject=INJECT_METRICS)
        hostname = instances[0].get('OS-EXT-SRV-ATTR:hypervisor_hostname')
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": hostname
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    @decorators.idempotent_id('cc5a0f1b-e8d2-4813-b012-874982d15d06')
    def test_execute_host_maintenance_strategy_backup_node(self):
        # This test does not require metrics injection
        INJECT_METRICS = False

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host_with_statistic(
            inject=INJECT_METRICS)
        hostname = instances[0].get('OS-EXT-SRV-ATTR:hypervisor_hostname')
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        backup_node = [hyp['hypervisor_hostname'] for hyp
                       in self.get_hypervisors_setup()
                       if hyp['state'] == 'up'
                       and hyp['hypervisor_hostname'] != hostname][0]

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": hostname,
                "backup_node": backup_node
            }
        }

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['change_nova_service_state',
                                                'migrate'],
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
        INJECT_METRICS = True

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        metrics = {
            'instance_cpu_usage': {},
            'instance_ram_usage': {},
            'instance_ram_allocated': {},
            'instance_root_disk_size': {},
        }
        instances = self._create_one_instance_per_host_with_statistic(
            metrics, inject=INJECT_METRICS)
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)
        self.make_host_statistic()

        goal_name = "server_consolidation"
        strategy_name = "vm_workload_consolidation"
        audit_kwargs = {
            "parameters": {
                "period": 300,
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    @decorators.idempotent_id('14360d59-4923-49f7-bfe5-31d6a819b6f7')
    def test_execute_workload_stabilization_strategy(self):
        # This test requires metrics injection
        INJECT_METRICS = True

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host_with_statistic(
            inject=INJECT_METRICS)
        used_host = self._pack_all_created_instances_on_one_host(instances)
        loaded_hosts = [used_host]
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)
        self.make_host_statistic(loaded_hosts=loaded_hosts)

        audit_parameters = {
            "metrics": ["instance_cpu_usage"],
            "thresholds": {"instance_cpu_usage": 0.1},
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

    @decorators.idempotent_id('2119b69f-1cbd-4874-a82e-fceec093ebbb')
    def test_execute_zone_migration_live_migration_strategy(self):
        # This test requires metrics injection
        INJECT_METRICS = True

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host_with_statistic(
            inject=INJECT_METRICS)
        node = instances[0].get('OS-EXT-SRV-ATTR:hypervisor_hostname')
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        vacant_node = [hyp['hypervisor_hostname'] for hyp
                       in self.get_hypervisors_setup()
                       if hyp['state'] == 'up'
                       and hyp['hypervisor_hostname'] != node][0]

        audit_parameters = {
            "compute_nodes": [{"src_node": node, "dst_node": vacant_node}],
            }

        goal_name = "hardware_maintenance"
        strategy_name = "zone_migration"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    @decorators.idempotent_id('c0c061e9-4713-4a23-a6e1-5db794add685')
    def test_execute_node_resource_consolidation_strategy_with_auto(self):
        # This test does not require metrics injection
        INJECT_METRICS = False

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host_with_statistic(
            inject=INJECT_METRICS)
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
        INJECT_METRICS = False

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host_with_statistic(
            inject=INJECT_METRICS)
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
