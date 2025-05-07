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


class ScoringEngineTests(base.TestCase):
    """Functional tests for scoring engine."""

    dummy_name = 'dummy_scorer'
    list_fields = ['UUID', 'Name', 'Description']
    detailed_list_fields = list_fields + ['Metainfo']

    @decorators.idempotent_id('87b34f07-df9a-49c9-a229-4aba831368b1')
    def test_scoringengine_list(self):
        raw_output = self.watcher('scoringengine list')
        self.assertIn(self.dummy_name, raw_output)
        self.assert_table_structure([raw_output], self.list_fields)

    @decorators.idempotent_id('ab987528-f56e-49ef-8463-0f4c023aaf48')
    def test_scoringengine_detailed_list(self):
        raw_output = self.watcher('scoringengine list --detail')
        self.assertIn(self.dummy_name, raw_output)
        self.assert_table_structure([raw_output], self.detailed_list_fields)

    @decorators.idempotent_id('f12b0cb7-808b-4ced-bb69-f18d6ab6ef0f')
    def test_scoringengine_show(self):
        raw_output = self.watcher('scoringengine show %s' % self.dummy_name)
        self.assertIn(self.dummy_name, raw_output)
        self.assert_table_structure([raw_output], self.detailed_list_fields)
        self.assertNotIn('dummy_avg_scorer', raw_output)
