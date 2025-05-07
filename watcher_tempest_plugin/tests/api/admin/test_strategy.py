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


class TestShowListStrategy(base.BaseInfraOptimTest):
    """Tests for strategies"""

    DUMMY_STRATEGY = "dummy"

    @classmethod
    def resource_setup(cls):
        super(TestShowListStrategy, cls).resource_setup()

    def assert_expected(self, expected, actual,
                        keys=('created_at', 'updated_at', 'deleted_at')):
        super(TestShowListStrategy, self).assert_expected(
            expected, actual, keys)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('569b6bc9-4dd9-43ae-be8a-fa9fff5b3e8f')
    def test_show_strategy(self):
        _, strategy = self.client.show_strategy(self.DUMMY_STRATEGY)

        self.assertEqual(self.DUMMY_STRATEGY, strategy['name'])
        self.assertIn("display_name", strategy.keys())

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('401fe965-c35f-4d0d-8aa2-b7af815fe31a')
    def test_show_strategy_with_links(self):
        _, strategy = self.client.show_strategy(self.DUMMY_STRATEGY)
        self.assertIn('links', strategy.keys())
        self.assertEqual(2, len(strategy['links']))
        self.assertIn(strategy['uuid'],
                      strategy['links'][0]['href'])

    @decorators.attr(type="smoke")
    @decorators.idempotent_id('cf308bd5-af8d-4112-9962-1d01851c30fd')
    def test_list_strategies(self):
        _, body = self.client.list_strategies()
        self.assertIn('strategies', body)
        strategies = body['strategies']
        self.assertIn(self.DUMMY_STRATEGY,
                      [i['name'] for i in body['strategies']])

        for strategy in strategies:
            self.assertTrue(
                all(val is not None for key, val in strategy.items()
                    if key in ['uuid', 'name', 'display_name', 'goal_uuid']))

        # Verify self links.
        for strategy in body['strategies']:
            self.validate_self_link('strategies', strategy['uuid'],
                                    strategy['links'][0]['href'])
