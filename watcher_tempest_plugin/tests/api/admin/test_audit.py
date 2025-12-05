# -*- encoding: utf-8 -*-
# Copyright (c) 2016 b<>com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import functools

from datetime import datetime
from datetime import timedelta
from datetime import timezone

from tempest.lib.common.utils import test_utils
from tempest.lib import decorators
from tempest.lib import exceptions

from watcher_tempest_plugin.tests.api.admin import base
from watcher_tempest_plugin.tests.common import base as common_base


class TestCreateUpdateDeleteAudit(base.BaseInfraOptimTest):
    """Tests for audit."""

    def assert_expected(self, expected, actual,
                        keys=('created_at', 'updated_at', 'next_run_time',
                              'deleted_at', 'state', 'hostname')):
        super(TestCreateUpdateDeleteAudit, self).assert_expected(
            expected, actual, keys)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('7e759ad3-17e8-4a8e-95cf-6532faf67667')
    def test_create_audit_oneshot(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='ONESHOT',
            name='audit_oneshot',
        )

        _, body = self.create_audit(**audit_params)
        audit_params.pop('audit_template_uuid')
        audit_params['goal_uuid'] = goal['uuid']
        self.assert_expected(audit_params, body)
        self.assertIn(body['state'], ('PENDING', 'ONGOING', 'SUCCEEDED'))

        _, audit = self.client.show_audit(body['uuid'])
        self.assert_expected(audit, body)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('3c9bf382-e43b-43d6-a310-f7387cfc2f58')
    def test_create_audit_continuous(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='CONTINUOUS',
            interval='7200',
            name='audit_continuous',
        )

        _, body = self.create_audit(**audit_params)
        audit_params.pop('audit_template_uuid')
        audit_params['goal_uuid'] = goal['uuid']
        self.assert_expected(audit_params, body)
        self.assertIn(body['state'], ('PENDING', 'ONGOING'))

        _, audit = self.client.show_audit(body['uuid'])
        self.assert_expected(audit, body)

        self.cancel_audit(body['uuid'])

        _, audit = self.client.show_audit(body['uuid'])
        self.assertEqual(audit['state'], 'CANCELLED')

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('3e845716-8288-42b3-b95c-395ba7afbaf5')
    def test_create_audit_with_wrong_audit_template(self):
        audit_params = dict(
            audit_template_uuid='INVALID',
            audit_type='ONESHOT',
        )

        self.assertRaises(
            exceptions.BadRequest, self.create_audit, **audit_params)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('1afb3b41-40a7-4000-9dc0-53b5e8eaa009')
    def test_create_audit_with_invalid_state(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            state='INVALID',
        )

        self.assertRaises(
            exceptions.BadRequest, self.create_audit, **audit_params)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('d6b6a3a0-0eed-474f-b3dc-14ed0d97c655')
    def test_create_audit_with_no_state(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            state='',
        )

        _, body = self.create_audit(**audit_params)
        audit_params.pop('audit_template_uuid')
        audit_params['goal_uuid'] = goal['uuid']
        self.assert_expected(audit_params, body)

        _, audit = self.client.show_audit(body['uuid'])

        initial_audit_state = audit.pop('state')
        self.assertIn(initial_audit_state, common_base.AuditStates.values())

        self.assert_expected(audit, body)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('d1520631-2dbb-4240-ba0a-14aa7f347003')
    def test_update_audit(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])
        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='CONTINUOUS',
            interval='7200',
        )

        _, body = self.create_audit(**audit_params)
        audit_uuid = body['uuid']
        test_utils.call_until_true(
            func=functools.partial(
                self.is_audit_ongoing, audit_uuid),
            duration=10,
            sleep_for=.5
        )

        self.cancel_audit(audit_uuid)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('e06add3b-1a48-41c2-871e-5d0803a81a37')
    def test_delete_audit(self):
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])
        _, body = self.create_audit(audit_template['uuid'])
        audit_uuid = body['uuid']

        test_utils.call_until_true(
            func=functools.partial(
                self.is_audit_idle, audit_uuid),
            duration=10,
            sleep_for=.5
        )

        def is_audit_deleted(uuid):
            try:
                return not bool(self.client.show_audit(uuid))
            except exceptions.NotFound:
                return True

        self.delete_audit(audit_uuid)

        test_utils.call_until_true(
            func=functools.partial(is_audit_deleted, audit_uuid),
            duration=5,
            sleep_for=1
        )

        self.assertTrue(is_audit_deleted(audit_uuid))

    @decorators.idempotent_id('c7a5e9f2-6b4c-4e5a-9d2e-1a0b3c4d5e6f')
    def test_create_continuous_audit_with_crontab_interval(self):
        """Test creating continuous audit with crontab-style interval"""
        _, goal = self.client.show_goal("dummy")
        _, strategy = self.client.show_strategy("dummy")

        _, audit_template = self.create_audit_template(
            goal['uuid'], strategy=strategy['uuid'])

        cron_expr = '*/5 * * * *'  # every 5 minutes

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='CONTINUOUS',
            interval=cron_expr,
        )

        _, body = self.create_audit(**audit_params)
        audit_params.pop('audit_template_uuid')
        audit_params['goal_uuid'] = goal['uuid']

        # Verify the audit was created with correct parameters
        self.assert_expected(audit_params, body)
        self.assertIn(body['state'], ('PENDING', 'ONGOING'))

        # Verify cron interval is accepted
        self.assertEqual(body['interval'], cron_expr)
        _, audit = self.client.show_audit(body['uuid'])
        self.assert_expected(audit, body)


