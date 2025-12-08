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

import functools

from tempest import config
from tempest.lib.common.utils import test_utils
from tempest.lib import decorators

from watcher_tempest_plugin.tests.scenario import base

CONF = config.CONF


class TestContinuousAudit(base.BaseInfraOptimScenarioTest):
    """Tests that create continuous audits and execute strategies."""

    # Minimal version required for list data models
    min_microversion = "1.3"
    # Minimal version required for _create_one_instance_per_host
    compute_min_microversion = base.NOVA_API_VERSION_CREATE_WITH_HOST

    @classmethod
    def skip_checks(cls):
        super().skip_checks()
        if not CONF.optimize.run_continuous_audit_tests:
            raise cls.skipException(
                "Continuous audit tests are disabled.")

        if CONF.compute.min_compute_nodes < 2:
            raise cls.skipException(
                "Less than 2 compute nodes, skipping multinode tests.")

        if not CONF.compute_feature_enabled.live_migration:
            raise cls.skipException("Live migration is not enabled")

    @decorators.idempotent_id("bd6a18e9-bd51-4164-9e7f-4f19d9b428ba")
    @decorators.attr(type=['strategy', 'zone_migration'])
    def test_continuous_audit_zone_migration(self):
        """Create a continuous audit using zone_migration strategy"""
        # NOTE(dviroel): We don't need to start/trigger the action plan to
        # validate continous audits, but we need to create the workload and
        # check if the strategy will get updates from the model.
        self.check_min_enabled_compute_nodes(2)
        self.addCleanup(self.wait_delete_instances_from_model)

        src_host = self.get_enabled_compute_nodes()[0]['host']
        audit_parameters = {
            "compute_nodes": [{"src_node": src_host}],
        }

        audit_template = self.create_audit_template_for_strategy(
            goal_name="hardware_maintenance", strategy_name="zone_migration")

        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_action_plans_finished),
            duration=600,
            sleep_for=2
        ))

        # 1. Create a continuous audit that should propose
        #    SUCCEEDED action plans, without actions, since
        #    we don't have any instances to move yet
        #    NOTE(dviroel): This is intentional to force a
        #    cluster model update from continous audit thread.
        _, audit = self.create_audit(
            audit_template["uuid"],
            audit_type="CONTINUOUS",
            interval="10",
            parameters=audit_parameters)

        # Wait until it reach the ONGOING state, otherwise fail
        try:
            self.assertTrue(test_utils.call_until_true(
                func=functools.partial(
                    self.is_audit_ongoing, audit["uuid"]),
                duration=300,
                sleep_for=2
            ))
        except ValueError:
            self.fail("Audit failed to reach ONGOING state.")

        # Wait for an action plan from this audit
        try:
            self.assertTrue(test_utils.call_until_true(
                func=functools.partial(
                    self.has_action_plans, audit["uuid"]),
                duration=300,
                sleep_for=10
            ))
        except ValueError:
            self.fail("Audit failed to create an action plan.")

        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit["uuid"])
        action_plan = action_plans["action_plans"][0]

        try:
            self.assertTrue(test_utils.call_until_true(
                func=functools.partial(
                    self.has_action_plan_finished, action_plan["uuid"]),
                duration=60,
                sleep_for=2
            ))
        except ValueError:
            self.fail("Action plan failed to reach a finished state.")
        # Since a new run of the continuous audit will change the last
        # action plan to CANCELLED. It is hard to guarantee that we will
        # always have a SUCCEEDED action plan.
        self.assertIn(action_plan['state'], ('SUCCEEDED', 'CANCELLED'))

        # Action plan should have no actions
        created_actions = self.client.list_actions(
            action_plan_uuid=action_plan["uuid"])[1]["actions"]
        self.assertEqual(len(created_actions), 0)

        # 2. Create a instance in the host, that is our
        # src_host in zone_migration.
        instance = self._create_instance(host=src_host)
        # wait for compute model updates
        self.wait_for_instances_in_model([instance])

        # Wait for a first RECOMMENDED action plan from this audit
        try:
            self.assertTrue(test_utils.call_until_true(
                func=functools.partial(
                    self.has_action_plans_recommended, audit["uuid"]),
                duration=300,
                sleep_for=10
            ))
        except ValueError:
            self.fail("Audit failed to create a RECOMMENDED action plan.")

        # Update state to CANCELLED, so it can be deleted afterwards
        _, audit = self.client.update_audit(
            audit["uuid"],
            [{"op": "replace", "path": "/state", "value": "CANCELLED"}]
        )

        try:
            self.assertTrue(test_utils.call_until_true(
                func=functools.partial(
                    self.has_audit_finished, audit["uuid"]),
                duration=300,
                sleep_for=2
            ))
        except ValueError:
            self.fail("The audit failed to reach one of finished states.")

        # 3. Check that the audit created a RECOMMENDED action plan, with
        #    a migrate action
        _, action_plans = self.client.list_action_plans(
            audit_uuid=audit["uuid"])
        recommended_aps = [ap for ap in action_plans["action_plans"]
                           if ap["state"] == "RECOMMENDED"]

        # At least one action plan should be a RECOMMENDED one
        self.assertGreaterEqual(len(recommended_aps), 1)

        # Validate action plan action type
        created_actions = self.client.list_actions(
            action_plan_uuid=recommended_aps[0]["uuid"])[1]["actions"]

        expected_actions = ["migrate"]
        action_types = {a["action_type"] for a in created_actions}
        if set(expected_actions) != action_types:
            self.fail("The audit has found action types %s when expecting "
                      "%s" % (action_types, expected_actions))
