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

from tempest.lib import decorators

from watcher_tempest_plugin.tests.api.admin import base


class TestApiDiscovery(base.BaseInfraOptimTest):
    """Tests for API discovery features."""

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('e5c9cfc5-1890-4e8e-949e-ab2dca4d5595')
    def test_api_versions(self):
        _, descr = self.client.get_api_description()
        expected_versions = ('v1',)
        versions = [version['id'] for version in descr['versions']]

        for v in expected_versions:
            self.assertIn(v, versions)

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('60602d80-fac7-44cc-a207-275dfcb62112')
    def test_default_version(self):
        _, descr = self.client.get_api_description()
        default_version = descr['default_version']
        self.assertEqual('v1', default_version['id'])

    @decorators.attr(type='smoke')
    @decorators.idempotent_id('79e4bfd1-a349-4dd3-bb32-e24586649255')
    def test_version_1_resources(self):
        _, descr = self.client.get_version_description(version='v1')
        expected_resources = ('audit_templates', 'audits', 'action_plans',
                              'actions', 'links', 'media_types')

        for res in expected_resources:
            self.assertIn(res, descr)
