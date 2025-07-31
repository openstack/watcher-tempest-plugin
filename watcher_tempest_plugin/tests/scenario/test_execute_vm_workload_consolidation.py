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

import functools

from tempest import config
from tempest.lib.common.utils import test_utils
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF


class TestExecuteVmWorkloadBalanceStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for action plans"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL_NAME = "server_consolidation"

    @classmethod
    def skip_checks(cls):
        super(TestExecuteVmWorkloadBalanceStrategy, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(TestExecuteVmWorkloadBalanceStrategy, cls).resource_setup()
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

    @decorators.idempotent_id('4b1830f6-846a-497f-b44c-636c2cac0df8')
    def test_execute_vm_workload_consolidation_action_plan(self):
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

        _, goal = self.client.show_goal(self.GOAL_NAME)
        _, strategy = self.client.show_strategy("vm_workload_consolidation")
        _, audit_template = self.create_audit_template(
            goal['uuid'], strategy=strategy['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plans_finished),
            duration=600,
            sleep_for=2
        ))

        _, audit = self.create_audit(
            audit_template['uuid'],
            parameters={
                "period": 72000
            }
        )

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
        if finished_audit.get('state') in ('FAILED', 'CANCELLED', 'SUSPENDED'):
            self.fail("The audit ended in unexpected state: %s!"
                      % finished_audit.get('state'))

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return

        # Execute the action by changing its state to PENDING
        _, updated_ap = self.client.start_action_plan(action_plan['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plan_finished, action_plan['uuid']),
            duration=600,
            sleep_for=2
        ))
        _, finished_ap = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=finished_ap["uuid"])
        self.assertIn(updated_ap['state'], ('PENDING', 'ONGOING'))
        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        for action in action_list['actions']:
            self.assertEqual('SUCCEEDED', action.get('state'))
