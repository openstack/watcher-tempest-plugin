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
#

import enum
import functools

from collections import abc

from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils
from tempest.lib import exceptions


class FrozenEnumMeta(enum.EnumMeta):
    """Prevent creation of new attributes and behave like a mapping."""

    def __getattr__(self, name):
        if name not in self._member_map_:
            raise AttributeError(
                f'{self.__class__.__name__} {self.__name__} has no '
                f'attribute {name!r}'
            )
        return super().__getattr__(name)

    def __setattr__(self, name, value):
        if name in self.__dict__ or name in self._member_map_:
            return super().__setattr__(name, value)
        raise AttributeError(
            f'{self.__class__.__name__} {self.__name__} has no '
            f'attribute {name!r}'
        )

    # Mapping interface

    def keys(self):
        return abc.KeysView(self)

    def items(self):
        return abc.ItemsView(self)

    def values(self):
        return abc.ValuesView(self)


def freeze(enum_class):
    enum_class.__class__ = FrozenEnumMeta
    return enum_class


@freeze
class IdleStates(str, enum.Enum):
    RECOMMENDED = 'RECOMMENDED'
    FAILED = 'FAILED'
    SUCCEEDED = 'SUCCEEDED'
    CANCELLED = 'CANCELLED'
    SUPERSEDED = 'SUPERSEDED'
    SUSPENDED = 'SUSPENDED'


# Audit finished states
@freeze
class AuditFinishedStates(str, enum.Enum):
    FAILED = 'FAILED'
    SUCCEEDED = 'SUCCEEDED'
    CANCELLED = 'CANCELLED'
    SUSPENDED = 'SUSPENDED'


# Action plan finished states
@freeze
class ActionPlanFinishedStates(str, enum.Enum):
    FAILED = 'FAILED'
    SUCCEEDED = 'SUCCEEDED'
    CANCELLED = 'CANCELLED'
    SUPERSEDED = 'SUPERSEDED'


# All audit states
@freeze
class AuditStates(str, enum.Enum):
    ONGOING = 'ONGOING'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'
    CANCELLED = 'CANCELLED'
    DELETED = 'DELETED'
    PENDING = 'PENDING'
    SUSPENDED = 'SUSPENDED'


