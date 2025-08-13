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

from oslo_log import log
from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base
from watcher_tempest_plugin import utils


CONF = config.CONF
LOG = log.getLogger(__name__)


class TestDataModelBase(base.BaseInfraOptimScenarioTest):
    """Base class for data model tests"""

    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST
    # Minimal version required for listing data model
    min_microversion = "1.3"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if CONF.compute.min_compute_nodes < 1:
            raise cls.skipException(
                "Data model tests requires at least 1 compute node, "
                "skipping tests.")


class TestDataModel(TestDataModelBase):
    """Tests for data models with instances"""

    @decorators.idempotent_id('dabd41a4-e668-43c8-89a2-3d231e2ed79d')
    def test_data_model_with_instances(self):
        # This test requires at least one enabled compute node
        self.check_min_enabled_compute_nodes(1)
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


class TestDataModelWithExtendedAttributes(TestDataModelBase):
    """Tests for compute data model with extended attributes"""

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.optimize.run_extended_attributes_tests:
            raise cls.skipException(
                "Extended attributes for compute model tests "
                "are not enabled.")

    # Minimal version required for extended attributes
    min_microversion = "1.6"

    @decorators.idempotent_id('788d4f08-6caa-4099-8d04-0c8e41ba0fdc')
    def test_data_model_with_extended_attributes(self):
        # This test requires at least one enabled compute node
        self.check_min_enabled_compute_nodes(1)
        self.addCleanup(self.wait_delete_instances_from_model)

        compute_node = self.get_enabled_compute_nodes()[0]
        kwargs_server = {'host': compute_node['host'],
                         'availability_zone': compute_node['zone']}
        flavor_id = CONF.compute.flavor_ref

        instance = self.create_server(
            image_id=CONF.compute.image_ref, flavor=flavor_id,
            wait_until='ACTIVE', clients=self.os_admin, **kwargs_server)

        # check that the instance is in the model
        self.wait_for_instances_in_model([instance])

        # Wait until we get flavor_extra_specs updated in model
        self.wait_for_instances_attributes_in_model(
            [instance], {'server_flavor_extra_specs':
                         instance['flavor']['extra_specs']})

        _, body = self.client.list_data_models(data_model_type="compute")

        # NOTE(dviroel): even with one instance, the result can contain
        # more elements than represent other compute nodes.
        server_ctx = [inst for inst in body['context']
                      if inst.get('server_uuid') == instance['id']][0]

        context_keys = server_ctx.keys()
        # Check some of the fields available in 1.3, including server fields
        expected_fields = set([
            'node_hostname', 'node_uuid', 'node_vcpus', 'node_memory',
            'server_uuid', 'server_state', 'server_vcpus', 'server_memory'])
        self.assertTrue(expected_fields.issubset(set(context_keys)))

        # New fields added in 1.6
        new_fields = set(['server_pinned_az', 'server_flavor_extra_specs'])
        self.assertTrue(new_fields.issubset(set(context_keys)))

        if (utils.is_microversion_le(
                base.NOVA_API_VERSION_SERVER_PINNED_AZ,
                CONF.compute.max_microversion)):

            # Wait until we get server_pinned_az updated in model
            # server_pinned_az can only be updated via collector
            self.wait_for_instances_attributes_in_model(
                [instance], {'server_pinned_az': compute_node['zone']})

        else:
            LOG.warning("Server pinned AZ validation was skipped because "
                        "the configured compute microversion does not "
                        "support `pinned_availability_zone`.")
