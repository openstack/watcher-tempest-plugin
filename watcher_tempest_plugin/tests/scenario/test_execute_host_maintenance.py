# -*- encoding: utf-8 -*-
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

from oslo_log import log
from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = log.getLogger(__name__)


class TestExecuteHostMaintenanceStrategyBase(base.BaseInfraOptimScenarioTest):
    """Base class for host_maintenance tests"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "cluster_maintaining"
    STRATEGY = "host_maintenance"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")


class TestExecuteHostMaintenanceStrategy(
        TestExecuteHostMaintenanceStrategyBase):
    """Tests for host_maintenance"""

    @decorators.idempotent_id('17afd352-1929-46dd-a10a-63c90bb9255d')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_execute_host_maintenance_strategy(self):
        # This test does not require metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])

        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node
            }
        }
        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['change_nova_service_state', 'migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

    @decorators.idempotent_id('cc5a0f1b-e8d2-4813-b012-874982d15d06')
    @decorators.attr(type=['strategy', 'host_maintenance'])
    def test_execute_host_maintenance_strategy_backup_node(self):
        # This test does not require metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        instances = self._create_one_instance_per_host()
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])
        dst_node = self.get_host_other_than(instances[0]['id'])

        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node,
                "backup_node": dst_node
            }
        }

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['change_nova_service_state', 'migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

        # Make sure server is migrated to backup node
        self.assertEqual(
            self.get_host_for_server(instances[0]['id']),
            dst_node
        )


class TestExecuteHostMaintenanceStrategyBfV(
        TestExecuteHostMaintenanceStrategyBase):
    """Tests for host_maintenance with boot from volume instances"""

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.service_available.cinder:
            raise cls.skipException("Cinder is not available")
        if not CONF.optimize.run_bfv_tests:
            raise cls.skipException(
                "Boot from volume tests are not enabled."
            )

    @decorators.attr(type=['strategy', 'host_maintenance'])
    @decorators.idempotent_id('c2da0904-2acd-4ab8-bf88-f62294856bb6')
    def test_execute_host_maintenance_strategy_backup_node_bfv(self):
        # Watcher host maintenance strategy checks if the instance fits
        # in the destination host when using the backup node.
        # In Boot from Volume instances, the accounting
        # of local disk differs from boot from image as root disk is not
        # taken from the compute node local disk. This test is intended to
        # validate this case by creating a flavor with disk size larger than
        # the available disk in the destination host.

        # This test does not require metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.rollback_compute_nodes_status)
        self.addCleanup(self.wait_delete_instances_from_model)
        # Create a flavor with disk size larger than the available disk
        host = self.get_enabled_compute_nodes()[0]['host']
        hypervisor = self.get_hypervisor_details(host)
        disk_inventory = self.get_resource_provider_inventory(
            hypervisor['id'])['DISK_GB']
        available_disk = (disk_inventory['total']
                          * disk_inventory['allocation_ratio'])
        flavor_disk = int(available_disk) + 2
        flavor_id = self._create_custom_flavor(disk=flavor_disk)

        instances = self._create_one_instance_per_host(
            flavor=flavor_id, boot_from_volume=True)
        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        src_node = self.get_host_for_server(instances[0]['id'])
        dst_node = self.get_host_other_than(instances[0]['id'])

        audit_kwargs = {
            "parameters": {
                "maintenance_node": src_node,
                "backup_node": dst_node
            }
        }

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['change_nova_service_state', 'migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        # This test is starting and validating the success of the action plan
        # to validate the actual live migration works in BfV instances.
        self.execute_action_plan_and_validate_states(action_plan['uuid'])

        # Make sure server is migrated to backup node
        self.assertEqual(
            self.get_host_for_server(instances[0]['id']),
            dst_node
        )
