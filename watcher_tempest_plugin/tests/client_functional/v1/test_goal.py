# Copyright (c) 2016 Servionica
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

from tempest.lib import decorators

from watcher_tempest_plugin.tests.client_functional.v1 import base


class GoalTests(base.TestCase):
    """Functional tests for goal."""

    dummy_name = 'dummy'
    list_fields = ['UUID', 'Name', 'Display name']

    @decorators.idempotent_id('53046516-5ddb-41b7-ab43-0dac13f964b1')
    def test_goal_list(self):
        raw_output = self.watcher('goal list')
        self.assertIn(self.dummy_name, raw_output)
        self.assert_table_structure([raw_output], self.list_fields)

    @decorators.idempotent_id('cb88a7fd-c19f-47fd-96e0-51cff152f77f')
    def test_goal_detailed_list(self):
        raw_output = self.watcher('goal list --detail')
        self.assertIn(self.dummy_name, raw_output)
        self.assert_table_structure(
            [raw_output], self.list_fields + ['Efficacy specification'])

    @decorators.idempotent_id('98645ffb-2450-43ce-ad8c-c616720f0471')
    def test_goal_show(self):
        raw_output = self.watcher('goal show %s' % self.dummy_name)
        self.assertIn(self.dummy_name, raw_output)
        self.assert_table_structure(
            [raw_output], self.list_fields + ['Efficacy specification'])
        self.assertNotIn('server_consolidation', raw_output)
