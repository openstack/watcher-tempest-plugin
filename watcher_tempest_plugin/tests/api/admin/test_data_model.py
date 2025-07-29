# Copyright 2025 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from tempest.lib import decorators
from tempest.lib import exceptions

from watcher_tempest_plugin.tests.api.admin import base


class TestListDataModel(base.BaseInfraOptimTest):
    """Tests for data models"""

    min_microversion = "1.3"

    @classmethod
    def resource_setup(cls):
        super(TestListDataModel, cls).resource_setup()

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('61b54061-d68c-4179-bb00-d72c97373224')
    def test_list_data_models(self):
        _, body = self.client.list_data_models()

        self.assertIn('context', body)

        # NOTE(dviroel): list data model returns at least
        # one element for each compute node. But we don't want to
        # if there is no enabled compute nodes.
        if len(body['context']) > 0:
            context_keys = body['context'][0].keys()
            # assert that the context has some of the expected fields
            # note that since we don't have any instances, we don't have
            # server fields available
            expected_fields = set([
                'node_hostname', 'node_uuid', 'node_vcpus', 'node_memory',
                'node_state', 'node_vcpu_ratio', 'node_vcpu_reserved'])
            self.assertTrue(expected_fields.issubset(set(context_keys)))


class TestNegativeListDataModel(base.BaseInfraOptimTest):
    """Negative tests for data models"""

    min_microversion = "1.3"

    @classmethod
    def resource_setup(cls):
        super(TestNegativeListDataModel, cls).resource_setup()

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('dd0f7313-e170-4de8-b9ce-840ef3cfdd5f')
    def test_list_data_models_storage(self):

        self.assertRaises(exceptions.NotFound, self.client.list_data_models,
                          data_model_type="storage")
