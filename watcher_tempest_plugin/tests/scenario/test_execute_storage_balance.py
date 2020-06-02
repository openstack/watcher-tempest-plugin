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

import functools

from oslo_log import log
from tempest import config
from tempest.lib.common.utils import test_utils

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF
LOG = log.getLogger(__name__)


class TestExecuteStorageCapacityBalanceStrategy(
        base.BaseInfraOptimScenarioTest):
    """Tests for storage capacity balance"""

    GOAL = "workload_balancing"

    @classmethod
    def skip_checks(cls):
        super(TestExecuteStorageCapacityBalanceStrategy, cls).skip_checks()

    @classmethod
    def resource_setup(cls):
        super(TestExecuteStorageCapacityBalanceStrategy, cls).resource_setup()
        if not CONF.volume_feature_enabled.multi_backend:
            raise cls.skipException("Cinder multi-backend feature disabled")

        if len(set(CONF.volume.backend_names)) < 2:
            raise cls.skipException("Requires at least two different "
                                    "backend names")

    def test_execute_storage_capacity_balance(self):
        """Execute the storage capacity balance strategy"""
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref)
        audit_parameters = {"volume_threshold": 25}

        _, goal = self.client.show_goal(self.GOAL)
        _, strategy = self.client.show_strategy("storage_capacity_balance")
        _, audit_template = self.create_audit_template(
            goal['uuid'], strategy=strategy['uuid'])

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plans_finished),
            duration=600,
            sleep_for=2
        ))

        _, audit = self.create_audit(
            audit_template['uuid'], parameters=audit_parameters)

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
        if finished_audit.get('state') in ('FAILED', 'CANCELLED'):
            self.fail("The audit ended in unexpected state: %s!" %
                      finished_audit.get('state'))

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit['uuid'])
        action_plan = action_plans['action_plans'][0]

        _, action_plan = self.client.show_action_plan(action_plan['uuid'])
        _, action_list = self.client.list_actions(
            action_plan_uuid=action_plan["uuid"])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            # This means the action plan is superseded so we cannot trigger it,
            # or it is empty.
            return
        for action in action_list['actions']:
            self.assertEqual('PENDING', action.get('state'))

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
