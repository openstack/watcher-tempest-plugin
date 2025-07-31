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

import functools

from oslo_log import log
from tempest import config
from tempest.lib.common.utils import test_utils
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = log.getLogger(__name__)


class TestExecuteWorkloadBalancingStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for action plans"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "workload_balancing"

    @classmethod
    def skip_checks(cls):
        super(TestExecuteWorkloadBalancingStrategy, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(TestExecuteWorkloadBalancingStrategy, cls).resource_setup()
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

    @decorators.idempotent_id('3bb80932-9caa-4c30-8dfd-7d6f429d8784')
    def test_execute_workload_stabilization(self):

        # This test requires metrics injection

        """Execute an action plan using the workload_stabilization strategy"""
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        host = self.get_enabled_compute_nodes()[0]['host']
        instances = []
        for _ in range(2):
            instance = self._create_instance(host=host)
            instances.append(instance)
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        audit_parameters = {
            "metrics": ["instance_cpu_usage"],
            "thresholds": {"instance_cpu_usage": 0.2},
            "weights": {"instance_cpu_usage_weight": 1.0},
            "periods": {"instance": 72000, "compute_node": 60000},
            "instance_metrics": {"instance_cpu_usage": "host_cpu_usage"},
            "granularity": 300,
            "aggregation_method": {"instance": "mean", "compute_node": "mean"}}

        _, goal = self.client.show_goal(self.GOAL)
        _, strategy = self.client.show_strategy("workload_stabilization")
        _, audit_template = self.create_audit_template(
            goal['uuid'], strategy=strategy['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plans_finished),
            duration=600,
            sleep_for=2
        ))

        _, audit = self.create_audit(
            audit_template['uuid'], parameters=audit_parameters)

        try:
            self.assertTrue(test_utils.call_until_true(
                func=functools.partial(
                    self.has_audit_finished, audit['uuid']),
                duration=600,
                sleep_for=2
            ))
        except ValueError:
            self.fail("The audit has failed!")

        _, finished_audit = self.client.show_audit(audit['uuid'])
        if finished_audit.get('state') in ('FAILED', 'CANCELLED'):
            self.fail("The audit ended in unexpected state: %s!" %
                      finished_audit.get('state'))

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=action_plan["uuid"])
