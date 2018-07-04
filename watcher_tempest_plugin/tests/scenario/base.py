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

from __future__ import unicode_literals

import functools
import random
import time

from datetime import datetime
from datetime import timedelta
from oslo_log import log
from tempest import config
from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils
from tempest.lib import exceptions

from watcher_tempest_plugin import infra_optim_clients as clients
from watcher_tempest_plugin.tests.scenario import manager

LOG = log.getLogger(__name__)
CONF = config.CONF


class BaseInfraOptimScenarioTest(manager.ScenarioTest):
    """Base class for Infrastructure Optimization API tests."""

    # States where the object is waiting for some event to perform a transition
    IDLE_STATES = ('RECOMMENDED', 'FAILED', 'SUCCEEDED', 'CANCELLED')
    # States where the object can only be DELETED (end of its life-cycle)
    FINISHED_STATES = ('FAILED', 'SUCCEEDED', 'CANCELLED', 'SUPERSEDED')

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

    @classmethod
    def resource_setup(cls):
        super(BaseInfraOptimScenarioTest, cls).resource_setup()

    @classmethod
    def resource_cleanup(cls):
        """Ensure that all created objects get destroyed."""
        super(BaseInfraOptimScenarioTest, cls).resource_cleanup()

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
        return all([ap['state'] in cls.FINISHED_STATES
                    for ap in action_plans['action_plans']])

    def wait_for_all_action_plans_to_finish(self):
        assert test_utils.call_until_true(
            func=self._are_all_action_plans_finished,
            duration=300,
            sleep_for=5
        )

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
            if body['metrics'].get('cpu_util'):
                self.gnocchi.delete_metric(body['metrics']['cpu_util'])
            metric_body = {
                "archive_policy_name": "bool",
                "resource_id": body['id'],
                "name": "cpu_util"
            }
            self.gnocchi.create_metric(**metric_body)
            resp, body = self.gnocchi.search_resource(**search_body)
            body = body[0]
        return resp, body

    def add_measures(self, metric_uuid, body):
        """Wrapper utility for creating a test measures for metric

        :param metric_uuid: The unique identifier of the metric
        :return: A tuple with The HTTP response and empty body
        """
        resp, body = self.gnocchi.add_measures(metric_uuid, body)
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

    def make_host_statistic(self):
        """Create host resource and its measures in Gnocchi DB"""
        hypervisors_client = self.mgr.hypervisor_client
        hypervisors = hypervisors_client.list_hypervisors(
            detail=True)['hypervisors']
        for h in hypervisors:
            host_name = "%s_%s" % (h['hypervisor_hostname'],
                                   h['hypervisor_hostname'])
            resource_params = {
                'type': 'host',
                'metrics': {
                    'compute.node.cpu.percent': {
                        'archive_policy_name': 'bool'
                    }
                },
                'host_name': host_name,
                'id': host_name
            }
            _, res = self.create_resource(**resource_params)
            metric_uuid = res['metrics']['compute.node.cpu.percent']
            self.add_measures(metric_uuid, self._make_measures(3, 5))

    def _show_measures(self, metric_uuid):
        try:
            _, res = self.gnocchi.show_measures(metric_uuid)
        except Exception:
            return False
        if len(res) > 0:
            return True

    def make_instance_statistic(self, instance):
        """Create instance resource and its measures in Gnocchi DB

        :param instance: Instance response body
        """
        flavor = self.flavors_client.show_flavor(instance['flavor']['id'])
        flavor_name = flavor['flavor']['name']
        resource_params = {
            'type': 'instance',
            'metrics': {
                'cpu_util': {
                    'archive_policy_name': 'bool'
                }
            },
            'host': instance.get('OS-EXT-SRV-ATTR:hypervisor_hostname'),
            'display_name': instance.get('OS-EXT-SRV-ATTR:instance_name'),
            'image_ref': instance['image']['id'],
            'flavor_id': instance['flavor']['id'],
            'flavor_name': flavor_name,
            'id': instance['id']
        }
        _, res = self.create_resource(**resource_params)
        metric_uuid = res['metrics']['cpu_util']
        self.add_measures(metric_uuid, self._make_measures(3, 5))

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self._show_measures, metric_uuid),
            duration=600,
            sleep_for=2
        ))

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
        return audit.get('state') in cls.FINISHED_STATES

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
        return action_plan.get('state') in ('FAILED', 'SUCCEEDED', 'CANCELLED',
                                            'SUPERSEDED')

    def has_action_plans_finished(self):
        _, action_plans = self.client.list_action_plans()
        for ap in action_plans['action_plans']:
            _, action_plan = self.client.show_action_plan(ap['uuid'])
            if action_plan.get('state') not in ('FAILED', 'SUCCEEDED',
                                                'CANCELLED', 'SUPERSEDED'):
                return False
        return True
