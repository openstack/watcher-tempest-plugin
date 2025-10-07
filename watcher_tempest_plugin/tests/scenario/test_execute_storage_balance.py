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


class TestExecuteStorageCapacityBalanceStrategy(
        base.BaseInfraOptimScenarioTest):
    """Tests for storage capacity balance"""

    GOAL = "workload_balancing"
    STRATEGY = "storage_capacity_balance"

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.volume_feature_enabled.multi_backend:
            raise cls.skipException("Cinder multi-backend feature disabled")

        if len(set(CONF.volume.backend_names)) < 2:
            raise cls.skipException("Requires at least two different "
                                    "backend names")

    @decorators.idempotent_id('7e3a9195-acc5-40cf-96da-a0a2883294d3')
    @decorators.attr(type=['strategy', 'storage_capacity_balance'])
    def test_execute_storage_capacity_balance_strategy(self):
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=3)
        self.create_volume(imageRef=CONF.compute.image_ref, size=1)

        audit_kwargs = {
            "parameters": {
                "volume_threshold": 25
            }
        }

        audit_template = self.create_audit_template_for_strategy()

        audit = self.create_audit_and_wait(
            audit_template['uuid'], **audit_kwargs)

        action_plan, _ = self.get_action_plan_and_validate_actions(
            audit['uuid'])

        if action_plan['state'] in ('SUPERSEDED', 'SUCCEEDED'):
            return

        self.execute_action_plan_and_validate_states(action_plan['uuid'])
