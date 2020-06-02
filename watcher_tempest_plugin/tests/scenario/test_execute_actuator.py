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

import collections
import functools

from tempest import config
from tempest.lib.common.utils import test_utils

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF


class TestExecuteActionsViaActuator(base.BaseInfraOptimScenarioTest):

    scenarios = [
        ("nop", {"actions": [
            {"action_type": "nop",
             "input_parameters": {
                 "message": "hello World"}}]}),
        ("sleep", {"actions": [
            {"action_type": "sleep",
             "input_parameters": {
                 "duration": 1.0}}]}),
        ("change_nova_service_state", {"actions": [
            {"action_type": "change_nova_service_state",
             "input_parameters": {
                 "state": "enabled"},
             "filling_function":
                 "_prerequisite_param_for_"
                 "change_nova_service_state_action"}]}),
        ("resize", {"actions": [
            {"action_type": "resize",
             "filling_function": "_prerequisite_param_for_resize_action"}]}),
        ("migrate", {"actions": [
            {"action_type": "migrate",
             "input_parameters": {
                 "migration_type": "live"},
             "filling_function": "_prerequisite_param_for_migrate_action"},
            {"action_type": "migrate",
             "input_parameters": {
                 "migration_type": "cold"},
             "filling_function": "_prerequisite_param_for_migrate_action"}]})
    ]

    @classmethod
    def resource_setup(cls):
        super(TestExecuteActionsViaActuator, cls).resource_setup()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

        cls.initial_compute_nodes_setup = cls.get_compute_nodes_setup()
        enabled_compute_nodes = [cn for cn in cls.initial_compute_nodes_setup
                                 if cn.get('status') == 'enabled']

        cls.wait_for_compute_node_setup()

        if len(enabled_compute_nodes) < 2:
            raise cls.skipException(
                "Less than 2 compute nodes are enabled, "
                "skipping multinode tests.")

    def _get_flavors(self):
        return self.mgr.flavors_client.list_flavors()['flavors']

    def _prerequisite_param_for_migrate_action(self):
        created_instances = self._create_one_instance_per_host_with_statistic()
        instance = created_instances[0]
        source_node = created_instances[0]["OS-EXT-SRV-ATTR:host"]
        destination_node = created_instances[-1]["OS-EXT-SRV-ATTR:host"]

        parameters = {
            "resource_id": instance['id'],
            "migration_type": "live",
            "source_node": source_node,
            "destination_node": destination_node
        }

        return parameters

    def _prerequisite_param_for_resize_action(self):
        created_instances = self._create_one_instance_per_host_with_statistic()
        instance = created_instances[0]
        current_flavor_name = instance['flavor']['original_name']

        flavors = self._get_flavors()
        new_flavors = [f for f in flavors if f['name'] != current_flavor_name]
        new_flavor = new_flavors[0]

        parameters = {
            "resource_id": instance['id'],
            "flavor": new_flavor['name']
        }

        return parameters

    def _prerequisite_param_for_change_nova_service_state_action(self):
        enabled_compute_nodes = [cn for cn in
                                 self.initial_compute_nodes_setup
                                 if cn.get('status') == 'enabled']
        enabled_compute_node = enabled_compute_nodes[0]

        parameters = {
            "resource_id": enabled_compute_node['host'],
            "state": "enabled"
        }

        return parameters

    def _fill_actions(self, actions):
        for action in actions:
            filling_function_name = action.pop('filling_function', None)

            if filling_function_name is not None:
                filling_function = getattr(self, filling_function_name, None)

                if filling_function is not None:
                    parameters = filling_function()

                    resource_id = parameters.pop('resource_id', None)

                    if resource_id is not None:
                        action['resource_id'] = resource_id

                    input_parameters = action.get('input_parameters', None)

                    if input_parameters is not None:
                        parameters.update(input_parameters)
                        input_parameters.update(parameters)
                    else:
                        action['input_parameters'] = parameters

    def _execute_actions(self, actions):
        self.wait_for_all_action_plans_to_finish()

        _, goal = self.client.show_goal("unclassified")
        _, strategy = self.client.show_strategy("actuator")
        _, audit_template = self.create_audit_template(
            goal['uuid'], strategy=strategy['uuid'])
        _, audit = self.create_audit(
            audit_template['uuid'], parameters={"actions": actions})

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(self.has_audit_succeeded, audit['uuid']),
            duration=30,
            sleep_for=.5
        ))
        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        # Execute the action plan
        _, updated_ap = self.client.start_action_plan(action_plan['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plan_finished, action_plan['uuid']),
            duration=300,
            sleep_for=1
        ))
        _, finished_ap = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=finished_ap["uuid"])

        self.assertIn(updated_ap['state'], ('PENDING', 'ONGOING'))
        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        expected_action_counter = collections.Counter(
            act['action_type'] for act in actions)
        action_counter = collections.Counter(
            act['action_type'] for act in action_list['actions'])

        self.assertEqual(expected_action_counter, action_counter)

    def test_execute_scenarios(self):
        self.addCleanup(self.rollback_compute_nodes_status)

        for _, scenario in self.scenarios:
            actions = scenario['actions']
            self._fill_actions(actions)
            self._execute_actions(actions)
