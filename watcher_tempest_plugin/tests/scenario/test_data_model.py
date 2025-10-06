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

from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF


class TestDataModel(base.BaseInfraOptimScenarioTest):
    """Tests for data models with instances"""

    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST
    # Minimal version required for listing data model
    min_microversion = "1.3"

    @classmethod
    def resource_setup(cls):
        super(TestDataModel, cls).resource_setup()
        if CONF.compute.min_compute_nodes < 1:
            raise cls.skipException(
                "Data model tests requires at least 1 compute node, "
                "skipping tests.")

        enabled_compute_nodes = cls.get_enabled_compute_nodes()
        cls.wait_for_compute_node_setup()

        if len(enabled_compute_nodes) < 1:
            raise cls.skipException(
                "Data model tests requires at least 1 enabled compute "
                "node, skipping tests.")

    @decorators.idempotent_id('dabd41a4-e668-43c8-89a2-3d231e2ed79d')
    def test_data_model_with_instances(self):
        self.addCleanup(self.wait_delete_instances_from_model)

        instances = self._create_one_instance_per_host()

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        _, body = self.client.list_data_models(data_model_type="compute")

        self.assertEqual(len(instances), len(body['context']))

        context_keys = body['context'][0].keys()

        # Check some of the fields available in 1.3, including server fields
        expected_fields = set([
            'node_hostname', 'node_uuid', 'node_vcpus', 'node_memory',
            'node_status', 'node_state', 'server_uuid', 'server_state',
            'server_vcpus', 'server_memory'])
        self.assertTrue(expected_fields.issubset(set(context_keys)))

        # Sanity check in content returned by the data model
        for instance in instances:
            server_ctx = [elem for elem in body['context']
                          if elem['server_uuid'] == instance['id']][0]
            node_details = self.get_hypervisor_details(
                instance['OS-EXT-SRV-ATTR:host'])

            self.assertEqual(server_ctx['node_hostname'],
                             node_details['hypervisor_hostname'])
            self.assertEqual(server_ctx['node_uuid'], node_details['id'])
            self.assertEqual(server_ctx['node_vcpus'], node_details['vcpus'])
            self.assertEqual(server_ctx['node_memory'],
                             node_details['memory_mb'])
            self.assertEqual(server_ctx['node_status'], node_details['status'])
            self.assertEqual(server_ctx['node_state'], node_details['state'])

            self.assertEqual(server_ctx['server_uuid'], instance['id'])
            self.assertEqual(server_ctx['server_vcpus'],
                             instance['flavor']['vcpus'])
            self.assertEqual(server_ctx['server_memory'],
                             instance['flavor']['ram'])
