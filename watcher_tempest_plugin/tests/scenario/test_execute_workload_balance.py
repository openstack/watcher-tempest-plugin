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

import copy
import math

from oslo_log import log
from tempest import config
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = log.getLogger(__name__)


class TestExecuteWorkloadBalanceStrategyBase(base.BaseInfraOptimScenarioTest):
    """Tests for workload_balance"""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    GOAL = "workload_balancing"
    STRATEGY = "workload_balance"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")
        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")


class TestExecuteWorkloadBalanceStrategy(
        TestExecuteWorkloadBalanceStrategyBase):
    """Tests for workload_balance"""

    @decorators.attr(type=['strategy', 'workload_balance'])
    @decorators.idempotent_id('64a9293f-0f81-431c-afae-ecabebae53f1')
    def test_execute_workload_balance_strategy_cpu(self):
        # This test requires metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)
        host = self.get_enabled_compute_nodes()[0]['host']
        hypervisor = self.get_hypervisor_details(host)
        instances = []
        created_instances = 2
        flavor_id = self._create_custom_flavor(ephemeral=1, swap=128)
        for _ in range(created_instances):
            instance = self._create_instance(host, flavor=flavor_id)
            instances.append(instance)

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        for instance in instances:
            # Inject metrics after the instances are created
            self.make_instance_statistic(instance)

        # Set a threshold for CPU usage
        # ( <number of vms> - 0.5 ) * (0.8/<vcpus of the compute host>)*100
        threshold = round(
            (created_instances - 0.5) * (0.8 / int(hypervisor['vcpus'])) * 100)

        audit_parameters = {
            "metrics": "instance_cpu_usage",
            "threshold": threshold,
            "period": 300,
            "granularity": 300}

        audit_kwargs = {"parameters": audit_parameters}

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

    @decorators.attr(type=['strategy', 'workload_balance'])
    @decorators.idempotent_id('de4f662a-26b1-4cbe-ba8e-c213bac0a996')
    def test_execute_workload_balance_strategy_ram(self):
        # This test requires metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)

        host = self.get_enabled_compute_nodes()[0]['host']
        hypervisor = self.get_hypervisor_details(host)
        # Flavor RAM is set to 15% of the hypervisor memory
        ram = int(hypervisor['memory_mb'] * 0.15)
        flavor_id = self._create_custom_flavor(ram=ram)
        instances = []
        for _ in range(2):
            instance = self._create_instance(host=host, flavor=flavor_id)
            instances.append(instance)

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        for instance in instances:
            # Inject metrics after the instances are created
            self.make_instance_statistic(instance)

        audit_parameters = {
            "metrics": "instance_ram_usage",
            "threshold": 18,
            "period": 300,
            "granularity": 300}

        audit_kwargs = {"parameters": audit_parameters}

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])


