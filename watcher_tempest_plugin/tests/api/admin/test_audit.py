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

from tempest.lib.common.utils import test_utils
from tempest.lib import decorators
from tempest.lib import exceptions

from watcher_tempest_plugin.tests.api.admin import base


class TestCreateUpdateDeleteAudit(base.BaseInfraOptimTest):
    """Tests for audit."""

    audit_states = ['ONGOING', 'SUCCEEDED', 'FAILED',
                    'CANCELLED', 'DELETED', 'PENDING', 'SUSPENDED']

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

        _, audit = self.update_audit(
            body['uuid'],
            [{'op': 'replace', 'path': '/state', 'value': 'CANCELLED'}]
        )

        test_utils.call_until_true(
            func=functools.partial(
                self.is_audit_idle, body['uuid']),
            duration=10,
            sleep_for=.5
        )

        _, audit = self.client.show_audit(body['uuid'])
        self.assertEqual(audit['state'], 'CANCELLED')

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('f26573d6-4020-4971-8868-495bffde982e')
    def test_create_audit_event(self):
        _, descr = self.client.get_api_description()
        if descr['versions']:
            max_version = descr['versions'][0]['max_version']
            # no EVENT type before microversion 1.4
            if max_version < '1.4':
                return

        _, goal = self.client.show_goal("dummy")
        _, audit_template = self.create_audit_template(goal['uuid'])

        audit_params = dict(
            audit_template_uuid=audit_template['uuid'],
            audit_type='EVENT',
            name='audit_event',
        )

        _, body = self.create_audit(**audit_params)
        audit_params.pop('audit_template_uuid')
        audit_params['goal_uuid'] = goal['uuid']
        self.assert_expected(audit_params, body)
        self.assertEqual(body['state'], 'PENDING')

        _, audit = self.client.show_audit(body['uuid'])
        self.assert_expected(audit, body)

        _, audit = self.update_audit(
            body['uuid'],
            [{'op': 'replace', 'path': '/state', 'value': 'CANCELLED'}]
        )

        test_utils.call_until_true(
            func=functools.partial(
                self.is_audit_idle, body['uuid']),
            duration=10,
            sleep_for=.5
        )

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
        self.assertIn(initial_audit_state, self.audit_states)

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

        _, audit = self.update_audit(
            audit_uuid,
            [{'op': 'replace', 'path': '/state', 'value': 'CANCELLED'}]
        )

        test_utils.call_until_true(
            func=functools.partial(
                self.is_audit_idle, audit_uuid),
            duration=10,
            sleep_for=.5
        )

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


class TestShowListAudit(base.BaseInfraOptimTest):
    """Tests for audit."""

    audit_states = ['ONGOING', 'SUCCEEDED', 'FAILED',
                    'CANCELLED', 'DELETED', 'PENDING', 'SUSPENDED']

    @classmethod
    def resource_setup(cls):
        super(TestShowListAudit, cls).resource_setup()
        _, cls.goal = cls.client.show_goal("dummy")
        _, cls.audit_template = cls.create_audit_template(cls.goal['uuid'])
        _, cls.audit = cls.create_audit(cls.audit_template['uuid'])

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

        self.assertIn(audit_state, self.audit_states)
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
