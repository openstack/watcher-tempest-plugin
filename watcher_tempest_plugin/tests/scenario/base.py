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
#

import functools
import json
import random
import time

from datetime import datetime
from datetime import timedelta
import os_traits
from oslo_log import log
from tempest.common import waiters
from tempest import config
from tempest.lib.common import api_microversion_fixture
from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils
from tempest.lib import exceptions
from tempest.scenario import manager

from watcher_tempest_plugin import infra_optim_clients as clients


LOG = log.getLogger(__name__)
CONF = config.CONF


class BaseInfraOptimScenarioTest(manager.ScenarioTest):
    """Base class for Infrastructure Optimization API tests."""

    # States where the object is waiting for some event to perform a transition
    IDLE_STATES = ('RECOMMENDED', 'FAILED', 'SUCCEEDED', 'CANCELLED')
    # States where the object can only be DELETED (end of its life-cycle)
    AUDIT_FINISHED_STATES = ('FAILED', 'SUCCEEDED', 'CANCELLED', 'SUSPENDED')
    # States where the object can only be DELETED (end of its life-cycle)
    AP_FINISHED_STATES = ('FAILED', 'SUCCEEDED', 'CANCELLED', 'SUPERSEDED')

    # Metric map used to add or retrieve metrics on Prometheus
    # NOTE(dviroel): This maps metrics consumed from Prometheus server,
    #  but the datasource may support other metrics from the model.
    PROMETHEUS_METRIC_MAP = dict(
        host_cpu_usage='node_cpu_seconds_total',
        host_ram_usage='node_memory_MemAvailable_bytes',
        instance_cpu_usage='ceilometer_cpu',
        instance_ram_usage='ceilometer_memory_usage')

    # Metric map used to add or retrieve metrics on Gnocchi
    GNOCCHI_METRIC_MAP = dict(
        host_cpu_usage='compute.node.cpu.percent',
        host_ram_usage='hardware.memory.used',
        host_outlet_temp='hardware.ipmi.node.outlet_temperature',
        host_inlet_temp='hardware.ipmi.node.temperature',
        host_airflow='hardware.ipmi.node.airflow',
        host_power='hardware.ipmi.node.power',
        instance_cpu_usage='cpu',
        instance_ram_usage='memory.resident',
        instance_ram_allocated='memory',
        instance_l3_cache_usage='cpu_l3_cache',
        instance_root_disk_size='disk.root.size',)

    @classmethod
    def skip_checks(cls):
        super(manager.ScenarioTest, cls).skip_checks()
        if not CONF.service_available.watcher:
            raise cls.skipException('Watcher support is required')

    @classmethod
    def setup_credentials(cls):
        cls._check_network_config()
        super(BaseInfraOptimScenarioTest, cls).setup_credentials()
        cls.mgr = clients.AdminManager()

    @classmethod
    def setup_clients(cls):
        super(BaseInfraOptimScenarioTest, cls).setup_clients()
        cls.client = cls.mgr.io_client
        cls.gnocchi = cls.mgr.gn_client
        cls.placement_client = cls.mgr.placement_client
        cls.prometheus_client = cls.mgr.prometheus_client

    def setUp(self):
        super(BaseInfraOptimScenarioTest, self).setUp()
        self.useFixture(api_microversion_fixture.APIMicroversionFixture(
            compute_microversion=CONF.compute.min_microversion))
        self.useFixture(api_microversion_fixture.APIMicroversionFixture(
            placement_microversion=CONF.placement.min_microversion))

    @classmethod
    def resource_setup(cls):
        super(BaseInfraOptimScenarioTest, cls).resource_setup()

    @classmethod
    def resource_cleanup(cls):
        """Ensure that all created objects get destroyed."""
        super(BaseInfraOptimScenarioTest, cls).resource_cleanup()

    @classmethod
    def get_hypervisors_setup(cls):
        hypervisors_client = cls.mgr.hypervisor_client
        hypervisors = hypervisors_client.list_hypervisors(
            detail=True)['hypervisors']
        return hypervisors

    @classmethod
    def get_compute_nodes_setup(cls):
        services_client = cls.mgr.services_client
        available_services = services_client.list_services()['services']

        return [srv for srv in available_services
                if srv.get('binary') == 'nova-compute']

    @classmethod
    def wait_for_compute_node_setup(cls):

        def _are_compute_nodes_setup():
            try:
                hypervisors = cls.get_hypervisors_setup()
                available_hypervisors = set(
                    hyp['hypervisor_hostname'] for hyp in hypervisors
                    if hyp['state'] == 'up')
                available_services = set(
                    service['host']
                    for service in cls.get_compute_nodes_setup()
                    if service['state'] == 'up')
                return (
                    len(available_hypervisors) == len(available_services)
                    and len(hypervisors) >= 2)
            except Exception as exc:
                LOG.exception(exc)
                return False

        assert test_utils.call_until_true(
            func=_are_compute_nodes_setup,
            duration=600,
            sleep_for=2
        )

    @classmethod
    def rollback_compute_nodes_status(cls):
        current_compute_nodes_setup = cls.get_compute_nodes_setup()
        for cn_setup in current_compute_nodes_setup:
            cn_hostname = cn_setup.get('host')
            matching_cns = [
                cns for cns in cls.initial_compute_nodes_setup
                if cns.get('host') == cn_hostname
            ]
            initial_cn_setup = matching_cns[0]  # Should return a single result
            if cn_setup.get('status') != initial_cn_setup.get('status'):
                svr_id = cn_setup.get('id')
                status = initial_cn_setup.get('status')
                # The Nova version Watcher neede is at least 2.56
                # Starting with microversion 2.53 disable/enable API
                # is superseded by PUT /os-services/{service_id}
                rollback_func = cls.mgr.services_client.update_service
                rollback_func(svr_id, status=status)

    @classmethod
    def wait_for(cls, condition, timeout=30):
        start_time = time.time()
        while time.time() - start_time < timeout:
            if condition():
                break
            time.sleep(.5)

    @classmethod
    def _check_network_config(cls):
        if not CONF.network.public_network_id:
            msg = 'public network not defined.'
            LOG.error(msg)
            raise exceptions.InvalidConfiguration(msg)

    @classmethod
    def _are_all_action_plans_finished(cls):
        _, action_plans = cls.client.list_action_plans()
        return all([ap['state'] in cls.AP_FINISHED_STATES
                    for ap in action_plans['action_plans']])

    def wait_for_all_action_plans_to_finish(self):
        assert test_utils.call_until_true(
            func=self._are_all_action_plans_finished,
            duration=300,
            sleep_for=5
        )

    def _migrate_server_to(self, server_id, dest_host):
        # The default value of  block_migration is auto and
        # disk_over_commit is not valid after version 2.25
        block_migration = 'auto'
        body = self.mgr.servers_client.live_migrate_server(
            server_id, host=dest_host, block_migration=block_migration)
        return body

    def _live_migrate(self, server_id, target_host, state):
        self._migrate_server_to(server_id, target_host)
        waiters.wait_for_server_status(self.servers_client, server_id, state)
        migration_list = (self.mgr.migrations_client.list_migrations()
                          ['migrations'])

        msg = ("Live Migration failed. Migrations list for Instance "
               "%s: [" % server_id)
        for live_migration in migration_list:
            if (live_migration['instance_uuid'] == server_id):
                msg += "\n%s" % live_migration
        msg += "]"
        server_host = self.mgr.servers_client.show_server(
            server_id)['server']['OS-EXT-SRV-ATTR:host']

        self.assertEqual(target_host, server_host, msg)

    def _create_one_instance_per_host_with_statistic(self, metrics=dict()):
        """Create 1 instance per compute node and make instance statistic

        This goes up to the min_compute_nodes threshold so that things don't
        get crazy if you have 1000 compute nodes but set min to 3.

        :param metrics: The metrics add to resource when using Gnocchi
        """
        compute_nodes = self.get_compute_nodes_setup()
        instances = self.mgr.servers_client.list_servers(
            detail=True)['servers']
        if instances:
            return instances

        hypervisors = self.get_hypervisors_setup()
        created_instances = []
        for node in compute_nodes[:CONF.compute.min_compute_nodes]:
            hyp_id = [
                hyp['id'] for hyp in hypervisors
                if hyp['hypervisor_hostname'] == node['host']]
            # Placement may fail to update trait because of Conflict
            # the trait may be updated by the Nova compute
            # update_available_resource periodic task.
            # We need node status is enabled, so we check the node
            # trait and delay if it is not the correct status.
            # the max delay time is 10 minutes.
            node_trait = os_traits.COMPUTE_STATUS_DISABLED
            retry = 20
            trait_status = True
            while trait_status and retry:
                trait_status = self.check_node_trait(hyp_id[0], node_trait)
                if not trait_status:
                    break
                time.sleep(30)
                retry -= 1
            self.assertNotEqual(0, retry)
            # by getting to active state here, this means this has
            # landed on the host in question.
            instance = self.create_server(image_id=CONF.compute.image_ref,
                                          wait_until='ACTIVE',
                                          clients=self.os_primary)
            # get instance object again as admin
            instance = self.mgr.servers_client.show_server(
                instance['id'])['server']
            created_instances.append(instance)
            self.make_instance_statistic(instance, metrics=metrics)

        return created_instances

    def _pack_all_created_instances_on_one_host(self, instances):
        hypervisors = [
            hyp['hypervisor_hostname'] for hyp in self.get_hypervisors_setup()
            if hyp['state'] == 'up']
        node = hypervisors[0]
        for instance in instances:
            if instance.get('OS-EXT-SRV-ATTR:hypervisor_hostname') != node:
                self._live_migrate(instance['id'], node, 'ACTIVE')

    # ### GNOCCHI ### #

    def create_resource(self, **kwargs):
        """Wrapper utility for creating a test resource

        :return: A tuple with The HTTP response and its body
        """
        try:
            resp, body = self.gnocchi.create_resource(**kwargs)
        except exceptions.Conflict:
            # if resource already exists we just request it
            search_body = {"=": {"original_resource_id": kwargs['id']}}
            resp, body = self.gnocchi.search_resource(**search_body)
            body = body[0]
            for metric_name in kwargs['metrics'].keys():
                metric_body = {
                    "archive_policy_name": "low",
                    "resource_id": body['id'],
                    "name": metric_name
                }
                if body['metrics'].get(metric_name, None):
                    self.gnocchi.delete_metric(body['metrics'][metric_name])
                self.gnocchi.create_metric(**metric_body)
            resp, body = self.gnocchi.search_resource(**search_body)
            body = body[0]
        return resp, body

    def _make_measures(self, measures_count, time_step):
        measures_body = []
        for i in range(1, measures_count + 1):
            dt = datetime.utcnow() - timedelta(minutes=i * time_step)
            measures_body.append(
                dict(value=random.randint(10, 20),
                     timestamp=dt.replace(microsecond=0).isoformat())
            )
        return measures_body

    def make_host_statistic(self, metrics=dict()):
        """Add host metrics to the datasource

        :param metrics: Metrics that should be created
          in the configured datasource.
        """
        # data sources that support fake metrics
        if CONF.optimize.datasource == "gnocchi":
            self.make_host_statistic_gnocchi(metrics)
        elif CONF.optimize.datasource == "prometheus":
            self.make_host_statistic_prometheus()

    def make_host_statistic_gnocchi(self, metrics=dict()):
        """Create host resource and its measures

        :param metrics: Metrics that should be created
          in the Gnocchi datasource.
        """
        hypervisors_client = self.mgr.hypervisor_client
        hypervisors = hypervisors_client.list_hypervisors(
            detail=True)['hypervisors']
        if metrics == dict():
            metrics = {
                self.GNOCCHI_METRIC_MAP['host_cpu_usage']: {
                    'archive_policy_name': 'low'
                }
            }
        else:
            metrics = {
                self.GNOCCHI_METRIC_MAP[m]: {
                    'archive_policy_name': 'low'
                } for m in metrics.keys()
            }
        for h in hypervisors:
            host_name = "%s_%s" % (h['hypervisor_hostname'],
                                   h['hypervisor_hostname'])
            resource_params = {
                'type': 'host',
                'metrics': metrics,
                'host_name': host_name,
                'id': host_name
            }
            _, res = self.create_resource(**resource_params)
            metric_uuid = res['metrics'][
                self.GNOCCHI_METRIC_MAP['host_cpu_usage']
            ]
            # Generate host_cpu_usage fake metrics
            self.gnocchi.add_measures(metric_uuid, self._make_measures(3, 5))

    def _show_measures(self, metric_uuid):
        try:
            _, res = self.gnocchi.show_measures(metric_uuid)
        except Exception:
            return False
        if len(res) > 0:
            return True

    def make_instance_statistic(self, instance, metrics=dict()):
        """Add instance resources and its measures to the datasource

        :param instance: Instance response body
        :param metrics: Metrics that should be created
          in the configured datasource.
        """
        # data sources that support fake metrics
        if CONF.optimize.datasource == "gnocchi":
            self.make_instance_statistic_gnocchi(instance, metrics)
        elif CONF.optimize.datasource == "prometheus":
            self.make_instance_statistic_prometheus(instance)

    def make_instance_statistic_gnocchi(self, instance, metrics=dict()):
        """Create instance resource and its measures in Gnocchi DB

        :param instance: Instance response body
        :param metrics: The metrics add to resource when using Gnocchi
        """
        all_flavors = self.flavors_client.list_flavors()['flavors']
        flavor_name = instance['flavor']['original_name']
        flavor = [f for f in all_flavors if f['name'] == flavor_name]
        if metrics == dict():
            metrics = {
                self.GNOCCHI_METRIC_MAP["instance_cpu_usage"]: {
                    'archive_policy_name': 'low'
                }
            }
        else:
            metrics = {
                self.GNOCCHI_METRIC_MAP[m]: {
                    'archive_policy_name': 'low'
                } for m in metrics.keys()
            }
        resource_params = {
            'type': 'instance',
            'metrics': metrics,
            'host': instance.get('OS-EXT-SRV-ATTR:hypervisor_hostname'),
            'display_name': instance.get('OS-EXT-SRV-ATTR:instance_name'),
            'image_ref': instance['image']['id'],
            'flavor_id': flavor[0]['id'],
            'flavor_name': flavor_name,
            'id': instance['id']
        }
        _, res = self.create_resource(**resource_params)
        # Generates cpu fake metrics
        metric_uuid = res['metrics'][
            self.GNOCCHI_METRIC_MAP["instance_cpu_usage"]
        ]
        self.gnocchi.add_measures(metric_uuid, self._make_measures(3, 5))

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self._show_measures, metric_uuid),
            duration=600,
            sleep_for=2
        ))

    # ### PROMETHEUS ### #
    def _generate_prometheus_metrics(self,
                                     metric_name,
                                     metric_type="counter",
                                     labels={},
                                     count=10,
                                     interval_secs=30,
                                     add_unique_label=True,
                                     inc_factor=0.8,
                                     start_value=1.0):
        """Generates multiple samples for a given metric.


        Samples are generate for a time interval defined by
        the provided 'interval_secs' and the number of
        samples (count) parameters, where the most recent
        sample will be datetime.now().

        :param metric_name: the name of the metric.
        :param metric_type: type of the metric.
        :param labels: labels to be added to each sample.
        :param count: number of samples to be generated.
        :param interval_sec: seconds between each generated
          sample.
        :param add_unique_label: when set to True, a unique
          label pair will be added to all samples, thus
          creating a new series in prometheus. Providing a
          different label pair for every metric generation
          will have the same effect.
        :param inc_factor: factor used when calculating the
          value of a sample, which is a factor of the sample's
          interval.
        :param start_value: value of the first sample to be
          generated.

        :return: String with all samples for a given metric.
        """
        # timestamp needs to be in milliseconds
        ts_now_ms = int(datetime.now().timestamp()*1000)

        # NOTE(dviroel): by including a unique label value, we avoid the
        #  'out of order sample' error when pushing multiple
        #  samples to prometheus that overlap the timestamp
        if add_unique_label:
            labels.update({"orig_timestamp": str(ts_now_ms)})

        # convert labels to exposition format
        str_labels = ""
        if labels:
            str_labels = json.dumps(labels, separators=(',', '='))

        # timestamp is in ms
        step_ms = interval_secs * 1000
        data = '# TYPE %s %s\n' % (metric_name, metric_type)
        # generate 'count' samples with incremental values
        # samples need to be ordered by their timestamp
        value = start_value
        for i in range(count, 0, -1):
            value += inc_factor * interval_secs
            data += '%s%s %s %s\n' % (
                metric_name, str_labels,
                value, ts_now_ms - step_ms * i
            )
        return data

    def make_instance_statistic_prometheus(self, instance):
        """Create Prometheus metrics for a instance

        :param instance: Instance response body
        """
        instance_labels = {
            "resource": instance['id'],
        }
        # Generate cpu usage data for a instance
        # unit is ns, so for a 80%, inc_factor is 0.8 * 1e+9
        data = self._generate_prometheus_metrics(
            self.PROMETHEUS_METRIC_MAP['instance_cpu_usage'],
            labels=instance_labels,
            start_value=1.0,
            inc_factor=8e+8)

        self.prometheus_client.add_measures(data)

    def make_host_statistic_prometheus(self):
        """Create host resource and its measures in Prometheus. """

        hypervisors = self.get_hypervisors_setup()

        for h in hypervisors:
            instance = self.prometheus_client.prometheus_instances.get(
                h['hypervisor_hostname'], None)
            if not instance:
                LOG.info(f"Hostname {h['hypervisor_hostname']} does not "
                         "map to any prometheus instance.")
            else:
                host_labels = {
                    "instance": instance,
                    "fqdn": h['hypervisor_hostname'],
                    "mode": "idle",
                }
                # Generate host usage data
                # unit is seconds, that represent cpu in idle
                data = self._generate_prometheus_metrics(
                    self.PROMETHEUS_METRIC_MAP['host_cpu_usage'],
                    labels=host_labels,
                    start_value=1.0,
                    inc_factor=0.4)

                self.prometheus_client.add_measures(data)

    # ### AUDIT TEMPLATES ### #

    def create_audit_template(self, goal, name=None, description=None,
                              strategy=None):
        """Wrapper utility for creating a test audit template

        :param goal: Goal UUID or name related to the audit template.
        :param name: The name of the audit template. Default: My Audit Template
        :param description: The description of the audit template.
        :param strategy: Strategy UUID or name related to the audit template.
        :return: A tuple with The HTTP response and its body
        """
        description = description or data_utils.rand_name(
            'test-audit_template')
        resp, body = self.client.create_audit_template(
            name=name, description=description, goal=goal, strategy=strategy)

        self.addCleanup(
            self.delete_audit_template,
            audit_template_uuid=body["uuid"]
        )

        return resp, body

    def delete_audit_template(self, audit_template_uuid):
        """Deletes a audit_template having the specified UUID

        :param audit_template_uuid: The unique identifier of the audit template
        :return: Server response
        """
        resp, _ = self.client.delete_audit_template(audit_template_uuid)
        return resp

    # ### AUDITS ### #

    def create_audit(self, audit_template_uuid, audit_type='ONESHOT',
                     state=None, interval=None, parameters=None):
        """Wrapper utility for creating a test audit

        :param audit_template_uuid: Audit Template UUID this audit will use
        :param type: Audit type (either ONESHOT or CONTINUOUS)
        :param state: Audit state (str)
        :param interval: Audit interval in seconds (int)
        :param parameters: list of execution parameters
        :return: A tuple with The HTTP response and its body
        """
        resp, body = self.client.create_audit(
            audit_template_uuid=audit_template_uuid, audit_type=audit_type,
            state=state, interval=interval, parameters=parameters)

        self.addCleanup(self.delete_audit, audit_uuid=body["uuid"])
        return resp, body

    def delete_audit(self, audit_uuid):
        """Deletes an audit having the specified UUID

        :param audit_uuid: The unique identifier of the audit.
        :return: the HTTP response
        """

        _, action_plans = self.client.list_action_plans(audit_uuid=audit_uuid)
        for action_plan in action_plans.get("action_plans", []):
            self.delete_action_plan(action_plan_uuid=action_plan["uuid"])

        resp, _ = self.client.delete_audit(audit_uuid)
        return resp

    def has_audit_succeeded(self, audit_uuid):
        _, audit = self.client.show_audit(audit_uuid)
        if audit.get('state') in ('FAILED', 'CANCELLED'):
            raise ValueError()

        return audit.get('state') == 'SUCCEEDED'

    @classmethod
    def has_audit_finished(cls, audit_uuid):
        _, audit = cls.client.show_audit(audit_uuid)
        return audit.get('state') in cls.AUDIT_FINISHED_STATES

    # ### ACTION PLANS ### #

    def delete_action_plan(self, action_plan_uuid):
        """Deletes an action plan having the specified UUID

        :param action_plan_uuid: The unique identifier of the action plan.
        :return: the HTTP response
        """
        resp, _ = self.client.delete_action_plan(action_plan_uuid)
        return resp

    def has_action_plan_finished(self, action_plan_uuid):
        _, action_plan = self.client.show_action_plan(action_plan_uuid)
        return action_plan.get('state') in self.AP_FINISHED_STATES

    def has_action_plans_finished(self):
        _, action_plans = self.client.list_action_plans()
        for ap in action_plans['action_plans']:
            _, action_plan = self.client.show_action_plan(ap['uuid'])
            if action_plan.get('state') not in self.AP_FINISHED_STATES:
                return False
        return True

    def execute_strategy(self, goal_name, strategy_name, **audit_kwargs):
        """Execute an action plan based on the specific strategy

        - create an audit template with the specific strategy
        - run the audit to create an action plan
        - get the action plan
        - run the action plan
        - get results and make sure it succeeded
        """
        _, goal = self.client.show_goal(goal_name)
        _, strategy = self.client.show_strategy(strategy_name)
        _, audit_template = self.create_audit_template(
            goal['uuid'], strategy=strategy['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plans_finished),
            duration=600,
            sleep_for=2
        ))

        audit_type = audit_kwargs.pop('audit_type', 'ONESHOT')
        state = audit_kwargs.pop('state', None)
        interval = audit_kwargs.pop('interval', None)
        parameters = audit_kwargs.pop('parameters', None)
        _, audit = self.create_audit(
            audit_template['uuid'],
            audit_type=audit_type,
            state=state,
            interval=interval,
            parameters=parameters)

        try:
            self.assertTrue(test_utils.call_until_true(
                func=functools.partial(
                    self.has_audit_finished, audit['uuid']),
                duration=600,
                sleep_for=2
            ))
        except ValueError:
            self.fail("The audit has failed!")

        _, finished_audit = self.client.show_audit(audit['uuid'])
        if finished_audit.get('state') in ('FAILED', 'CANCELLED', 'SUSPENDED'):
            self.fail("The audit ended in unexpected state: %s!"
                      % finished_audit.get('state'))

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return

        # Execute the action by changing its state to PENDING
        _, updated_ap = self.client.start_action_plan(action_plan['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plan_finished, action_plan['uuid']),
            duration=600,
            sleep_for=2
        ))
        _, finished_ap = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=finished_ap["uuid"])
        self.assertIn(updated_ap['state'], ('PENDING', 'ONGOING'))
        self.assertIn(finished_ap['state'], ('SUCCEEDED', 'SUPERSEDED'))

        for action in action_list['actions']:
            self.assertEqual('SUCCEEDED', action.get('state'))

    def check_node_trait(self, node_id, trait):
        """Check if trait is in node traits

        :param node_id: The unique identifier of the node.
        :param trait: node trait
        :return: True if node has the trait else False
        """
        traits = self.placement_client.list_provider_traits(node_id)
        if trait in traits.get('traits'):
            return True
        else:
            return False

    def wait_for_instances_in_model(self, instances, timeout=300):
        """Waits until all instance ids are mapped to a model."""
        timeout_end = time.time() + timeout

        _, body = self.client.list_data_models(data_model_type="compute")
        model_uuids = [s["server_uuid"]
                       for s in body.get("context", []) if "server_uuid" in s]

        ids = [instance['id'] for instance in instances]
        while not set(ids) <= set(model_uuids):
            time.sleep(15)
            if time.time() >= timeout_end:
                raise Exception("Instances are not mapped to compute model.")

            _, body = self.client.list_data_models(data_model_type="compute")
            model_uuids = [
                s["server_uuid"]
                for s in body.get("context", []) if "server_uuid" in s]

    def wait_delete_instances_from_model(self, timeout=300):
        """Waits until all deleted instaces be removed from model."""
        timeout_end = time.time() + timeout

        _, body = self.client.list_data_models(data_model_type="compute")
        model_uuids = [s["server_uuid"]
                       for s in body.get("context", []) if "server_uuid" in s]
        instances = self.mgr.servers_client.list_servers(
            detail=True)['servers']

        ids = [instance['id'] for instance in instances]

        while not set(model_uuids) <= set(ids):
            time.sleep(15)
            if time.time() >= timeout_end:
                raise Exception("Compute model still contains instances "
                                "that were already deleted. Failing...")

            _, body = self.client.list_data_models(data_model_type="compute")
            model_uuids = [
                s["server_uuid"]
                for s in body.get("context", []) if "server_uuid" in s]
