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

    # Minimal version required for _create_one_instance_per_host_with_statistic
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    # Commands used to create load for different metrics
    COMMANDS_CREATE_LOAD = dict(
        instance_cpu_usage='nohup dd if=/dev/random of=/dev/null &',)

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
        cls.initial_compute_nodes_setup = cls.get_compute_nodes_setup()
        enabled_compute_nodes = [cn for cn in cls.initial_compute_nodes_setup
                                 if cn.get('status') == 'enabled']
        if len(enabled_compute_nodes) < 2:
            raise cls.skipException(
                "Less than 2 compute nodes are enabled, "
                "skipping multinode tests.")

    @decorators.attr(type=['slow', 'real_load'])
    @decorators.idempotent_id('95c7f20b-cd6e-4763-b1be-9a6ac7b5331c')
    def test_workload_stabilization_strategy(self):
        # This test does not require metrics injection
        INJECT_METRICS = False

        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host_with_statistic(
            run_command=self.COMMANDS_CREATE_LOAD['instance_cpu_usage'],
            inject=INJECT_METRICS)
        self._pack_all_created_instances_on_one_host(instances)
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
