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

import time

from oslo_log import log
from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = log.getLogger(__name__)


class TestRealExecuteStrategies(base.BaseInfraOptimScenarioTest):
    """Tests with real data for strategies"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    # Commands used to create load for different metrics
    COMMANDS_CREATE_LOAD = dict(
        instance_cpu_usage='nohup dd if=/dev/random of=/dev/null &',
        instance_ram_usage=(
            "sudo sh -c \"mkdir -p /mnt/tmpfs && "
            "mount -t tmpfs -o size=$(($(grep MemTotal /proc/meminfo | "
            "tr -s ' ' | cut -d' ' -f2)*9/10))k tmpfs /mnt/tmpfs\" && "
            "yes > /mnt/tmpfs/x")
    )

    @classmethod
    def skip_checks(cls):
        super(TestRealExecuteStrategies, cls).skip_checks()
        if not CONF.network_feature_enabled.floating_ips:
            raise cls.skipException(
                "network_feature_enabled.floating_ips option must be enabled")

    @classmethod
    def resource_setup(cls):
        super(TestRealExecuteStrategies, cls).resource_setup()
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

    @decorators.attr(type=['slow', 'real_load', 'cpu'])
    @decorators.idempotent_id('672a7a4d-91a0-4753-a7a4-be28db8c1bfb')
    def test_workload_balance_strategy_cpu(self):
        # This test does not require metrics injection
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        host = self.get_enabled_compute_nodes()[0]['host']
        hypervisor = self.get_hypervisor_details(host)
        instances = []
        created_instances = 2
        for _ in range(created_instances):
            instance = self._create_instance(
                host=host,
                run_command=self.COMMANDS_CREATE_LOAD['instance_cpu_usage'])
            instances.append(instance)

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        # This is the time that we want to generate metrics
        time.sleep(CONF.optimize.real_workload_period)

        # Set a threshold for CPU usage
        # ( <number of vms> - 0.5 ) * (0.8/<vcpus of the compute host>)*100
        threshold = round(
            (created_instances - 0.5) * (0.8 / int(hypervisor['vcpus'])) * 100)

        audit_parameters = {
            "metrics": "instance_cpu_usage",
            "threshold": threshold,
            "period": CONF.optimize.real_workload_period,
            "granularity": 300}

        goal_name = "workload_balancing"
        strategy_name = "workload_balance"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'], **audit_kwargs)

    @decorators.attr(type=['slow', 'real_load', 'ram'])
    @decorators.idempotent_id('f1b8a0c4-2d3e-4a5b-8f7c-6d9e5f2a0b1c')
    def test_workload_balance_strategy_ram(self):
        # This test does not require metrics injection
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        host = self.get_enabled_compute_nodes()[0]['host']
        hypervisor = self.get_hypervisor_details(host)
        # Flavor RAM is set to 15% of the hypervisor memory
        ram = int(hypervisor['memory_mb'] * 0.15)
        flavor_id = self._create_custom_flavor(ram=ram)
        instances = []
        for _ in range(2):
            instance = self._create_instance(
                host=host,
                flavor=flavor_id,
                run_command=self.COMMANDS_CREATE_LOAD['instance_ram_usage'])
            instances.append(instance)

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        # This is the time that we want to generate metrics
        time.sleep(CONF.optimize.real_workload_period)

        audit_parameters = {
            "metrics": "instance_ram_usage",
            "threshold": 18,
            "period": CONF.optimize.real_workload_period,
            "granularity": 300}

        goal_name = "workload_balancing"
        strategy_name = "workload_balance"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'], **audit_kwargs)

    @decorators.idempotent_id('95c7f20b-cd6e-4763-b1be-9a6ac7b5331c')
    @decorators.attr(type=['slow', 'real_load'])
    def test_workload_stabilization_strategy(self):
        # This test does not require metrics injection

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        run_command = self.COMMANDS_CREATE_LOAD['instance_cpu_usage']
        host = self.get_enabled_compute_nodes()[0]['host']
        instances = []
        for _ in range(2):
            instance = self._create_instance(host=host,
                                             run_command=run_command)
            instances.append(instance)
        # This is the time that we want to generate metrics
        time.sleep(CONF.optimize.real_workload_period)
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        audit_parameters = {
            "metrics": ["instance_cpu_usage"],
            "thresholds": {"instance_cpu_usage": 0.05},
            "weights": {"instance_cpu_usage_weight": 1.0},
            "periods": {"instance": CONF.optimize.real_workload_period,
                        "compute_node": CONF.optimize.real_workload_period},
            "instance_metrics": {"instance_cpu_usage": "host_cpu_usage"},
            "granularity": 30,
            "aggregation_method": {"instance": "mean", "compute_node": "mean"}}

        goal_name = "workload_balancing"
        strategy_name = "workload_stabilization"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'], **audit_kwargs)