class WatcherHelperMixin:
    """Mixin class providing helper utilities for Watcher resources."""

    # Aliases for accessing enum values without importing the module
    IDLE_STATES = IdleStates
    AUDIT_FINISHED_STATES = AuditFinishedStates
    ACTIONPLAN_FINISHED_STATES = ActionPlanFinishedStates

    # ### AUDIT TEMPLATES ### #

    def create_audit_template(self, goal, name=None, description=None,
                              strategy=None, scope=None):
        """Wrapper utility for creating a test audit template

        :param goal: Goal UUID or name related to the audit template.
        :param name: The name of the audit template. Default: My Audit Template
        :param description: The description of the audit template.
        :param strategy: Strategy UUID or name related to the audit template.
        :param scope: Audit scope
        :return: A tuple with The HTTP response and its body
        """
        description = description or data_utils.rand_name(
            'test-audit_template')
        resp, body = self.client.create_audit_template(
            name=name, description=description, goal=goal,
            strategy=strategy, scope=scope)

        self.addCleanup(
            test_utils.call_and_ignore_notfound_exc,
            self.delete_audit_template,
            audit_template_uuid=body["uuid"]
        )

        return resp, body

    def delete_audit_template(self, audit_template_uuid):
        """Deletes a audit_template having the specified UUID

        :param audit_template_uuid: The unique identifier of the audit template
        :return: Server response
        """
        try:
            resp, _ = self.client.delete_audit_template(audit_template_uuid)
        except exceptions.NotFound:
            # Resource might already be deleted
            resp = None
        return resp

    # ### AUDITS ### #

    def create_audit(self, audit_template_uuid, audit_type='ONESHOT',
                     state=None, interval=None, parameters=None, **kwargs):
        """Wrapper utility for creating a test audit

        :param audit_template_uuid: Audit Template UUID this audit will use
        :param audit_type: Audit type (either ONESHOT or CONTINUOUS)
        :param state: Audit state (str)
        :param interval: Audit interval in seconds (int)
        :param parameters: list of execution parameters
        :param kwargs: Additional keyword arguments (e.g., name)
        :return: A tuple with The HTTP response and its body
        """
        resp, body = self.client.create_audit(
            audit_template_uuid=audit_template_uuid, audit_type=audit_type,
            state=state, interval=interval, parameters=parameters, **kwargs)

        self.addCleanup(test_utils.call_and_ignore_notfound_exc,
                        self.delete_audit,
                        audit_uuid=body["uuid"])
        return resp, body

    def update_audit(self, audit_uuid, patch):
        """Update an audit with proposed patch

        :param audit_uuid: The unique identifier of the audit.
        :param patch: List of dicts representing json patches.
        :return: A tuple with The HTTP response and its body
        """
        resp, body = self.client.update_audit(
            audit_uuid=audit_uuid, patch=patch)

        return resp, body

    def cancel_audit(self, audit_uuid):
        """Cancel an audit and wait until it becomes finished.

        Handles race conditions where the audit may have already finished
        between the caller's state check and this cancellation attempt.
        """
        try:
            self.update_audit(
                audit_uuid,
                [{'op': 'replace', 'path': '/state', 'value': 'CANCELLED'}]
            )
        except exceptions.BadRequest as e:
            # Audit may have finished already (race condition)
            # Ignore state transition errors, re-raise other BadRequest errors
            if 'State transition not allowed' not in str(e):
                raise
            # If it's a state transition error, audit is already in a
            # finished state, so no need to wait
            return

        test_utils.call_until_true(
            func=functools.partial(
                self.has_audit_finished, audit_uuid),
            duration=60,
            sleep_for=2
        )

    def is_audit_idle(self, audit_uuid):
        """Check if an audit is in an idle state

        :param audit_uuid: The unique identifier of the audit.
        :return: True if the audit is idle, False otherwise
        """
        try:
            _, audit = self.client.show_audit(audit_uuid)
            return audit.get('state') in self.IDLE_STATES.values()
        except exceptions.NotFound:
            # Audit was deleted, consider it idle
            return True

    def has_audit_succeeded(self, audit_uuid):
        _, audit = self.client.show_audit(audit_uuid)
        return audit.get('state') == IdleStates.SUCCEEDED.value

    def has_audit_finished(self, audit_uuid):
        _, audit = self.client.show_audit(audit_uuid)
        finished_states = self.AUDIT_FINISHED_STATES.values()
        if audit.get('audit_type') == 'CONTINUOUS':
            # For continuous audits, also include ONGOING as a finished state
            return (audit.get('state') in finished_states
                    or audit.get('state') == 'ONGOING')
        return audit.get('state') in finished_states

    def has_audit_failed(self, audit_uuid):
        _, audit = self.client.show_audit(audit_uuid)
        return audit.get('state') in (AuditFinishedStates.FAILED.value,
                                      AuditFinishedStates.CANCELLED.value,
                                      AuditFinishedStates.SUSPENDED.value)

    def is_audit_ongoing(self, audit_uuid):
        _, audit = self.client.show_audit(audit_uuid)
        return audit.get('state') == 'ONGOING'

    def delete_audit(self, audit_uuid):
        """Deletes an audit having the specified UUID

        :param audit_uuid: The unique identifier of the audit.
        :return: the HTTP response
        """
        try:
            _, audit = self.client.show_audit(audit_uuid)

            # Cancel the audit if it's in a state that prevents deletion
            if audit.get('state') in ('ONGOING', 'PENDING'):
                self.cancel_audit(audit_uuid)

            _, action_plans = self.client.list_action_plans(
                audit_uuid=audit_uuid)
            for action_plan in action_plans.get("action_plans", []):
                try:
                    self.delete_action_plan(
                        action_plan_uuid=action_plan["uuid"])
                except exceptions.NotFound:
                    # Action plan might already be deleted
                    pass

            resp, _ = self.client.delete_audit(audit_uuid)
        except exceptions.NotFound:
            resp = None
        except exceptions.BadRequest as e:
            # Handle cases where audit cannot be deleted due to state
            # This can happen during cleanup if there's a race condition
            if "Couldn't delete when state is" in str(e):
                # Audit is in a non-deletable state, skip deletion
                # This is acceptable during cleanup
                resp = None
            else:
                # Re-raise other BadRequest errors
                raise

        return resp

    # ### ACTION PLANS ### #

    def create_action_plan(self, audit_template_uuid, **audit_kwargs):
        """Wrapper utility for creating a test action plan

        This method creates an audit and waits for it to finish. If the audit
        completes successfully and produces recommendations, an action plan
        will be returned. Otherwise, None is returned.

        :param audit_template_uuid: Audit template UUID to use
        :param audit_kwargs: Dict of audit properties to set
        :return: The action plan as dict, or None if no action plan was created
        """
        _, audit = self.create_audit(audit_template_uuid, **audit_kwargs)
        audit_uuid = audit['uuid']

        assert test_utils.call_until_true(
            func=functools.partial(self.has_audit_finished, audit_uuid),
            duration=30,
            sleep_for=.5
        ), "Audit %s did not finish within expected time" % audit_uuid

        _, action_plans = self.client.list_action_plans(audit_uuid=audit_uuid)
        if len(action_plans['action_plans']) == 0:
            # No action plan was created - this can happen if the audit
            # failed or produced no recommendations
            return

        action_plan = action_plans['action_plans'][0]
        self.addCleanup(test_utils.call_and_ignore_notfound_exc,
                        self.delete_action_plan,
                        action_plan_uuid=action_plan["uuid"])

        return action_plan

    def start_action_plan(self, action_plan_uuid):
        """Starts an action plan having the specified UUID

        :param action_plan_uuid: The unique identifier of the action plan.
        :return: the HTTP response
        """
        resp, _ = self.client.start_action_plan(action_plan_uuid)

        test_utils.call_until_true(
            func=functools.partial(
                self.is_action_plan_idle, action_plan_uuid),
            duration=30,
            sleep_for=.5
        )

        return resp

    def is_action_plan_idle(self, action_plan_uuid):
        """This guard makes sure your action plan is not running"""
        _, action_plan = self.client.show_action_plan(action_plan_uuid)
        return action_plan.get('state') in self.IDLE_STATES.values()

    def delete_action_plan(self, action_plan_uuid):
        """Deletes an action plan having the specified UUID

        :param action_plan_uuid: The unique identifier of the action plan.
        :return: the HTTP response
        """
        try:
            resp, _ = self.client.delete_action_plan(action_plan_uuid)
        except exceptions.NotFound:
            # Action plan might already be deleted
            resp = None
        return resp

    def has_action_plans(self, audit_uuid=None):
        """Check if there are any action plans for the given audit.

        :param audit_uuid: The unique identifier of the audit (optional).
        :return: True if action plans exist, False otherwise
        """
        _, action_plans = self.client.list_action_plans(audit_uuid=audit_uuid)
        return len(action_plans['action_plans']) > 0

    def _has_multiple_action_plans(self, audit_uuid):
        """Check if there are multiple action plans for the given audit.

        :param audit_uuid: The unique identifier of the audit.
        :return: True if multiple action plans exist, False otherwise
        """
        _, action_plans = self.client.list_action_plans(audit_uuid=audit_uuid)
        return len(action_plans['action_plans']) > 1
