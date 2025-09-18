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

from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base


class TestExecuteDummyStrategy(base.BaseInfraOptimScenarioTest):
    """Tests for action plans"""

    @decorators.attr(type=['strategy', 'dummy'])
    @decorators.idempotent_id('a660e484-da76-478c-b18c-2eff243dde48')
    def test_execute_dummy_strategy(self):
        """Execute an action plan based on the 'dummy' strategy

        - create an audit template with the 'dummy' strategy
        - run the audit to create an action plan
        - get the action plan
        - run the action plan
        - get results and make sure it succeeded
        """

        audit_kwargs = dict()

        self.execute_strategy("dummy", "dummy",
                              expected_actions=['sleep', 'nop'],
                              **audit_kwargs)
