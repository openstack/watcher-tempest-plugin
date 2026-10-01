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

from tempest.common import compute
from tempest.common import waiters
from tempest import config
from tempest.lib.common.utils import test_utils
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF


class TestExecuteActionsViaActuator(base.BaseInfraOptimScenarioTest):

    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

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
    def skip_checks(cls):
        super().skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

    def _get_flavors(self):
        return self.mgr.flavors_client.list_flavors()['flavors']

    def _prerequisite_param_for_migrate_action(self):
        # This test requires metrics injection
        self.addCleanup(self.clean_injected_metrics)
        created_instances = self._create_one_instance_per_host()
        source_node = self.get_host_for_server(created_instances[0]['id'])
        destination_node = self.get_host_other_than(created_instances[0]['id'])
        for instance in created_instances:
            self.make_instance_statistic(instance)

        parameters = {
            "resource_id": created_instances[0]['id'],
            "migration_type": "live",
            "source_node": source_node,
            "destination_node": destination_node
        }

        return parameters

    def _prerequisite_param_for_resize_action(self):
        # This test requires metrics injection
        self.addCleanup(self.clean_injected_metrics)
        created_instances = self._create_one_instance_per_host()
        for instance in created_instances:
            self.make_instance_statistic(instance)

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
        enabled_compute_node = self.get_enabled_compute_nodes()[0]

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
            duration=CONF.optimize.resource_timeout,
            sleep_for=CONF.optimize.resource_check_interval
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
            duration=CONF.optimize.resource_timeout,
            sleep_for=CONF.optimize.resource_check_interval
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

    @decorators.idempotent_id('0af1a181-38c8-4416-8e85-8ebca8ac1cf8')
    def test_execute_scenarios(self):
        # Migration action requires at least 2 enabled compute nodes
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.rollback_compute_nodes_status)

        for _, scenario in self.scenarios:
            actions = scenario['actions']
            self._fill_actions(actions)
            self._execute_actions(actions)


