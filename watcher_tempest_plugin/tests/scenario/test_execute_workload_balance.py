# -*- encoding: utf-8 -*-
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

from oslo_log import log
from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = log.getLogger(__name__)


class TestExecuteWorkloadBalanceStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for workload_balance"""

    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    @classmethod
    def skip_checks(cls):
        super(TestExecuteWorkloadBalanceStrategy, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(TestExecuteWorkloadBalanceStrategy, cls).resource_setup()
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

    @decorators.attr(type=['strategy', 'workload_balance'])
    @decorators.idempotent_id('64a9293f-0f81-431c-afae-ecabebae53f1')
    def test_execute_workload_balance_strategy_cpu(self):
        # This test requires metrics injection
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        host = self.get_enabled_compute_nodes()[0]['host']
        instances = []
        for _ in range(4):
            instance = self._create_instance(host)
            instances.append(instance)

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        for instance in instances:
            # Inject metrics after the instances are created
            self.make_instance_statistic(instance)

        audit_parameters = {
            "metrics": "instance_cpu_usage",
            "threshold": 15,
            "period": 300,
            "granularity": 300}

        goal_name = "workload_balancing"
        strategy_name = "workload_balance"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'], **audit_kwargs)

    @decorators.attr(type=['strategy', 'workload_balance'])
    @decorators.idempotent_id('de4f662a-26b1-4cbe-ba8e-c213bac0a996')
    def test_execute_workload_balance_strategy_ram(self):
        # This test requires metrics injection
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        host = self.get_enabled_compute_nodes()[0]['host']
        instances = []
        for _ in range(4):
            instance = self._create_instance(host)
            instances.append(instance)

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        for instance in instances:
            # Inject metrics after the instances are created
            self.make_instance_statistic(instance)

        audit_parameters = {
            "metrics": "instance_ram_usage",
            "threshold": 2.5,
            "period": 300,
            "granularity": 300}

        goal_name = "workload_balancing"
        strategy_name = "workload_balance"
        audit_kwargs = {"parameters": audit_parameters}

        self.execute_strategy(goal_name, strategy_name,
                              expected_actions=['migrate'], **audit_kwargs)