class TestCreateUpdateDeleteAuditV11(base.BaseInfraOptimTest):
    """Audit tests with microversion greater than 1.1"""
    min_microversion = '1.1'

    def assert_expected(self, expected, actual,
                        keys=('created_at', 'updated_at', 'next_run_time',
                              'deleted_at', 'state', 'hostname')):
        super(TestCreateUpdateDeleteAuditV11, self).assert_expected(
            expected, actual, keys)

    @decorators.idempotent_id('4f8a2c1e-6b3d-4e5a-9c7b-1a2e3f4d5c6b')
    def test_create_continuous_audit_with_start_end_time(self):
        """Test creating continuous audit with start_time and end_time"""
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])

        # Set start time to current time + 10 seconds
        start_time = datetime.now(tz=timezone.utc) + timedelta(seconds=10)

        # Set end time to current time + 1 hour
        end_time = datetime.now(tz=timezone.utc) + timedelta(hours=1)
        start_time_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")
        end_time_str = end_time.strftime("%Y-%m-%dT%H:%M:%S")

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='CONTINUOUS',
            interval='600',  # 10 minutes
            start_time=start_time_str,
            end_time=end_time_str,
        )

        _, body = self.create_audit(**audit_params)
        audit_params.pop('audit_template_uuid')
        audit_params['goal_uuid'] = goal['uuid']

        # Verify the audit was created with correct parameters
        self.assert_expected(audit_params, body)
        self.assertIn(body['state'], ('PENDING', 'ONGOING'))

        # Verify start_time and end_time are set correctly
        if 'start_time' in body:
            self.assertIsNotNone(body['start_time'])
        if 'end_time' in body:
            self.assertIsNotNone(body['end_time'])

        _, audit = self.client.show_audit(body['uuid'])
        self.assert_expected(audit, body)

    @decorators.idempotent_id('a1b2c3d4-5e6f-7890-1234-567890abcdef')
    def test_continuous_audit_actionplan_superseding(self):
        """Test action plan superseding behavior in continuous audits.

        Validates that when multiple action plans are created by the same
        continuous audit, only the latest remains RECOMMENDED while
        previous ones are automatically set to CANCELLED.
        """
        _, goal = self.client.show_goal("dummy")
        _, strategy = self.client.show_strategy("dummy")
        _, audit_template = self.create_audit_template(
            goal['uuid'], strategy=strategy['uuid'])

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='CONTINUOUS',
            interval='10',
        )

        _, body = self.create_audit(**audit_params)
        audit_uuid = body['uuid']

        # Wait for first action plan
        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(self.has_action_plans, audit_uuid),
            duration=300, sleep_for=10))

        # Wait for multiple action plans (superseding behavior)
        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(self._has_multiple_action_plans,
                                   audit_uuid),
            duration=180, sleep_for=10),
            "Failed to generate multiple action plans for superseding test")

        # Verify superseding: latest RECOMMENDED, previous CANCELLED
        _, action_plans = self.client.list_action_plans_detail(
            audit_uuid=audit_uuid)
        all_aps = action_plans.get("action_plans", [])

        # Count RECOMMENDED and CANCELLED action plans
        recommended_state = common_base.IdleStates.RECOMMENDED.value
        cancelled_state = common_base.IdleStates.CANCELLED.value

        recommended_aps = [ap for ap in all_aps
                           if ap.get('state') == recommended_state]

        cancelled_aps = [ap for ap in all_aps
                         if ap.get('state') == cancelled_state]

        # Verify exactly one RECOMMENDED (the latest)
        self.assertEqual(1, len(recommended_aps),
                         "Should have exactly 1 RECOMMENDED action plan")

        # Verify at least one CANCELLED (previous ones)
        self.assertGreaterEqual(len(cancelled_aps), 1,
                                "Should have at least 1 CANCELLED "
                                "action plan")

        # Verify the RECOMMENDED action plan is the latest one
        recommended_ap = recommended_aps[0]
        for cancelled_ap in cancelled_aps:
            self.assertGreater(recommended_ap.get('created_at'),
                               cancelled_ap.get('created_at'),
                               "RECOMMENDED action plan should be created "
                               "after CANCELLED ones")

    @decorators.idempotent_id('d4e5f678-9012-3456-def0-456789012345')
    def test_continuous_audit_interval_updates(self):
        """Test runtime interval updates via PATCH."""
        _, goal = self.client.show_goal("dummy")
        _, strategy = self.client.show_strategy("dummy")
        _, audit_template = self.create_audit_template(
            goal['uuid'], strategy=strategy['uuid'])

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='CONTINUOUS',
            interval='*/2 * * * *',
        )
        _, body = self.create_audit(**audit_params)
        audit_uuid = body['uuid']

        # Verify initial interval
        _, initial_audit = self.client.show_audit(audit_uuid)
        self.assertEqual("*/2 * * * *", initial_audit.get('interval'))

        # Update interval and verify change
        self.client.update_audit(audit_uuid, [
            {"op": "replace", "path": "/interval", "value": "*/1 * * * *"}])
        _, updated_audit = self.client.show_audit(audit_uuid)

        self.assertEqual("*/1 * * * *", updated_audit.get('interval'))

    @decorators.idempotent_id('e5f6a789-0123-4567-ef01-567890123456')
    def test_continuous_audit_crontab_formats(self):
        """Test various crontab expression formats."""
        _, goal = self.client.show_goal("dummy")
        _, strategy = self.client.show_strategy("dummy")

        test_formats = [
            ("*/1 * * * *", "every minute"),
            ("0 * * * *", "hourly"),
            ("30 */2 * * *", "every 2 hours at :30"),
            ("0 9 * * *", "daily at 9 AM")
        ]

        for cron_expr, description in test_formats:
            with self.subTest(cron_expr=cron_expr, description=description):
                _, test_audit_template = self.create_audit_template(
                    goal['uuid'], strategy=strategy['uuid'])

                test_audit_params = dict(
                    audit_template_uuid=test_audit_template['uuid'],
                    audit_type='CONTINUOUS',
                    interval=cron_expr,
                )

                _, test_body = self.create_audit(**test_audit_params)

                _, created_audit = self.client.show_audit(test_body['uuid'])
                self.assertEqual(cron_expr, created_audit.get('interval'))


