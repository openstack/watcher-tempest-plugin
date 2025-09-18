# -*- encoding: utf-8 -*-
# Copyright (c) 2016 b<>com
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


class TestExecuteBasicStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for action plans"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "server_consolidation"
    STRATEGY = "basic"

    @classmethod
    def skip_checks(cls):
        super(TestExecuteBasicStrategy, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(TestExecuteBasicStrategy, cls).resource_setup()
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

    @decorators.attr(type=['strategy', 'basic'])
    @decorators.idempotent_id('62766a61-dfc4-478c-b80b-86d871227e67')
    def test_execute_basic_strategy(self):
        """Execute an action plan based on the BASIC strategy

        - create an audit template with the basic strategy
        - run the audit to create an action plan
        - get the action plan
        - run the action plan
        - get results and make sure it succeeded
        """
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)
        self.make_host_statistic()
        for instance in instances:
            self.make_instance_statistic(instance)

        audit_kwargs = {
            "parameters": {
                "granularity": 300,
                "period": 300,
                "aggregation_method": {"instance": "mean",
                                       "compute_node": "mean"}
            }
        }

        self.execute_strategy(self.GOAL, self.STRATEGY, **audit_kwargs)
