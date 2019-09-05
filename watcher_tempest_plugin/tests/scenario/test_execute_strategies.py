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

    def test_execute_basic_strategy(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        self._create_one_instance_per_host_with_statistic()
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

    def test_execute_dummy_strategy(self):
        goal_name = "dummy"
        strategy_name = "dummy"
        audit_kwargs = dict()

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    def test_execute_host_maintenance_strategy(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        instances = self._create_one_instance_per_host_with_statistic()
        hostname = instances[0].get('OS-EXT-SRV-ATTR:hypervisor_hostname')

        goal_name = "cluster_maintaining"
        strategy_name = "host_maintenance"
        audit_kwargs = {
            "parameters": {
                "maintenance_node": hostname
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    def test_execute_storage_capacity_balance_strategy(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref)
        audit_parameters = {"volume_threshold": 25}

        goal_name = "workload_balancing"
        strategy_name = "storage_capacity_balance"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    def test_execute_vm_workload_consolidation_strategy(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        metrics = {
            'cpu_util': {
                'archive_policy_name': 'low'
            },
            'memory.resident': {
                'archive_policy_name': 'low'
            },
            'memory': {
                'archive_policy_name': 'low'
            },
            'disk.root.size': {
                'archive_policy_name': 'low'
            }
        }
        self._create_one_instance_per_host_with_statistic(metrics)

        goal_name = "server_consolidation"
        strategy_name = "vm_workload_consolidation"
        audit_kwargs = {
            "parameters": {
                "period": 300,
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    def test_execute_workload_stabilization_strategy(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        instances = self._create_one_instance_per_host_with_statistic()
        self._pack_all_created_instances_on_one_host(instances)
        self.make_host_statistic()

        audit_parameters = {
            "metrics": ["instance_cpu_usage"],
            "thresholds": {"instance_cpu_usage": 0.2},
            "weights": {"instance_cpu_usage_weight": 1.0},
            "periods": {"instance": 72000, "compute_node": 60000},
            "instance_metrics": {"instance_cpu_usage": "host_cpu_usage"},
            "granularity": 300,
            "aggregation_method": {"instance": "mean", "compute_node": "mean"}}

        goal_name = "workload_balancing"
        strategy_name = "workload_stabilization"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    def test_execute_zone_migration_live_migration_strategy(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        instances = self._create_one_instance_per_host_with_statistic()
        node = instances[0].get('OS-EXT-SRV-ATTR:hypervisor_hostname')

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

    def test_execute_node_resource_consolidation_strategy_with_auto(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        self._create_one_instance_per_host_with_statistic()

        goal_name = "server_consolidation"
        strategy_name = "node_resource_consolidation"
        audit_kwargs = {
            "parameters": {
                "host_choice": 'auto'
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)

    def test_execute_node_resource_consolidation_strategy_with_specify(self):
        self.addCleanup(self.rollback_compute_nodes_status)
        self._create_one_instance_per_host_with_statistic()

        goal_name = "server_consolidation"
        strategy_name = "node_resource_consolidation"
        audit_kwargs = {
            "parameters": {
                "host_choice": 'specify'
            }
        }

        self.execute_strategy(goal_name, strategy_name, **audit_kwargs)