class TestExecuteDeleteAndShelveActions(
        base.BaseInfraOptimScenarioTest):
    """Scenario tests for the delete and shelve actions.

    Each test creates a real Nova instance via the actuator strategy,
    executes the action plan, and then verifies the expected server state
    (terminated or shelved) as the postcondition.
    """

    # Minimal version required for _create_instance with a specific host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST
    # Minimal version required for waiting for instances in model using the
    # datamodel list api
    min_microversion = '1.3'

    GOAL = "unclassified"
    STRATEGY = "actuator"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.optimize.run_delete_shelve_action_tests:
            raise cls.skipException(
                "Delete and shelve action tests are not enabled."
            )

    def _run_actuator_action(self, actions):
        """Submit actions through the actuator and wait for completion.

        :param actions: list of action dicts to pass as audit parameters.
        :returns: the finished action plan dict.
        """
        self.wait_for_all_action_plans_to_finish()

        audit_template = self.create_audit_template_for_strategy()
        audit = self.create_audit_and_wait(
            audit_template['uuid'], parameters={"actions": actions})

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]
        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        _, updated_ap = self.client.start_action_plan(action_plan['uuid'])
        self.assertIn(updated_ap['state'], ('PENDING', 'ONGOING'))

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plan_finished, action_plan['uuid']),
            duration=CONF.optimize.resource_timeout,
            sleep_for=CONF.optimize.resource_check_interval
        ))

        _, finished_ap = self.client.show_action_plan(action_plan['uuid'])
        return finished_ap

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('b3f2a1c4-8e7d-4a90-bc12-5f6e3d9a0b47')
    def test_delete_active_instance(self):
        """Test that the delete action terminates an ACTIVE instance.

        Creates an instance, submits a delete action through the actuator
        strategy, and verifies the instance no longer exists after the
        action plan succeeds.
        """
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        source_host = self.get_enabled_compute_nodes()[0]['host']
        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        actions = [
            {
                "action_type": "delete",
                "resource_id": instance['id'],
                "input_parameters": {}
            }
        ]

        finished_ap = self._run_actuator_action(actions)
        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        # Verify the instance no longer exists
        waiters.wait_for_server_termination(
            self.mgr.servers_client, instance['id'])

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('4070c0ec-43b1-41fc-9363-a5e8458cb87c')
    def test_delete_skipped_when_instance_already_deleted(self):
        """Test that the delete action is skipped when instance is gone.

        Deletes the instance before executing the action plan. The
        pre_condition check should detect the missing instance and mark
        the action as SKIPPED, leaving the action plan in SUCCEEDED state.
        """
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        source_host = self.get_enabled_compute_nodes()[0]['host']
        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        actions = [
            {
                "action_type": "delete",
                "resource_id": instance['id'],
                "input_parameters": {}
            }
        ]

        self.wait_for_all_action_plans_to_finish()

        audit_template = self.create_audit_template_for_strategy()
        audit = self.create_audit_and_wait(
            audit_template['uuid'], parameters={"actions": actions})

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]
        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        # Delete the instance before the action plan is executed so the
        # pre_condition finds it missing and skips the action.
        self._delete_instance(instance['id'])

        _, updated_ap = self.client.start_action_plan(action_plan['uuid'])
        self.assertIn(updated_ap['state'], ('PENDING', 'ONGOING'))

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plan_finished, action_plan['uuid']),
            duration=CONF.optimize.resource_timeout,
            sleep_for=CONF.optimize.resource_check_interval
        ))

        _, finished_ap = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=finished_ap['uuid'])

        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        action_states = [a['state'] for a in action_list['actions']]
        self.assertIn('SKIPPED', action_states)

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('ef156ca9-50d3-45e6-83f4-d97bfa92e168')
    def test_shelve_active_instance(self):
        """Test that the shelve action shelves an ACTIVE instance.

        Creates an instance, submits a shelve action through the actuator
        strategy, and verifies the instance reaches SHELVED or
        SHELVED_OFFLOADED state after the action plan succeeds.
        """
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        source_host = self.get_enabled_compute_nodes()[0]['host']
        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        actions = [
            {
                "action_type": "shelve",
                "resource_id": instance['id'],
                "input_parameters": {}
            }
        ]

        finished_ap = self._run_actuator_action(actions)
        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        # Verify the instance is shelved or shelved_offloaded.
        # Nova may offload immediately (e.g. with Ceph or BFV), so both
        # states are valid postconditions.
        instance_details = self.mgr.servers_client.show_server(
            instance['id'])['server']
        self.assertIn(
            instance_details['status'], ('SHELVED', 'SHELVED_OFFLOADED'))

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('752d84da-bb38-4cf2-8fb0-7bd1963dab21')
    def test_shelve_skipped_when_instance_already_shelved(self):
        """Test that the shelve action is skipped when instance is shelved.

        Shelves the instance manually before executing the action plan.
        The pre_condition check should detect the existing shelved state
        and mark the action as SKIPPED, leaving the action plan SUCCEEDED.
        """
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        source_host = self.get_enabled_compute_nodes()[0]['host']
        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        # Shelve the instance before the action plan runs so the
        # pre_condition finds it already shelved and skips the action.
        compute.shelve_server(self.mgr.servers_client, instance['id'])

        actions = [
            {
                "action_type": "shelve",
                "resource_id": instance['id'],
                "input_parameters": {}
            }
        ]

        finished_ap = self._run_actuator_action(actions)
        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        _, action_list = self.client.list_actions(
            action_plan_uuid=finished_ap['uuid'])
        action_states = [a['state'] for a in action_list['actions']]
        self.assertIn('SKIPPED', action_states)

        # Verify instance is still in a shelved state
        instance_details = self.mgr.servers_client.show_server(
            instance['id'])['server']
        self.assertIn(
            instance_details['status'], ('SHELVED', 'SHELVED_OFFLOADED'))

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('72c68eec-3223-4216-a984-902caca3cfb4')
    def test_shelve_skipped_when_instance_not_found(self):
        """Test that the shelve action is skipped when instance is gone.

        Deletes the instance before executing the action plan. The
        pre_condition check should detect the missing instance and mark
        the action as SKIPPED, leaving the action plan in SUCCEEDED state.
        """
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        source_host = self.get_enabled_compute_nodes()[0]['host']
        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        actions = [
            {
                "action_type": "shelve",
                "resource_id": instance['id'],
                "input_parameters": {}
            }
        ]

        self.wait_for_all_action_plans_to_finish()

        audit_template = self.create_audit_template_for_strategy()
        audit = self.create_audit_and_wait(
            audit_template['uuid'], parameters={"actions": actions})

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]
        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        # Delete the instance before execution so pre_condition skips.
        self._delete_instance(instance['id'])

        _, updated_ap = self.client.start_action_plan(action_plan['uuid'])
        self.assertIn(updated_ap['state'], ('PENDING', 'ONGOING'))

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plan_finished, action_plan['uuid']),
            duration=CONF.optimize.resource_timeout,
            sleep_for=CONF.optimize.resource_check_interval
        ))

        _, finished_ap = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=finished_ap['uuid'])

        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        action_states = [a['state'] for a in action_list['actions']]
        self.assertIn('SKIPPED', action_states)
