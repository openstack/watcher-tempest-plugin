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

from oslo_utils import uuidutils

from tempest.lib import decorators
from tempest.lib import exceptions

from watcher_tempest_plugin.tests.api.admin import base


class TestCreateDeleteAuditTemplate(base.BaseInfraOptimTest):
    """Tests on audit templates"""

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('51e48dd3-a32f-4a82-b8e9-ca9e897f88ed')
    def test_create_audit_template(self):
        goal_name = "dummy"
        _, goal = self.client.show_goal(goal_name)

        params = {
            'name': 'my at name %s' % uuidutils.generate_uuid(),
            'description': 'my at description',
            'goal': goal['uuid']}
        expected_data = {
            'name': params['name'],
            'description': params['description'],
            'goal_uuid': params['goal'],
            'goal_name': goal_name,
            'strategy_uuid': None,
            'strategy_name': None}

        _, body = self.create_audit_template(**params)
        self.assert_expected(expected_data, body)

        _, audit_template = self.client.show_audit_template(body['uuid'])
        self.assert_expected(audit_template, body)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('9f1ccd3e-fbe0-4c59-8e0d-b720593e1519')
    def test_create_audit_template_unicode_description(self):
        goal_name = "dummy"
        _, goal = self.client.show_goal(goal_name)
        # Use a unicode string for testing:
        params = {
            'name': 'my at name %s' % uuidutils.generate_uuid(),
            'description': 'my àt déscrïptïôn',
            'goal': goal['uuid']}

        expected_data = {
            'name': params['name'],
            'description': params['description'],
            'goal_uuid': params['goal'],
            'goal_name': goal_name,
            'strategy_uuid': None,
            'strategy_name': None}

        _, body = self.create_audit_template(**params)
        self.assert_expected(expected_data, body)

        _, audit_template = self.client.show_audit_template(body['uuid'])
        self.assert_expected(audit_template, body)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('7dcaf918-9744-4b1c-aa05-1ccb4b077a57')
    def test_delete_audit_template(self):
        _, goal = self.client.show_goal("dummy")
        _, body = self.create_audit_template(goal=goal['uuid'])
        audit_uuid = body['uuid']

        self.delete_audit_template(audit_uuid)

        self.assertRaises(exceptions.NotFound, self.client.show_audit_template,
                          audit_uuid)