class TestExecuteWorkloadBalanceStrategyBfV(
        TestExecuteWorkloadBalanceStrategyBase):
    """Tests for workload_balance with boot from volume instances"""

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.service_available.cinder:
            raise cls.skipException("Cinder is not available")
        if not CONF.optimize.run_bfv_tests:
            raise cls.skipException(
                "Boot from volume tests are not enabled."
            )

    @decorators.attr(type=['strategy', 'workload_balance'])
    @decorators.idempotent_id('5686b82d-462b-4298-bdb7-563309406848')
    def test_execute_workload_balance_strategy_cpu_bfv(self):
        # Watcher worklkoad balance strategy checks available disk in the
        # destination host. In Boot from Volume instances, the accounting
        # of local disk differs from boot from image as root disk is not
        # taken from the compute node local disk. This test is intended to
        # validate this case by creating a flavor with disk size larger than
        # the available disk in the destination host.

        # This test requires metrics injection
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)
        host = self.get_enabled_compute_nodes()[0]['host']
        hypervisor = self.get_hypervisor_details(host)
        # Let's create the flavor with disk size larger than the available disk
        disk_inventory = self.get_resource_provider_inventory(
            hypervisor['id'])['DISK_GB']
        available_disk = (disk_inventory['total']
                          * disk_inventory['allocation_ratio'])
        flavor_disk = int(available_disk) + 2
        flavor_id = self._create_custom_flavor(
            disk=flavor_disk, ephemeral=1, swap=128)

        instances = []
        created_instances = 2
        for _ in range(created_instances):
            instance = self._create_instance(
                host, flavor=flavor_id, boot_from_volume=True)
            instances.append(instance)

        # wait for compute model updates
        self.wait_for_instances_in_model(instances)

        for instance in instances:
            # Inject metrics after the instances are created
            self.make_instance_statistic(instance)

        # Set a threshold for CPU usage
        threshold = round(
            (created_instances - 0.5) * (0.8 / int(hypervisor['vcpus'])) * 100)

        audit_parameters = {
            "metrics": "instance_cpu_usage",
            "threshold": threshold,
            "period": 300,
            "granularity": 300}

        audit_kwargs = {"parameters": audit_parameters}

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'], ['migrate'])

        self.assertEqual("RECOMMENDED", action_plan['state'])

        self.execute_action_plan_and_validate_states(action_plan['uuid'])

    @decorators.attr(type=['strategy', 'workload_balance'])
    @decorators.idempotent_id('8c72586c-eedd-4b99-91b6-97d24636d116')
    def test_execute_workload_balance_strategy_ram_bfv_disk_full(self):
        # This test validates that the workload_balance strategy produces
        # an empty action plan when BfV instances use a flavor whose
        # ephemeral disk exceeds 40% of the host disk capacity.
        # With two such instances per host, the destination node cannot
        # accommodate a migration because its local disk is already
        # consumed by its own instances' ephemeral storage.

        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)
        self.addCleanup(self.clean_injected_metrics)

        nodes = self.get_enabled_compute_nodes()
        host_loaded = nodes[0]['host']
        hypervisor = self.get_hypervisor_details(host_loaded)
        # Hosts other than the loaded host.
        hosts_other = copy.deepcopy(nodes)
        hosts_other.pop(0)

        disk_inventory = self.get_resource_provider_inventory(
            hypervisor['id'])['DISK_GB']
        available_disk = ((disk_inventory['total']
                           - disk_inventory['reserved'])
                          * disk_inventory['allocation_ratio'])

        # Each instance uses 40% of the host disk via ephemeral disks
        # so that there is not enough disk space for three instances.
        flavor_ephemeral_size = math.ceil(available_disk * 0.40)
        # ram is set to 15% of the hypervisor memory as it will be used
        # as metric for the workload_balance strategy.
        ram = int(hypervisor['memory_mb'] * 0.15)

        flavor_id = self._create_custom_flavor(
            disk=1,
            ephemeral=flavor_ephemeral_size,
            ram=ram,
            swap=128)

        instances = []
        loaded_instances = []
        created_instances = 2
        for _ in range(created_instances):
            instance = self._create_instance(
                host_loaded, flavor=flavor_id)
            instances.append(instance)
            loaded_instances.append(instance)

        for host in hosts_other:
            for _ in range(created_instances):
                instance = self._create_instance(
                    host['host'], flavor=flavor_id)
                instances.append(instance)

        self.wait_for_instances_in_model(instances)

        for instance in loaded_instances:
            self.make_instance_statistic(instance)

        self.make_host_statistic(loaded_hosts=[host_loaded])

        audit_parameters = {
            "metrics": "instance_ram_usage",
            "threshold": 18,
            "period": 300,
            "granularity": 300}

        audit_kwargs = {"parameters": audit_parameters}

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, actions = self.get_action_plan_and_validate_actions(
            audit['uuid'])

        self.assertEqual("SUCCEEDED", action_plan['state'])
        self.assertEqual(0, len(actions))