class TestCreateUpdateDeleteAuditV14(base.BaseInfraOptimTest):
    """Audit tests with microversion greater than 1.4"""
    min_microversion = '1.4'

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('f26573d6-4020-4971-8868-495bffde982e')
    def test_create_audit_event(self):
        """Test Event Audit"""
        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])
        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='EVENT',
        )

        _, body = self.create_audit(**audit_params)
        audit_params.pop('audit_template_uuid')
        audit_params['goal_uuid'] = goal['uuid']
        self.assert_expected(audit_params, body)
        self.assertEqual(body['state'], 'PENDING')

        _, audit = self.client.show_audit(body['uuid'])
        self.assert_expected(audit, body)
        self.cancel_audit(body['uuid'])

        _, audit = self.client.show_audit(body['uuid'])
        self.assertEqual(audit['state'], 'CANCELLED')


class TestShowListAudit(base.BaseInfraOptimTest):
    """Tests for audit."""

    def setUp(self):
        super(TestShowListAudit, self).setUp()
        _, self.goal = self.client.show_goal("dummy")
        _, self.audit_template = self.create_audit_template(self.goal['uuid'])
        _, self.audit = self.create_audit(self.audit_template['uuid'])

        # Wait for audit to finish to prevent race conditions
        # during cleanup when running tests with high concurrency
        self.assertTrue(test_utils.call_until_true(
            func=functools.partial(
                self.has_audit_finished, self.audit['uuid']),
            duration=30,
            sleep_for=.5
        ))

    def assert_expected(self, expected, actual,
                        keys=('created_at', 'updated_at',
                              'deleted_at', 'state', 'hostname')):
        super(TestShowListAudit, self).assert_expected(
            expected, actual, keys)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('f1b31895-db1c-4a07-979c-dceb811bad98')
    def test_show_audit(self):
        _, audit = self.client.show_audit(
            self.audit['uuid'])

        initial_audit = self.audit.copy()
        audit_state = audit['state']
        actual_audit = audit.copy()

        self.assertIn(audit_state, common_base.AuditStates.values())
        # hostname may be None if audit state is
        # CANCELLED/DELETED/PENDING/SUSPENDED
        if audit_state in ('ONGOING', 'SUCCEEDED', 'FAILED'):
            self.assertIsNotNone(actual_audit['hostname'])
        self.assert_expected(initial_audit, actual_audit)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('4f5ced80-3082-43f5-8394-1cba1160d893')
    def test_show_audit_with_links(self):
        _, audit = self.client.show_audit(
            self.audit['uuid'])
        self.assertIn('links', audit.keys())
        self.assertEqual(2, len(audit['links']))
        self.assertIn(audit['uuid'],
                      audit['links'][0]['href'])

    @decorators.attr(type="smoke")
    @decorators.idempotent_id('14e720d7-ffb3-4c5f-8a5b-2510b31198e8')
    def test_list_audits(self):
        _, body = self.client.list_audits()
        self.assertIn(self.audit['uuid'],
                      [i['uuid'] for i in body['audits']])
        # Verify self links.
        for audit in body['audits']:
            self.validate_self_link('audits', audit['uuid'],
                                    audit['links'][0]['href'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('5175607c-f2df-4df6-9168-45c789b4a6ea')
    @decorators.skip_because(bug="2134046")
    def test_list_with_limit(self):
        # We create 3 extra audits to exceed the limit we fix
        for _ in range(3):
            self.create_audit(self.audit_template['uuid'])

        _, body = self.client.list_audits(limit=3)

        next_marker = body['audits'][-1]['uuid']
        self.assertEqual(3, len(body['audits']))
        self.assertIn(next_marker, body['next'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('beb25611-24a8-44e2-a381-923053fb282f')
    def test_list_audits_related_to_given_audit_template(self):
        _, body = self.client.list_audits(
            goal=self.goal['uuid'])
        self.assertIn(self.audit['uuid'], [n['uuid'] for n in body['audits']])
