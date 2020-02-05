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
import time

from tempest import config
from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils
from tempest import test

from watcher_tempest_plugin import infra_optim_clients as clients

CONF = config.CONF


class BaseInfraOptimTest(test.BaseTestCase):
    """Base class for Infrastructure Optimization API tests."""

    # States where the object is waiting for some event to perform a transition
    IDLE_STATES = ('RECOMMENDED',
                   'FAILED',
                   'SUCCEEDED',
                   'CANCELLED',
                   'SUSPENDED')
    # States where the object can only be DELETED (end of its life-cycle)
    FINISHED_STATES = ('FAILED',
                       'SUCCEEDED',
                       'CANCELLED',
                       'SUPERSEDED')

    @classmethod
    def skip_checks(cls):
        super(BaseInfraOptimTest, cls).skip_checks()
        if not CONF.service_available.watcher:
            raise cls.skipException('Watcher support is required')

    @classmethod
    def setup_credentials(cls):
        super(BaseInfraOptimTest, cls).setup_credentials()
        cls.mgr = clients.AdminManager()

    @classmethod
    def setup_clients(cls):
        super(BaseInfraOptimTest, cls).setup_clients()
        cls.client = cls.mgr.io_client
        cls.gnocchi = cls.mgr.gn_client

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

    @classmethod
    def resource_cleanup(cls):
        """Ensure that all created objects get destroyed."""
        try:
            action_plans_to_be_deleted = set()
            # Phase 1: Make sure all objects are in an idle state
            for audit_uuid in cls.created_audits:
                test_utils.call_until_true(
                    func=functools.partial(
                        cls.is_audit_idle, audit_uuid),
                    duration=30,
                    sleep_for=.5
                )

            for audit_uuid in cls.created_action_plans_audit_uuids:
                _, action_plans = cls.client.list_action_plans(
                    audit_uuid=audit_uuid)
                action_plans_to_be_deleted.update(
                    ap['uuid'] for ap in action_plans['action_plans'])

                for action_plan in action_plans['action_plans']:
                    try:
                        test_utils.call_until_true(
                            func=functools.partial(
                                cls.is_action_plan_idle, action_plan['uuid']),
                            duration=30,
                            sleep_for=.5
                        )
                    except Exception:
                        action_plans_to_be_deleted.remove(
                            action_plan['uuid'])

            # Phase 2: Delete them all
            for action_plan_uuid in action_plans_to_be_deleted:
                cls.delete_action_plan(action_plan_uuid)

            for audit_uuid in cls.created_audits.copy():
                cls.delete_audit(audit_uuid)

            for audit_template_uuid in cls.created_audit_templates.copy():
                cls.delete_audit_template(audit_template_uuid)

        finally:
            super(BaseInfraOptimTest, cls).resource_cleanup()

    @classmethod
    def _are_all_action_plans_finished(cls):
        _, action_plans = cls.client.list_action_plans()
        return all([ap['state'] in cls.IDLE_STATES
                    for ap in action_plans['action_plans']])

    @classmethod
    def wait_for_all_action_plans_to_finish(cls):
        assert test_utils.call_until_true(
            func=cls._are_all_action_plans_finished,
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

    # ### AUDIT TEMPLATES ### #

    @classmethod
    def create_audit_template(cls, goal, name=None, description=None,
                              strategy=None, scope=None):
        """Wrapper utility for creating a test audit template

        :param goal: Goal UUID or name related to the audit template.
        :param name: The name of the audit template. Default: My Audit Template
        :param description: The description of the audit template.
        :param strategy: Strategy UUID or name related to the audit template.
        :param scope: Scope that will be applied on all derived audits.
        :return: A tuple with The HTTP response and its body
        """
        description = description or data_utils.rand_name(
            'test-audit_template')
        resp, body = cls.client.create_audit_template(
            name=name, description=description,
            goal=goal, strategy=strategy, scope=scope)

        cls.created_audit_templates.add(body['uuid'])

        return resp, body

    @classmethod
    def delete_audit_template(cls, uuid):
        """Deletes a audit_template having the specified UUID

        :param uuid: The unique identifier of the audit template
        :return: Server response
        """
        resp, _ = cls.client.delete_audit_template(uuid)

        if uuid in cls.created_audit_templates:
            cls.created_audit_templates.remove(uuid)

        return resp

    # ### AUDITS ### #

    @classmethod
    def create_audit(cls, audit_template_uuid, audit_type='ONESHOT',
                     state=None, interval=None, parameters=None, name=None):
        """Wrapper utility for creating a test audit

        :param audit_template_uuid: Audit Template UUID this audit will use
        :param audit_type: Audit type (either ONESHOT or CONTINUOUS)
        :param state: Audit state (str)
        :param interval: Audit interval in seconds or cron syntax (str)
        :param parameters: list of execution parameters
        :return: A tuple with The HTTP response and its body
        """
        # if actionplan is running, create_audit will fail, we retry 5 times.
        retry = 5
        audit_success = False
        cls.wait_for_all_action_plans_to_finish()
        while not audit_success and retry:
            resp, body = cls.client.create_audit(
                audit_template_uuid=audit_template_uuid,
                audit_type=audit_type, state=state, interval=interval,
                parameters=parameters, name=name)
            audit_uuid = body['uuid']
            test_utils.call_until_true(
                func=functools.partial(cls.has_audit_finished, audit_uuid),
                duration=30,
                sleep_for=2
            )
            if cls.has_audit_failed(audit_uuid):
                audit_success = False
                cls.delete_audit(audit_uuid)
                time.sleep(5)
            else:
                audit_success = True
            retry -= 1

        assert audit_success
        cls.created_audits.add(body['uuid'])
        cls.created_action_plans_audit_uuids.add(body['uuid'])

        return resp, body

    @classmethod
    def update_audit(cls, audit_uuid, patch):
        """Update an audit with proposed patch

        :param audit_uuid: The unique identifier of the audit.
        :param patch: List of dicts representing json patches.
        :return: A tuple with The HTTP response and its body
        """
        resp, body = cls.client.update_audit(
            audit_uuid=audit_uuid, patch=patch)

        return resp, body

    @classmethod
    def delete_audit(cls, audit_uuid):
        """Deletes an audit having the specified UUID

        :param audit_uuid: The unique identifier of the audit.
        :return: the HTTP response
        """
        _, audit = cls.client.show_audit(audit_uuid)
        if audit.get('state') == 'ONGOING':
            cls.update_audit(
                audit_uuid,
                [{'op': 'replace', 'path': '/state', 'value': 'CANCELLED'}]
            )
        resp, _ = cls.client.delete_audit(audit_uuid)

        if audit_uuid in cls.created_audits:
            cls.created_audits.remove(audit_uuid)

        return resp

    @classmethod
    def has_audit_succeeded(cls, audit_uuid):
        _, audit = cls.client.show_audit(audit_uuid)
        return audit.get('state') == 'SUCCEEDED'

    @classmethod
    def has_audit_finished(cls, audit_uuid):
        _, audit = cls.client.show_audit(audit_uuid)
        finished_states = cls.FINISHED_STATES
        if audit.get('audit_type') == 'CONTINUOUS':
            finished_states += ('ONGOING',)
        return audit.get('state') in finished_states

    @classmethod
    def has_audit_failed(cls, audit_uuid):
        _, audit = cls.client.show_audit(audit_uuid)
        return audit.get('state') in ('FAILED',
                                      'CANCELLED',
                                      'SUPERSEDED')

    @classmethod
    def is_audit_idle(cls, audit_uuid):
        _, audit = cls.client.show_audit(audit_uuid)
        return audit.get('state') in cls.IDLE_STATES

    @classmethod
    def is_audit_ongoing(cls, audit_uuid):
        _, audit = cls.client.show_audit(audit_uuid)
        return audit.get('state') == 'ONGOING'

    # ### ACTION PLANS ### #

    @classmethod
    def create_action_plan(cls, audit_template_uuid, **audit_kwargs):
        """Wrapper utility for creating a test action plan

        :param audit_template_uuid: Audit template UUID to use
        :param audit_kwargs: Dict of audit properties to set
        :return: The action plan as dict
        """
        _, audit = cls.create_audit(audit_template_uuid, **audit_kwargs)
        audit_uuid = audit['uuid']

        assert test_utils.call_until_true(
            func=functools.partial(cls.has_audit_finished, audit_uuid),
            duration=30,
            sleep_for=.5
        )

        _, action_plans = cls.client.list_action_plans(audit_uuid=audit_uuid)
        if len(action_plans['action_plans']) == 0:
            return

        return action_plans['action_plans'][0]

    @classmethod
    def start_action_plan(cls, action_plan_uuid):
        """Starts an action plan having the specified UUID

        :param action_plan_uuid: The unique identifier of the action plan.
        :return: the HTTP response
        """
        resp, _ = cls.client.start_action_plan(action_plan_uuid)

        test_utils.call_until_true(
            func=functools.partial(
                cls.is_action_plan_idle, action_plan_uuid),
            duration=30,
            sleep_for=.5
        )

        return resp

    @classmethod
    def delete_action_plan(cls, action_plan_uuid):
        """Deletes an action plan having the specified UUID

        :param action_plan_uuid: The unique identifier of the action plan.
        :return: the HTTP response
        """
        resp, _ = cls.client.delete_action_plan(action_plan_uuid)

        if action_plan_uuid in cls.created_action_plans_audit_uuids:
            cls.created_action_plans_audit_uuids.remove(action_plan_uuid)

        return resp

    @classmethod
    def is_action_plan_idle(cls, action_plan_uuid):
        """This guard makes sure your action plan is not running"""
        _, action_plan = cls.client.show_action_plan(action_plan_uuid)
        return action_plan.get('state') in cls.IDLE_STATES
