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

import functools

from tempest.lib.common.utils import test_utils
from tempest.lib import decorators
from tempest.lib import exceptions

from watcher_tempest_plugin.tests.api.admin import base


class TestCreateDeleteExecuteActionPlan(base.BaseInfraOptimTest):
    """Tests for action plans"""

    @decorators.attr(type='smoke')
    def test_create_action_plan(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])
        _, audit = self.create_audit(audit_template['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(self.has_audit_finished, audit['uuid']),
            duration=30,
            sleep_for=.5
        ))
        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        self.assertEqual(audit['uuid'], action_plan['audit_uuid'])
        self.assertEqual('RECOMMENDED', action_plan['state'])

    @decorators.attr(type='smoke')
    def test_execute_action_plan(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])
        _, audit = self.create_audit(audit_template['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(self.has_audit_finished, audit['uuid']),
            duration=30,
            sleep_for=.5
        ))
        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])
        self.assertEqual('RECOMMENDED', action_plan['state'])

        self.start_action_plan(action_plan['uuid'])

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])
        self.assertEqual('SUCCEEDED', action_plan['state'])

    @decorators.attr(type='smoke')
    def test_delete_action_plan(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])
        _, audit = self.create_audit(audit_template['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(self.has_audit_finished, audit['uuid']),
            duration=30,
            sleep_for=.5
        ))
        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        self.client.delete_action_plan(action_plan['uuid'])

        self.assertRaises(exceptions.NotFound, self.client.show_action_plan,
                          action_plan['uuid'])


class TestShowListActionPlan(base.BaseInfraOptimTest):
    """Tests for action_plan."""

    @classmethod
    def resource_setup(cls):
        super(TestShowListActionPlan, cls).resource_setup()
        _, cls.goal = cls.client.show_goal("dummy")
        _, cls.audit_template = cls.create_audit_template(cls.goal['uuid'])
        _, cls.audit = cls.create_audit(cls.audit_template['uuid'])

        assert test_utils.call_until_true(
            func=functools.partial(cls.has_audit_finished, cls.audit['uuid']),
            duration=30,
            sleep_for=.5
        )
        _, action_plans = cls.client.list_action_plans(
            audit_uuid=cls.audit['uuid'])
        if len(action_plans['action_plans']) > 0:
            cls.action_plan = action_plans['action_plans'][0]

    @decorators.attr(type='smoke')
    def test_show_action_plan(self):
        _, action_plan = self.client.show_action_plan(
            self.action_plan['uuid'])

        self.assert_expected(self.action_plan, action_plan)

    @decorators.attr(type='smoke')
    def test_show_action_plan_detail(self):
        _, action_plans = self.client.list_action_plans_detail(
            audit_uuid=self.audit['uuid'])

        action_plan = action_plans['action_plans'][0]

        self.assert_expected(self.action_plan, action_plan)

    @decorators.attr(type='smoke')
    def test_show_action_plan_with_links(self):
        _, action_plan = self.client.show_action_plan(
            self.action_plan['uuid'])
        self.assertIn('links', action_plan.keys())
        self.assertEqual(2, len(action_plan['links']))
        self.assertIn(action_plan['uuid'],
                      action_plan['links'][0]['href'])

    @decorators.attr(type="smoke")
    def test_list_action_plans(self):
        _, body = self.client.list_action_plans()
        self.assertIn(self.action_plan['uuid'],
                      [i['uuid'] for i in body['action_plans']])
        # Verify self links.
        for action_plan in body['action_plans']:
            self.validate_self_link('action_plans', action_plan['uuid'],
                                    action_plan['links'][0]['href'])

    @decorators.attr(type='smoke')
    def test_list_with_limit(self):
        # We create 3 extra audits to exceed the limit we fix
        for _ in range(3):
            self.create_action_plan(self.audit_template['uuid'])

        _, body = self.client.list_action_plans(limit=3)

        next_marker = body['action_plans'][-1]['uuid']

        self.assertEqual(3, len(body['action_plans']))
        self.assertIn(next_marker, body['next'])