class TestAuditTemplate(base.BaseInfraOptimTest):
    """Tests for audit_template."""

    @classmethod
    def resource_setup(cls):
        super(TestAuditTemplate, cls).resource_setup()
        _, cls.goal = cls.client.show_goal("dummy")
        _, cls.strategy = cls.client.show_strategy("dummy")
        _, cls.audit_template = cls.create_audit_template(
            goal=cls.goal['uuid'], strategy=cls.strategy['uuid'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('93f98a9c-b892-48c5-a60a-a56d78bb8c3b')
    def test_show_audit_template(self):
        _, audit_template = self.client.show_audit_template(
            self.audit_template['uuid'])

        self.assert_expected(self.audit_template, audit_template)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('a071dd02-8fa7-4c71-bbb9-1293589a1a1a')
    def test_filter_audit_template_by_goal_uuid(self):
        _, audit_templates = self.client.list_audit_templates(
            goal=self.audit_template['goal_uuid'])

        audit_template_uuids = [
            at["uuid"] for at in audit_templates['audit_templates']]
        self.assertIn(self.audit_template['uuid'], audit_template_uuids)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('0a037446-1a04-415f-810d-5953edfa12a9')
    def test_filter_audit_template_by_strategy_uuid(self):
        _, audit_templates = self.client.list_audit_templates(
            strategy=self.audit_template['strategy_uuid'])

        audit_template_uuids = [
            at["uuid"] for at in audit_templates['audit_templates']]
        self.assertIn(self.audit_template['uuid'], audit_template_uuids)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('17c06b01-88a7-41e8-9b1f-2650b4854832')
    def test_show_audit_template_with_links(self):
        _, audit_template = self.client.show_audit_template(
            self.audit_template['uuid'])
        self.assertIn('links', audit_template.keys())
        self.assertEqual(2, len(audit_template['links']))
        self.assertIn(audit_template['uuid'],
                      audit_template['links'][0]['href'])

    @decorators.attr(type="smoke")
    @decorators.idempotent_id('70ff0bb3-c3be-432c-ab51-5dd094ee9160')
    def test_list_audit_templates(self):
        _, body = self.client.list_audit_templates()
        self.assertIn(self.audit_template['uuid'],
                      [i['uuid'] for i in body['audit_templates']])
        # Verify self links.
        for audit_template in body['audit_templates']:
            self.validate_self_link('audit_templates', audit_template['uuid'],
                                    audit_template['links'][0]['href'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('47f135ef-056a-48ec-9df7-dc64b9092cbd')
    def test_list_with_limit(self):
        # We create 3 extra audit templates to exceed the limit we fix
        for _ in range(3):
            self.create_audit_template(self.goal['uuid'])

        _, body = self.client.list_audit_templates(limit=3)

        next_marker = body['audit_templates'][-1]['uuid']
        self.assertEqual(3, len(body['audit_templates']))
        self.assertIn(next_marker, body['next'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('41f02098-e043-4b66-96f1-c1461994a95a')
    def test_update_audit_template_replace(self):
        _, new_goal = self.client.show_goal("server_consolidation")
        _, new_strategy = self.client.show_strategy("basic")

        params = {'name': 'my at name %s' % uuidutils.generate_uuid(),
                  'description': 'my at description',
                  'goal': self.goal['uuid']}

        _, body = self.create_audit_template(**params)

        new_name = 'my at new name %s' % uuidutils.generate_uuid()
        new_description = 'my new at description'

        patch = [{'path': '/name',
                  'op': 'replace',
                  'value': new_name},
                 {'path': '/description',
                  'op': 'replace',
                  'value': new_description},
                 {'path': '/goal',
                  'op': 'replace',
                  'value': new_goal['uuid']},
                 {'path': '/strategy',
                  'op': 'replace',
                  'value': new_strategy['uuid']}]

        self.client.update_audit_template(body['uuid'], patch)

        _, body = self.client.show_audit_template(body['uuid'])
        self.assertEqual(new_name, body['name'])
        self.assertEqual(new_description, body['description'])
        self.assertEqual(new_goal['uuid'], body['goal_uuid'])
        self.assertEqual(new_strategy['uuid'], body['strategy_uuid'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('c2afac59-f8ea-41b1-bdd4-cc2c25170cf5')
    def test_update_audit_template_remove(self):
        description = 'my at description'
        name = 'my at name %s' % uuidutils.generate_uuid()
        params = {'name': name,
                  'description': description,
                  'goal': self.goal['uuid']}

        _, audit_template = self.create_audit_template(**params)

        # Removing the description
        self.client.update_audit_template(
            audit_template['uuid'],
            [{'path': '/description', 'op': 'remove'}])

        _, body = self.client.show_audit_template(audit_template['uuid'])
        self.assertIsNone(body.get('description'))

        # Assert nothing else was changed
        self.assertEqual(name, body['name'])
        self.assertIsNone(body['description'])
        self.assertEqual(self.goal['uuid'], body['goal_uuid'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('b2555a7f-1f8b-48d1-8ab2-9b957ba06a5b')
    def test_update_audit_template_add(self):
        params = {'name': 'my at name %s' % uuidutils.generate_uuid(),
                  'goal': self.goal['uuid']}

        _, body = self.create_audit_template(**params)

        patch = [{'path': '/description', 'op': 'add', 'value': 'description'}]

        self.client.update_audit_template(body['uuid'], patch)

        _, body = self.client.show_audit_template(body['uuid'])
        self.assertEqual('description', body['description'])
