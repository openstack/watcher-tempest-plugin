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

from tempest.lib import decorators

from watcher_tempest_plugin.tests.api.admin import base


class TestShowListGoal(base.BaseInfraOptimTest):
    """Tests for goals"""

    DUMMY_GOAL = "dummy"

    @classmethod
    def resource_setup(cls):
        super(TestShowListGoal, cls).resource_setup()

    def assert_expected(self, expected, actual,
                        keys=('created_at', 'updated_at', 'deleted_at')):
        super(TestShowListGoal, self).assert_expected(
            expected, actual, keys)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('1962c7cf-eb84-468a-8386-53166f4b2c9f')
    def test_show_goal(self):
        _, goal = self.client.show_goal(self.DUMMY_GOAL)

        self.assertEqual(self.DUMMY_GOAL, goal['name'])
        expected_fields = {
            'created_at', 'deleted_at', 'display_name',
            'efficacy_specification', 'links', 'name',
            'updated_at', 'uuid'}
        self.assertEqual(expected_fields, set(goal.keys()))

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('a2a9b467-0ba3-4902-9f93-c4d6a43bea94')
    def test_show_goal_with_links(self):
        _, goal = self.client.show_goal(self.DUMMY_GOAL)
        self.assertIn('links', goal.keys())
        self.assertEqual(2, len(goal['links']))
        self.assertIn(goal['uuid'],
                      goal['links'][0]['href'])

    @decorators.attr(type="smoke")
    @decorators.idempotent_id('99dca2f7-091b-4de5-b455-0b15786fabca')
    def test_list_goals(self):
        _, body = self.client.list_goals()
        self.assertIn(self.DUMMY_GOAL,
                      [i['name'] for i in body['goals']])

        # Verify self links.
        for goal in body['goals']:
            self.validate_self_link('goals', goal['uuid'],
                                    goal['links'][0]['href'])
