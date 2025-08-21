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

import base64
import functools
import json
import os_traits
import random
import textwrap
import time

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from oslo_log import log
from tempest.common import waiters
from tempest import config
from tempest.lib.common import api_microversion_fixture
from tempest.lib.common import api_version_utils
from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils
from tempest.lib import exceptions
from tempest.scenario import manager

from watcher_tempest_plugin import infra_optim_clients as clients
from watcher_tempest_plugin.services.infra_optim.v1.json import (
    api_microversion_fixture as watcher_microversion_fixture
)


LOG = log.getLogger(__name__)
CONF = config.CONF

# Minimal Nova API required to specify the hosts used when creating
# instances is 2.74.This constant will be used to set the minimal
# version of nova to be used in tests which use create_one_instance_per_host.
# Note that it will not affect the version of the Nova API used by
# Watcher, only the version used by tempest when used from those tests.
NOVA_API_VERSION_CREATE_WITH_HOST = '2.74'


class BaseInfraOptimScenarioTest(manager.ScenarioTest):
    """Base class for Infrastructure Optimization API tests."""

    min_microversion = None
    max_microversion = manager.LATEST_MICROVERSION

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
        host_ram_total='node_memory_MemTotal_bytes',
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
        super(BaseInfraOptimScenarioTest, cls).skip_checks()
        if not CONF.service_available.watcher:
            raise cls.skipException('Watcher support is required')

        api_version_utils.check_skip_with_microversion(
            cls.min_microversion,
            cls.max_microversion,
            CONF.optimize.min_microversion,
            CONF.optimize.max_microversion)

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
        cls.flavors_client = cls.mgr.flavors_client

    def setUp(self):
        super(BaseInfraOptimScenarioTest, self).setUp()
        self.useFixture(api_microversion_fixture.APIMicroversionFixture(
            compute_microversion=self.compute_request_microversion))
        self.useFixture(api_microversion_fixture.APIMicroversionFixture(
            placement_microversion=CONF.placement.min_microversion))
        self.useFixture(watcher_microversion_fixture.APIMicroversionFixture(
            optimize_microversion=self.request_microversion))

    @classmethod
    def resource_setup(cls):
        super(BaseInfraOptimScenarioTest, cls).resource_setup()

        cls.request_microversion = (
            api_version_utils.select_request_microversion(
                cls.min_microversion,
                CONF.optimize.min_microversion))

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
    def get_hypervisor_details(cls, node_name):
        """Get hypervisor details by node name."""
        hypervisors = cls.get_hypervisors_setup()
        for hyp in hypervisors:
            if hyp['hypervisor_hostname'] == node_name:
                return hyp
        raise exceptions.InvalidConfiguration(
            "Hypervisor %s not found in the list of hypervisors." %
            node_name)

    @classmethod
    def get_compute_nodes_setup(cls):
        services_client = cls.mgr.services_client
        available_services = services_client.list_services()['services']

        return [srv for srv in available_services
                if srv.get('binary') == 'nova-compute']

    @classmethod
    def get_enabled_compute_nodes(cls):
        cls.initial_compute_nodes_setup = cls.get_compute_nodes_setup()
        return [cn for cn in cls.initial_compute_nodes_setup
                if cn.get('status') == 'enabled']

    @classmethod
    def get_host_other_than(cls, server_id):
        source_host = cls.get_host_for_server(server_id)

        svcs = cls.os_admin.services_client.list_services(
            binary='nova-compute')['services']
        hosts = []
        for svc in svcs:
            if CONF.compute.target_hosts_to_avoid in svc['host']:
                continue
            if svc['state'] == 'up' and svc['status'] == 'enabled':
                if CONF.compute.compute_volume_common_az:
                    if svc['zone'] == CONF.compute.compute_volume_common_az:
                        hosts.append(svc['host'])
                else:
                    hosts.append(svc['host'])

        for target_host in hosts:
            if source_host != target_host:
                return target_host

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
        waiters.wait_for_server_status(self.os_admin.servers_client,
                                       server_id, state)
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

    def _create_custom_flavor(self, ram=512, vcpus=1):
        """Create a flavor with custom RAM size

        :param ram: RAM in MB to be set for the flavor.
        :returns: A flavor id
        """

        flavor_id = self.flavors_client.create_flavor(
            name=data_utils.rand_name('watcher_flavor'),
            ram=ram,
            vcpus=vcpus,
            disk=1,
            ephemeral=0,
            swap=0,
            rxtx_factor=1.0,
            is_public=True)['flavor']['id']
        self.addCleanup(test_utils.call_and_ignore_notfound_exc,
                        self.flavors_client.delete_flavor, flavor_id)
        return flavor_id

    def _create_one_instance_per_host(self, flavor=None, run_command=None):
        """Create one instance per compute node

        This goes up to the min_compute_nodes threshold so that things don't
        get crazy if you have 1000 compute nodes but set min to 3.

        :param flavor: Flavor Name or ID
        :param run_command: the command you want to run in the new instances
        :returns: A list of instance UUIDs.
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
            instance = self._create_instance(node['host'], flavor, run_command)
            created_instances.append(instance)
        return created_instances

    def _create_instance(self, host=None, flavor=None, run_command=None):
        # We enforce the compute node where we create the instance to
        # make sure we have one node on each compute.
        # This requires Nova API version 2.74 or higher.
        kwargs_server = {'host': host} if host else {}
        validatable = False
        validation_resources = None
        if run_command:
            # In case we want to run commands we will be injecting it via
            # user_data which requires to setup the instance as validatable
            # in tempest.common.compute.create_test_server
            validation_resources = self.get_test_validation_resources(
                self.os_admin)
            validatable = True
            script = '''
                    #!/bin/sh
                    {run_command}
                    '''.format(run_command=run_command)
            script_clean = textwrap.dedent(script).lstrip().encode('utf8')
            script_b64 = base64.b64encode(script_clean)
            kwargs_server['user_data'] = script_b64
        flavor = flavor if flavor else CONF.compute.flavor_ref
        instance = self.create_server(
            image_id=CONF.compute.image_ref, wait_until='ACTIVE',
            flavor=flavor, clients=self.os_admin, validatable=validatable,
            validation_resources=validation_resources,
            **kwargs_server)
        # get instance object again as admin
        instance = self.mgr.servers_client.show_server(
            instance['id'])['server']
        return instance

    def _pack_all_created_instances_on_one_host(self, instances):
        hypervisors = [
            hyp['hypervisor_hostname'] for hyp in self.get_hypervisors_setup()
            if hyp['state'] == 'up']
        node = hypervisors[0]
        for instance in instances:
            if self.get_host_for_server(instance['id']) != node:
                self._live_migrate(instance['id'], node, 'ACTIVE')
        return node

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
                default_metric = {
                    "archive_policy_name": "low",
                    "resource_id": body['id'],
                    "name": metric_name,
                    "unit": "ns"
                }
                metric_body = {**default_metric,
                               **kwargs['metrics'][metric_name]}
                if body['metrics'].get(metric_name, None):
                    self.gnocchi.delete_metric(body['metrics'][metric_name])
                self.gnocchi.create_metric(**metric_body)
            resp, body = self.gnocchi.search_resource(**search_body)
            body = body[0]
        return resp, body

    def _make_measures_host(self, measures_count, time_step, min=10, max=20):
        measures_body = []
        now = datetime.now(timezone.utc)
        for i in range(0, measures_count):
            dt = now - timedelta(minutes=i * time_step)
            measures_body.append(
                dict(value=random.randint(int(min), int(max)),
                     timestamp=dt.replace(microsecond=0).isoformat())
            )
        return measures_body

    def _make_measures_instance(self, measures_count, time_step,
                                min=80, max=90, metric_type='cpu'):
        measures_body = []
        now = datetime.now(timezone.utc)

        if metric_type == "cpu":
            final_cpu = (measures_count + 1) * 60 * time_step * 1e9
            for i in range(0, measures_count):
                dt = now - timedelta(minutes=i * time_step)
                cpu = final_cpu - ((i - 1) * 60 * time_step * 1e9
                                   * random.randint(int(min), int(max)) / 100)
                measures_body.append(
                    dict(value=cpu,
                         timestamp=dt.replace(microsecond=0).isoformat())
                )
        elif metric_type == "ram":
            for i in range(0, measures_count):
                dt = now - timedelta(minutes=i * time_step)
                ram = random.randint(int(min), int(max))
                measures_body.append(
                    dict(value=ram,
                         timestamp=dt.replace(microsecond=0).isoformat())
                )
        else:
            raise ValueError(f"Unsupported metric_type: {metric_type}")

        return measures_body

    def clean_injected_metrics(self):
        """Delete all injected metrics from datastore.

        This is useful to ensure that the tests are not affected by
        previously injected metrics.
        """
        LOG.debug("Deleting injected metrics from Datastore")
        if CONF.optimize.datasource == "gnocchi":
            # TODO(morenod): Add function for deleting injected metrics
            # from Gnocchi.
            pass
        elif CONF.optimize.datasource == "prometheus":
            self.prometheus_client.delete_series()

    def make_host_statistic(self, metrics=dict(), loaded_hosts=[]):
        """Add host metrics to the datasource

        :param metrics: Metrics that should be created
          in the configured datasource.
        :param loaded_hosts: list of hosts that we want to inject data
          representing high usage of resource.
        """
        # data sources that support fake metrics
        if CONF.optimize.datasource == "gnocchi":
            self.make_host_statistic_gnocchi(metrics,
                                             loaded_hosts=loaded_hosts)
        elif CONF.optimize.datasource == "prometheus":
            self.make_host_statistic_prometheus(loaded_hosts=loaded_hosts)

    def make_host_statistic_gnocchi(self, metrics=dict(), loaded_hosts=[]):
        """Create host resource and its measures

        :param metrics: Metrics that should be created
          in the Gnocchi datasource.
        :param loaded_hosts: list of hosts that we want to inject data
          representing high usage of resource.
        """
        hypervisors_client = self.mgr.hypervisor_client
        hypervisors = hypervisors_client.list_hypervisors(
            detail=True)['hypervisors']
        if metrics == dict():
            metrics = {
                self.GNOCCHI_METRIC_MAP['host_cpu_usage']: {
                    'archive_policy_name': 'low'
                },
                self.GNOCCHI_METRIC_MAP['host_ram_usage']: {
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

            # Generate host_cpu_usage fake metrics
            cpu_metric_uuid = res['metrics'][
                self.GNOCCHI_METRIC_MAP['host_cpu_usage']
            ]
            if h['hypervisor_hostname'] in loaded_hosts:
                cpu_measures = self._make_measures_host(10, 1, min=80, max=90)
            else:
                cpu_measures = self._make_measures_host(10, 1)
            self.gnocchi.add_measures(cpu_metric_uuid, cpu_measures)

            # Generate host_ram_usage fake metrics. Metric is based on
            # hardware.memory.used which is in KB.
            ram_metric_uuid = res['metrics'][
                self.GNOCCHI_METRIC_MAP['host_ram_usage']
            ]
            if h['hypervisor_hostname'] in loaded_hosts:
                mem_measures = self._make_measures_host(
                    10, 1,
                    min=int(h['memory_mb']) * 0.8 * 1024,
                    max=int(h['memory_mb']) * 0.9 * 1024)
            else:
                mem_measures = self._make_measures_host(
                    10, 1,
                    min=int(h['memory_mb']) * 0.1 * 1024,
                    max=int(h['memory_mb']) * 0.2 * 1024)
            self.gnocchi.add_measures(ram_metric_uuid, mem_measures)

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
        all_flavors = self.flavors_client.list_flavors(detail=True)['flavors']
        flavor_name = instance['flavor']['original_name']
        flavor = [f for f in all_flavors if f['name'] == flavor_name]
        if metrics == dict():
            metrics = {
                self.GNOCCHI_METRIC_MAP["instance_cpu_usage"]: {
                    'archive_policy_name': 'ceilometer-low-rate',
                    'unit': 'ns'
                },
                self.GNOCCHI_METRIC_MAP["instance_ram_usage"]: {
                    'archive_policy_name': 'ceilometer-low',
                    'unit': 'MB'
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
            'host': self.get_host_for_server(instance['id']),
            'display_name': instance.get('OS-EXT-SRV-ATTR:instance_name'),
            'image_ref': instance['image']['id'],
            'flavor_id': flavor[0]['id'],
            'flavor_name': flavor_name,
            'id': instance['id']
        }
        _, res = self.create_resource(**resource_params)

        # Generates cpu fake metrics
        cpu_metric_uuid = res['metrics'][
            self.GNOCCHI_METRIC_MAP["instance_cpu_usage"]
        ]
        cpu_measures = self._make_measures_instance(5, 5, metric_type='cpu')
        self.gnocchi.add_measures(cpu_metric_uuid, cpu_measures)

        # Generate ram fake metrics

        ram_metric_uuid = res['metrics'][
            self.GNOCCHI_METRIC_MAP["instance_ram_usage"]
        ]
        ram_measures = self._make_measures_instance(
            5, 5,
            min=int(flavor[0]['ram']) * 0.8,
            max=int(flavor[0]['ram']) * 0.9,
            metric_type='ram')
        self.gnocchi.add_measures(ram_metric_uuid, ram_measures)

        for metric_uuid in [cpu_metric_uuid, ram_metric_uuid]:
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
                                     start_value=1.0,
                                     timestamp=None):
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
        :param timestamp: timestamp in ms for the most recent

        :return: String with all samples for a given metric.
        """
        ts_now_ms = timestamp or int(datetime.now().timestamp()*1000)

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
        cpu_data = self._generate_prometheus_metrics(
            self.PROMETHEUS_METRIC_MAP['instance_cpu_usage'],
            labels=instance_labels,
            start_value=1.0,
            inc_factor=8e+8)

        # Generate memory usage data for a instance consuming 80%
        # unit is megabytes, total is obtained from flavor
        # no inc_factor as memory is saved as gauge
        mem_usage_mb = int(instance['flavor']['ram'] * 0.8)
        ram_data = self._generate_prometheus_metrics(
            self.PROMETHEUS_METRIC_MAP['instance_ram_usage'],
            metric_type='gauge',
            labels=instance_labels,
            start_value=mem_usage_mb,
            inc_factor=0)

        self.prometheus_client.add_measures(cpu_data)
        self.prometheus_client.add_measures(ram_data)

    def make_host_statistic_prometheus(self, loaded_hosts=[]):
        """Create host resource and its measures in Prometheus.

        :param loaded_hosts: list of hosts that we want to inject data
          representing high usage of resource.
        """

        hypervisors = self.get_hypervisors_setup()

        for h in hypervisors:
            # When doing maths with prometheus, we need to
            # have all metrics with the same timestamp.
            timestamp = int(datetime.now().timestamp()*1000)
            instance = self.prometheus_client.prometheus_instances.get(
                h['hypervisor_hostname'], None)
            if not instance:
                LOG.info(f"Hostname {h['hypervisor_hostname']} does not "
                         "map to any prometheus instance.")
            else:
                # cpu metrics in prometheus are by cpu so we need to create
                # a set of metrics for each one.
                vcpus = h['vcpus']
                for cpu in range(vcpus):
                    host_labels = {
                        "instance": instance,
                        "fqdn": h['hypervisor_hostname'],
                        "mode": "idle",
                        "cpu": str(cpu),
                    }
                    # Generate host usage data
                    # unit is seconds, that represent cpu in idle
                    if h['hypervisor_hostname'] in loaded_hosts:
                        cpu_data = self._generate_prometheus_metrics(
                            self.PROMETHEUS_METRIC_MAP['host_cpu_usage'],
                            labels=host_labels,
                            start_value=1.0,
                            inc_factor=0.0,
                            timestamp=timestamp)
                    else:
                        cpu_data = self._generate_prometheus_metrics(
                            self.PROMETHEUS_METRIC_MAP['host_cpu_usage'],
                            labels=host_labels,
                            start_value=1.0,
                            inc_factor=1.0,
                            timestamp=timestamp)
                    self.prometheus_client.add_measures(cpu_data)

                host_labels_ram = {
                    "instance": instance,
                    "fqdn": h['hypervisor_hostname'],
                }

                # Generate memory usage data for a hypervisor
                # simulate 80% of memory usage on loaded_hosts
                # simulate 10% of memory load on others
                # unit is megabytes, total is obtained from hypervisor
                # no inc_factor as memory is saved as gauge

                load = 0.8 if h['hypervisor_hostname'] in loaded_hosts else 0.1
                mem_available_mb = int(h['memory_mb'] * (1 - load))
                # metric is node_memory_MemAvailable_bytes which is in bytes
                mem_available_bytes = mem_available_mb * 1024 * 1024
                ram_data = self._generate_prometheus_metrics(
                    self.PROMETHEUS_METRIC_MAP['host_ram_usage'],
                    metric_type='gauge',
                    labels=host_labels_ram,
                    start_value=mem_available_bytes,
                    inc_factor=0,
                    timestamp=timestamp)
                self.prometheus_client.add_measures(ram_data)

                # Generate host total memory data for a hypervisor
                # unit is megabytes, total is obtained from hypervisor
                # no inc_factor as memory is saved as gauge
                mem_total_mb = int(h['memory_mb'])
                # metric is node_memory_MemTotal_bytes which is in bytes
                mem_total_bytes = mem_total_mb * 1024 * 1024
                ram_total_data = self._generate_prometheus_metrics(
                    self.PROMETHEUS_METRIC_MAP['host_ram_total'],
                    metric_type='gauge',
                    labels=host_labels_ram,
                    start_value=mem_total_bytes,
                    inc_factor=0,
                    timestamp=timestamp)
                self.prometheus_client.add_measures(ram_total_data)

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

    def execute_strategy(self, goal_name, strategy_name,
                         expected_actions=[], **audit_kwargs):
        """Execute an action plan based on the specific strategy

        - create an audit template with the specific strategy
        - run the audit to create an action plan
        - get the action plan
        - Verify that all action types in the expected_actions
          list are present in the action plan.
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
        created_actions = self.client.list_actions(
            action_plan_uuid=action_plan["uuid"])[1]['actions']

        if expected_actions:
            action_types = {a['action_type'] for a in created_actions}
            if set(expected_actions) != action_types:
                self.fail("The audit has found action types %s when expecting "
                          "%s" % (action_types, expected_actions))

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
        """Waits until all instance ids are mapped to a model.

        Get the model and save instance ids and hypervisor hostname
        Get instances details and save instance ids and current hypervisora
        hostname
        (hypervisor hostname from argument is the one where it was created)
        Compare the two lists and wait until they are equal.
        """

        timeout_end = time.time() + timeout

        _, body = self.client.list_data_models(data_model_type="compute")
        model_pairs = [(s['server_uuid'], s['node_hostname'])
                       for s in body.get('context', [])
                       if 'server_uuid' in s and 'node_hostname' in s]
        instance_pairs = []
        for instance in instances:
            s = self.mgr.servers_client.show_server(instance['id'])['server']
            instance_pairs.append((s['id'], s['OS-EXT-SRV-ATTR:host']))

        # If no instances were created, we should not wait for them
        if not instance_pairs:
            raise Exception("No instances were created.")

        # Check all instances are in the model and model is not empty
        while (not set(instance_pairs) <= set(model_pairs) or not model_pairs):
            time.sleep(15)
            if time.time() >= timeout_end:
                raise Exception("Instances are not mapped to compute model.")

            _, body = self.client.list_data_models(data_model_type="compute")
            model_pairs = [(s['server_uuid'], s['node_hostname'])
                           for s in body.get('context', [])
                           if 'server_uuid' in s and 'node_hostname' in s]

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
