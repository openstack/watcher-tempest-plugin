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

from tempest.lib.common.utils import test_utils
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base


class TestExecuteDummyStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for action plans"""

    @decorators.idempotent_id('77884962-8739-422f-8471-6c9227e8481f')
    def test_execute_dummy_action_plan(self):
        """Execute an action plan based on the 'dummy' strategy

        - create an audit template with the 'dummy' strategy
        - run the audit to create an action plan
        - get the action plan
        - run the action plan
        - get results and make sure it succeeded
        """
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plans_finished),
            duration=600,
            sleep_for=2
        ))

        _, audit = self.create_audit(audit_template['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(self.has_audit_finished, audit['uuid']),
            duration=60,
            sleep_for=2
        ))

        self.assertTrue(self.has_audit_succeeded(audit['uuid']))

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        if action_plan['state'] in ['SUPERSEDED', 'SUCCEEDED']:
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return

        # Execute the action by changing its state to PENDING
        _, updated_ap = self.client.start_action_plan(action_plan['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plan_finished, action_plan['uuid']),
            duration=60,
            sleep_for=2
        ))
        _, finished_ap = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=finished_ap["uuid"])

        action_counter = collections.Counter(
            act['action_type'] for act in action_list['actions'])

        self.assertIn(updated_ap['state'], ('PENDING', 'ONGOING'))
        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        # A dummy strategy generates 2 "nop" actions and 1 "sleep" action
        self.assertEqual(3, len(action_list['actions']))
        self.assertEqual(2, action_counter.get("nop"))
        self.assertEqual(1, action_counter.get("sleep"))
