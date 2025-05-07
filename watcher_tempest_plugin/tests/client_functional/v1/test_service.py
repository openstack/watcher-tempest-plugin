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


class ServiceTests(base.TestCase):
    """Functional tests for service."""

    decision_engine_name = 'watcher-decision-engine'
    applier_name = 'watcher-applier'
    list_fields = ['ID', 'Name', 'Host', 'Status']

    @decorators.idempotent_id('901af2d0-2a18-45b5-bd07-31d221f19259')
    def test_service_list(self):
        raw_output = self.watcher('service list')
        self.assertIn(self.decision_engine_name, raw_output)
        self.assertIn(self.applier_name, raw_output)
        self.assert_table_structure([raw_output], self.list_fields)

    @decorators.idempotent_id('86b6826b-58ee-4338-a294-e0e24e060ef1')
    def test_service_detailed_list(self):
        raw_output = self.watcher('service list --detail')
        self.assertIn(self.decision_engine_name, raw_output)
        self.assertIn(self.applier_name, raw_output)
        self.assert_table_structure([raw_output],
                                    self.list_fields + ['Last seen up'])

    @decorators.idempotent_id('d3b0dc69-290b-4b2d-aaf6-c2768420e125')
    def test_service_show(self):
        # TODO(alexchadin): this method should be refactored since Watcher will
        # get HA support soon.
        raw_output = self.watcher('service show %s'
                                  % self.decision_engine_name)
        self.assertIn(self.decision_engine_name, raw_output)
        self.assert_table_structure([raw_output],
                                    self.list_fields + ['Last seen up'])
        self.assertNotIn(self.applier_name, raw_output)
