# -*- encoding: utf-8 -*-
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

from tempest.common import waiters
from tempest import config
from tempest.lib.common.utils import test_utils
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF


class TestExecuteSkippedActionsBase(base.BaseInfraOptimScenarioTest):
    """Base class for action precondition validation and skip behavior tests"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "unclassified"
    STRATEGY = "actuator"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.optimize.run_skipped_action_tests:
            raise cls.skipException(
                "Skipped action tests are not enabled."
            )

    def execute_actions_and_validate_states(
            self, actions, expected_action_plan_state,
            expected_actions_dict, pre_execution_hook=None):
        """Create and execute action plan with custom actions.

        :param actions: List of action definitions
        :param expected_action_plan_state: Expected final state of
                                            action plan
        :param expected_actions_dict: Dict mapping states to expected
                                      action types list. Example:
                                      {'SKIPPED': ['migrate'],
                                       'SUCCEEDED': []}
                                      The count is derived from list
                                      length.
        :param pre_execution_hook: Optional callable to run before
                                   execution
        :returns: Tuple of (finished_action_plan, actions_by_state)
        :raises: AssertionError if action plan or action states don't
                 match expected values, or if timeout occurs waiting
                 for completion
        """
        self.wait_for_all_action_plans_to_finish()

        audit_template = self.create_audit_template_for_strategy()
        audit = self.create_audit_and_wait(
            audit_template['uuid'], parameters={"actions": actions})

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]
        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        # Run pre-execution hook if provided (e.g., delete resources)
        if pre_execution_hook:
            pre_execution_hook()

        # Execute the action plan
        _, updated_ap = self.client.start_action_plan(action_plan['uuid'])
        self.assertIn(updated_ap['state'], ('PENDING', 'ONGOING'))

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plan_finished, action_plan['uuid']),
            duration=180,
            sleep_for=1
        ))

        _, finished_ap = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=finished_ap["uuid"])

        # Categorize actions by state
        actions_by_state = collections.defaultdict(list)
        for action in action_list['actions']:
            state = action['state']
            actions_by_state[state].append(action)

        # Validate expected states, counts, and action types
        # Note: expected_actions_dict specifies both the expected action types
        # and their counts (derived from list length).
        # Example: {'SKIPPED': ['migrate'], 'SUCCEEDED': []}
        # Any state not listed in expected_actions_dict is unexpected.
        for state, expected_types in expected_actions_dict.items():
            actual_actions = actions_by_state.get(state, [])
            actual_count = len(actual_actions)
            expected_count = len(expected_types)

            # Verify count matches
            self.assertEqual(
                expected_count, actual_count,
                "Expected %s %s action(s) but got %s" %
                (expected_count, state, actual_count))

            # Verify action types match
            if expected_count > 0:
                actual_types = [a['action_type'] for a in actual_actions]
                for expected_type in expected_types:
                    self.assertIn(expected_type, actual_types,
                                  "Expected action type '%s' in state '%s' "
                                  "but got %s" %
                                  (expected_type, state, actual_types))

        # Verify no unexpected action states
        for state in actions_by_state:
            if state not in expected_actions_dict:
                self.fail("Unexpected action state: %s" % state)

        # Verify action plan final state
        self.assertEqual(expected_action_plan_state, finished_ap['state'],
                         "Action plan should be %s but is %s" %
                         (expected_action_plan_state, finished_ap['state']))

        return finished_ap, actions_by_state


class TestExecuteSkippedActionsInstances(TestExecuteSkippedActionsBase):
    """Tests for action precondition validation for instance-related actions"""

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('d5517c8c-6dcd-4c10-92b0-ffa371812080')
    def test_migrate_instance_deleted(self):
        """Test migration action skipped when instance is deleted"""
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)

        source_host = self.get_enabled_compute_nodes()[0]['host']
        destination_host = self.get_enabled_compute_nodes()[1]['host']

        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        actions = [
            {
                "action_type": "migrate",
                "resource_id": instance['id'],
                "input_parameters": {
                    "migration_type": "live",
                    "source_node": source_host,
                    "destination_node": destination_host
                }
            },
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={'SKIPPED': ['migrate'], 'SUCCEEDED': []},
            pre_execution_hook=functools.partial(
                self._delete_instance, instance['id'])
        )

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('3cb260b6-1211-403c-81f1-b5cbd9f9eebe')
    def test_migrate_wrong_source_host(self):
        """Test migration action skipped when source host is wrong"""
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)

        compute_nodes = self.get_enabled_compute_nodes()
        source_host = compute_nodes[0]['host']
        wrong_source_host = compute_nodes[1]['host']
        destination_host = compute_nodes[1]['host']

        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        actions = [
            {
                "action_type": "migrate",
                "resource_id": instance['id'],
                "input_parameters": {
                    "migration_type": "live",
                    "source_node": wrong_source_host,
                    "destination_node": destination_host
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={'SKIPPED': ['migrate'], 'SUCCEEDED': []}
        )

        # Verify instance remained on original host
        final_host = self.get_host_for_server(instance['id'])
        self.assertEqual(source_host, final_host)

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('c1215a50-e6f8-46a1-acbc-aa94a006cc5e')
    def test_migrate_wrong_destination_host(self):
        """Test migration action fails when destination node is invalid"""
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)

        source_host = self.get_enabled_compute_nodes()[0]['host']
        invalid_destination = "non-existent-host-12345"

        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        actions = [
            {
                "action_type": "migrate",
                "resource_id": instance['id'],
                "input_parameters": {
                    "migration_type": "live",
                    "source_node": source_host,
                    "destination_node": invalid_destination
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='FAILED',
            expected_actions_dict={'FAILED': ['migrate'], 'SUCCEEDED': []}
        )

        # Verify instance remained on source host
        final_host = self.get_host_for_server(instance['id'])
        self.assertEqual(source_host, final_host)

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('36d0e831-546a-4bce-aec3-1b2cfc3c5c6c')
    def test_migrate_live_instance_shutoff(self):
        """Test live migration action fails when instance is SHUTOFF"""
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)

        source_host = self.get_enabled_compute_nodes()[0]['host']
        destination_host = self.get_enabled_compute_nodes()[1]['host']

        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        # Stop the instance to make it SHUTOFF
        self.mgr.servers_client.stop_server(instance['id'])
        waiters.wait_for_server_status(
            self.mgr.servers_client, instance['id'], 'SHUTOFF')

        actions = [
            {
                "action_type": "migrate",
                "resource_id": instance['id'],
                "input_parameters": {
                    "migration_type": "live",
                    "source_node": source_host,
                    "destination_node": destination_host
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='FAILED',
            expected_actions_dict={'FAILED': ['migrate'], 'SUCCEEDED': []}
        )

        # Verify instance remained on source host
        final_host = self.get_host_for_server(instance['id'])
        self.assertEqual(source_host, final_host)

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('831ec131-e7ac-4a8f-b4ce-3615776ee68d')
    def test_nova_service_state_change(self):
        """Test change_nova_service_state skipped when already disabled"""
        self.check_min_enabled_compute_nodes(1)

        compute_nodes = self.get_enabled_compute_nodes()
        target_host = compute_nodes[0]['host']

        services_client = self.mgr.services_client
        services = services_client.list_services(
            host=target_host, binary='nova-compute')['services']
        self.assertGreater(len(services), 0)

        service = services[0]
        service_id = service['id']
        original_status = service['status']

        if original_status == 'enabled':
            services_client.update_service(service_id, status='disabled')
            self.addCleanup(self._restore_service_state, service_id,
                            original_status)

        actions = [
            {
                "action_type": "change_nova_service_state",
                "resource_id": target_host,
                "input_parameters": {
                    "state": "disabled"
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={
                'SKIPPED': ['change_nova_service_state'],
                'SUCCEEDED': []
            }
        )

        # Verify service remained disabled
        services = services_client.list_services(
            host=target_host, binary='nova-compute')['services']
        self.assertEqual('disabled', services[0]['status'])

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('0aa3fc16-7e5f-466d-b149-5d6e1d31747e')
    def test_resize_invalid_instance(self):
        """Test resize action skipped when instance is deleted"""
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        compute_nodes = self.get_enabled_compute_nodes()
        source_host = compute_nodes[0]['host']

        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        # Get default flavor details to create an identical one
        default_flavor_id = CONF.compute.flavor_ref
        default_flavor = self.mgr.flavors_client.show_flavor(
            default_flavor_id)['flavor']

        # Create a flavor identical to the default one
        target_flavor_id = self._create_custom_flavor(
            ram=default_flavor['ram'],
            vcpus=default_flavor['vcpus'])

        actions = [
            {
                "action_type": "resize",
                "resource_id": instance['id'],
                "input_parameters": {
                    "flavor": target_flavor_id
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={'SKIPPED': ['resize'], 'SUCCEEDED': []},
            pre_execution_hook=functools.partial(
                self._delete_instance, instance['id'])
        )

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('1276213c-7a00-47cc-bb69-4c7e83f737ab')
    def test_resize_invalid_flavor(self):
        """Test resize action fails when flavor does not exist"""
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        compute_nodes = self.get_enabled_compute_nodes()
        source_host = compute_nodes[0]['host']

        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        fake_flavor_id = "00000000-0000-0000-0000-000000000000"

        actions = [
            {
                "action_type": "resize",
                "resource_id": instance['id'],
                "input_parameters": {
                    "flavor": fake_flavor_id
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='FAILED',
            expected_actions_dict={'FAILED': ['resize'], 'SUCCEEDED': []}
        )

        # Verify instance remained ACTIVE
        instance_details = self.mgr.servers_client.show_server(
            instance['id'])['server']
        self.assertEqual('ACTIVE', instance_details['status'])

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('e4253725-1bd8-48d0-a702-91656390d013')
    def test_stop_invalid_instance(self):
        """Test stop action skipped when instance is deleted"""
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        compute_nodes = self.get_enabled_compute_nodes()
        source_host = compute_nodes[0]['host']

        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        actions = [
            {
                "action_type": "stop",
                "resource_id": instance['id'],
                "input_parameters": {}
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={'SKIPPED': ['stop'], 'SUCCEEDED': []},
            pre_execution_hook=functools.partial(
                self._delete_instance, instance['id'])
        )

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('800abf49-03b2-419d-afa6-da51aa554901')
    def test_stop_stopped_instance(self):
        """Test stop action skipped when instance is already stopped"""
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        compute_nodes = self.get_enabled_compute_nodes()
        source_host = compute_nodes[0]['host']

        instance = self._create_instance(source_host)
        self.wait_for_instances_in_model([instance])

        self.mgr.servers_client.stop_server(instance['id'])
        waiters.wait_for_server_status(
            self.mgr.servers_client, instance['id'], 'SHUTOFF')

        actions = [
            {
                "action_type": "stop",
                "resource_id": instance['id'],
                "input_parameters": {}
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={'SKIPPED': ['stop'], 'SUCCEEDED': []}
        )

        # Verify instance remained SHUTOFF
        instance_details = self.mgr.servers_client.show_server(
            instance['id'])['server']
        self.assertEqual('SHUTOFF', instance_details['status'])


class TestExecuteSkippedActionsVolumes(TestExecuteSkippedActionsBase):
    """Tests for action precondition validation for volume-related actions"""

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.service_available.cinder:
            raise cls.skipException("Cinder is not available")

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('dc502457-501e-42a7-b31a-9dfb64c9dcf2')
    def test_volume_migrate_invalid_volume(self):
        """Test volume_migration action skipped when volume is deleted"""
        volume = self.create_volume(name="test_volume_migrate_invalid")

        actions = [
            {
                "action_type": "volume_migrate",
                "resource_id": volume['id'],
                "input_parameters": {
                    "migration_type": "migrate",
                    "destination_node": "dummy-pool"
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={
                'SKIPPED': ['volume_migrate'],
                'SUCCEEDED': []
            },
            pre_execution_hook=functools.partial(
                self._delete_volume, volume['id'])
        )

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('eba9c7ec-1865-4d11-89ed-7387e8c6cd84')
    def test_volume_migrate_retype(self):
        """Test volume_migration retype skipped when type is same as current"""

        volume_type = self.create_volume_type()
        type_name = volume_type["name"]

        volume = self.create_volume(
            name="test_volume_retype_same",
            volume_type=type_name)

        actions = [
            {
                "action_type": "volume_migrate",
                "resource_id": volume['id'],
                "input_parameters": {
                    "migration_type": "retype",
                    "destination_type": type_name
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={
                'SKIPPED': ['volume_migrate'],
                'SUCCEEDED': []
            }
        )

        # Verify volume type remained unchanged
        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume['id'])['volume']
        self.assertEqual(type_name, volume_details['volume_type'])

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('5407d063-0f60-4411-b099-2a5ebb357a2b')
    def test_volume_migrate_node(self):
        """Test volume_migration migrate skipped when node is current"""

        volume = self.create_volume(name="test_volume_migrate_same_node")

        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume['id'])['volume']
        current_host = volume_details['os-vol-host-attr:host']

        actions = [
            {
                "action_type": "volume_migrate",
                "resource_id": volume['id'],
                "input_parameters": {
                    "migration_type": "migrate",
                    "destination_node": current_host
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='SUCCEEDED',
            expected_actions_dict={
                'SKIPPED': ['volume_migrate'],
                'SUCCEEDED': []
            }
        )

        # Verify volume host remained unchanged
        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume['id'])['volume']
        self.assertEqual(current_host,
                         volume_details['os-vol-host-attr:host'])

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('3acee916-04b9-4ba0-8a6a-3c0130d18dc9')
    def test_volume_migrate_invalid_type(self):
        """Test volume_migration retype fails when type does not exist"""

        volume = self.create_volume(name="test_volume_retype_invalid")

        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume['id'])['volume']
        original_type = volume_details['volume_type']

        fake_type = "non-existent-volume-type-12345"

        actions = [
            {
                "action_type": "volume_migrate",
                "resource_id": volume['id'],
                "input_parameters": {
                    "migration_type": "retype",
                    "destination_type": fake_type
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='FAILED',
            expected_actions_dict={
                'FAILED': ['volume_migrate'],
                'SUCCEEDED': []
            }
        )

        # Verify volume type remained unchanged
        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume['id'])['volume']
        self.assertEqual(original_type, volume_details['volume_type'])

    @decorators.attr(type=['strategy', 'actuator'])
    @decorators.idempotent_id('3108b311-b84c-45ea-8478-702c308c24fe')
    def test_volume_migrate_invalid_node(self):
        """Test volume_migration migrate fails when node does not exist"""

        volume = self.create_volume(name="test_volume_migrate_invalid_node")

        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume['id'])['volume']
        original_host = volume_details['os-vol-host-attr:host']

        fake_node = "non-existent-pool-12345"

        actions = [
            {
                "action_type": "volume_migrate",
                "resource_id": volume['id'],
                "input_parameters": {
                    "migration_type": "migrate",
                    "destination_node": fake_node
                }
            }
        ]

        self.execute_actions_and_validate_states(
            actions,
            expected_action_plan_state='FAILED',
            expected_actions_dict={
                'FAILED': ['volume_migrate'],
                'SUCCEEDED': []
            }
        )

        # Verify volume host remained unchanged
        volume_details = self.os_admin.volumes_client_latest.show_volume(
            volume['id'])['volume']
        self.assertEqual(original_host,
                         volume_details['os-vol-host-attr:host'])
