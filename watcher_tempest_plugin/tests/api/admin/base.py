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

from tempest import config
from tempest.lib.common import api_version_utils
from tempest.lib.common.utils import test_utils
from tempest import test

from watcher_tempest_plugin import infra_optim_clients as clients
from watcher_tempest_plugin.services.infra_optim.v1.json import (
    api_microversion_fixture
)
from watcher_tempest_plugin.tests.common import base

CONF = config.CONF


class BaseInfraOptimTest(api_version_utils.BaseMicroversionTest,
                         test.BaseTestCase,
                         base.WatcherHelperMixin):
    """Base class for Infrastructure Optimization API tests."""

    @classmethod
    def skip_checks(cls):
        super(BaseInfraOptimTest, cls).skip_checks()
        if not CONF.service_available.watcher:
            raise cls.skipException('Watcher support is required')

        api_version_utils.check_skip_with_microversion(
            cls.min_microversion,
            cls.max_microversion,
            CONF.optimize.min_microversion,
            CONF.optimize.max_microversion)

    @classmethod
    def setup_credentials(cls):
        super(BaseInfraOptimTest, cls).setup_credentials()
        cls.mgr = clients.AdminManager()

    @classmethod
    def setup_clients(cls):
        super(BaseInfraOptimTest, cls).setup_clients()
        cls.client = cls.mgr.io_client
        cls.gnocchi = cls.mgr.gn_client

    def setUp(self):
        super(BaseInfraOptimTest, self).setUp()
        self.useFixture(api_microversion_fixture.APIMicroversionFixture(
            optimize_microversion=self.request_microversion))

    @classmethod
    def resource_setup(cls):
        super(BaseInfraOptimTest, cls).resource_setup()

        # Set of all created audit templates UUIDs
        cls.created_audit_templates = set()
        # Set of all created audit UUIDs
        cls.created_audits = set()
        # Set of all created audit UUIDs. We use it to build the list of
        # action plans to delete (including potential orphan one(s))
        cls.created_action_plans_audit_uuids = set()

        cls.request_microversion = (
            api_version_utils.select_request_microversion(
                cls.min_microversion,
                CONF.optimize.min_microversion))

    @classmethod
    def resource_cleanup(cls):
        """Ensure that all created objects get destroyed."""
        super(BaseInfraOptimTest, cls).resource_cleanup()

    def _are_all_action_plans_finished(self):
        _, action_plans = self.client.list_action_plans()
        return all([ap['state'] in self.IDLE_STATES.values()
                    for ap in action_plans['action_plans']])

    def wait_for_all_action_plans_to_finish(self):
        assert test_utils.call_until_true(
            func=self._are_all_action_plans_finished,
            duration=300,
            sleep_for=5
        )

    def validate_self_link(self, resource, uuid, link):
        """Check whether the given self link formatted correctly."""
        expected_link = "{base}/{pref}/{res}/{uuid}".format(
            base='https?://[^/]*',
            pref=self.client.URI_PREFIX,
            res=resource,
            uuid=uuid
        )
        self.assertRegex(link, expected_link)

    def assert_expected(self, expected, actual,
                        keys=('created_at', 'updated_at', 'deleted_at')):
        # Check if not expected keys/values exists in actual response body
        for key, value in expected.items():
            if key not in keys:
                self.assertIn(key, actual)
                self.assertEqual(value, actual[key])
