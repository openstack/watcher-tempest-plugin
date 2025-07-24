# -*- encoding: utf-8 -*-
# Copyright (c) 2016 b<>com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
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

from watcher_tempest_plugin.tests.api.admin import base


class TestShowListAction(base.BaseInfraOptimTest):
    """Tests for actions"""

    @classmethod
    def resource_setup(cls):
        super(TestShowListAction, cls).resource_setup()
        _, cls.goal = cls.client.show_goal("DUMMY")
        _, cls.audit_template = cls.create_audit_template(cls.goal['uuid'])
        _, cls.audit = cls.create_audit(cls.audit_template['uuid'])

        assert test_utils.call_until_true(
            func=functools.partial(cls.has_audit_finished, cls.audit['uuid']),
            duration=30,
            sleep_for=.5
        )
        _, action_plans = cls.client.list_action_plans(
            audit_uuid=cls.audit['uuid'])
        cls.action_plan = action_plans['action_plans'][0]

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('0390c465-df10-460f-9924-ff3d14779395')
    def test_show_one_action(self):
        _, body = self.client.list_actions(
            action_plan_uuid=self.action_plan["uuid"])
        actions = body['actions']

        _, action = self.client.show_action(actions[0]["uuid"])

        self.assertEqual(self.action_plan["uuid"], action['action_plan_uuid'])
        self.assertEqual("PENDING", action['state'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('a5dd767a-6d4f-4d72-bd58-9ce69a6c327d')
    def test_show_action_with_links(self):
        _, body = self.client.list_actions(
            action_plan_uuid=self.action_plan["uuid"])
        actions = body['actions']

        _, action = self.client.show_action(actions[0]["uuid"])

        self.assertIn('links', action.keys())
        self.assertEqual(2, len(action['links']))
        self.assertIn(action['uuid'], action['links'][0]['href'])

    @decorators.attr(type="smoke")
    @decorators.idempotent_id('530a308a-f590-4af7-832d-1714ee3e4d59')
    def test_list_actions(self):
        _, body = self.client.list_actions()

        # Verify self links.
        for action in body['actions']:
            self.validate_self_link('actions', action['uuid'],
                                    action['links'][0]['href'])

    @decorators.attr(type="smoke")
    @decorators.idempotent_id('570ef821-af69-473d-989d-bbe86b585a78')
    def test_list_actions_by_action_plan(self):
        _, body = self.client.list_actions(
            action_plan_uuid=self.action_plan["uuid"])

        for item in body['actions']:
            self.assertEqual(self.action_plan["uuid"],
                             item['action_plan_uuid'])

        action_counter = collections.Counter(
            act['action_type'] for act in body['actions'])

        # A dummy strategy generates 2 "nop" actions and 1 "sleep" action
        self.assertEqual(3, len(body['actions']))
        self.assertEqual(2, action_counter.get("nop"))
        self.assertEqual(1, action_counter.get("sleep"))

    @decorators.attr(type="smoke")
    @decorators.idempotent_id('5aa8ff0c-aa8c-4488-a246-4e0c98180a69')
    def test_list_actions_by_audit(self):
        _, body = self.client.list_actions(audit_uuid=self.audit["uuid"])

        for item in body['actions']:
            self.assertEqual(self.action_plan["uuid"],
                             item['action_plan_uuid'])

        action_counter = collections.Counter(
            act['action_type'] for act in body['actions'])

        # A dummy strategy generates 2 "nop" actions and 1 "sleep" action
        self.assertEqual(3, len(body['actions']))
        self.assertEqual(2, action_counter.get("nop"))
        self.assertEqual(1, action_counter.get("sleep"))


class TestPatchAction(base.BaseInfraOptimTest):
    """Tests for patch actions"""

    # Minimal version required for Actions Patch API
    min_microversion = "1.5"

    @classmethod
    def setup(cls):
        super(TestPatchAction, cls).setup()

    @classmethod
    def resource_setup(cls):
        super(TestPatchAction, cls).resource_setup()
        _, cls.goal = cls.client.show_goal("DUMMY")
        _, cls.audit_template = cls.create_audit_template(cls.goal['uuid'])
        _, cls.audit = cls.create_audit(cls.audit_template['uuid'])

        assert test_utils.call_until_true(
            func=functools.partial(cls.has_audit_finished, cls.audit['uuid']),
            duration=30,
            sleep_for=.5
        )
        _, action_plans = cls.client.list_action_plans(
            audit_uuid=cls.audit['uuid'])
        cls.action_plan = action_plans['action_plans'][0]

    @decorators.attr(type="smoke")
    @decorators.idempotent_id('e2360342-8042-4faf-a028-5e63fd844387')
    def test_skip_action(self):
        _, body = self.client.list_actions(audit_uuid=self.audit["uuid"])
        actions = body['actions']

        _, action = self.client.show_action(actions[0]["uuid"])
        action_plan = action['action_plan_uuid']

        self.assertEqual("PENDING", action['state'])
        self.client.update_action(
            action['uuid'],
            [{'op': 'replace', 'path': '/state', 'value': 'SKIPPED'},
             {'op': 'replace', 'path': '/status_message',
              'value': 'skipped test'}]
        )
        _, updated_action = self.client.show_action(actions[0]["uuid"])

        self.assertEqual("SKIPPED", updated_action['state'])
        self.assertEqual("Action skipped by user. Reason: skipped test",
                         updated_action['status_message'])

        self.start_action_plan(action_plan)

        _, action_plan = self.client.show_action_plan(action_plan)
        self.assertEqual('SUCCEEDED', action_plan['state'])

        _, final_body = self.client.list_actions(audit_uuid=self.audit["uuid"])
        final_actions = final_body['actions']
        self.assertEqual("SKIPPED", final_actions[0]['state'])
        self.assertEqual("SUCCEEDED", final_actions[1]['state'])
        self.assertEqual("SUCCEEDED", final_actions[2]['state'])
