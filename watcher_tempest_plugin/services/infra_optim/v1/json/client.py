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

from oslo_serialization import jsonutils
from oslo_utils import uuidutils
from watcher_tempest_plugin.services import base


INFRA_OPTIM_VERSION = '1.4'


class InfraOptimClientJSON(base.BaseClient):
    """Base Tempest REST client for Watcher API v1."""

    URI_PREFIX = 'v1'

    api_microversion_header_name = 'OpenStack-API-Version'

    def get_headers(self):
        headers = super(InfraOptimClientJSON, self).get_headers()
        if INFRA_OPTIM_VERSION:
            headers[self.api_microversion_header_name] = (
                " ".join(["infra-optim", INFRA_OPTIM_VERSION]))
        return headers

    def serialize(self, object_dict):
        """Serialize an Watcher object."""
        return jsonutils.dumps(object_dict)

    def deserialize(self, object_str):
        """Deserialize an Watcher object."""
        return jsonutils.loads(object_str.decode('utf-8'))

    # ### AUDIT TEMPLATES ### #

    @base.handle_errors
    def list_audit_templates(self, **kwargs):
        """List all existing audit templates."""
        return self._list_request('audit_templates', **kwargs)

    @base.handle_errors
    def list_audit_templates_detail(self, **kwargs):
        """Lists details of all existing audit templates."""
        return self._list_request('/audit_templates/detail', **kwargs)

    @base.handle_errors
    def show_audit_template(self, audit_template_uuid):
        """Gets a specific audit template.

        :param audit_template_uuid: Unique identifier of the audit template
        :return: Serialized audit template as a dictionary.
        """
        return self._show_request('audit_templates', audit_template_uuid)

    @base.handle_errors
    def create_audit_template(self, **kwargs):
        """Creates an audit template with the specified parameters.

        :param name: The name of the audit template.
        :param description: The description of the audit template.
        :param goal_uuid: The related Goal UUID associated.
        :param strategy_uuid: The related Strategy UUID associated.
        :param audit_scope: Scope the audit should apply to.
        :return: A tuple with the server response and the created audit
                 template.
        """

        parameters = {k: v for k, v in kwargs.items() if v is not None}
        # This name is unique to avoid the DB unique constraint on names
        unique_name = '%s' % uuidutils.generate_uuid()

        audit_template = {
            'name': parameters.get('name', unique_name),
            'description': parameters.get('description'),
            'goal': parameters.get('goal'),
            'strategy': parameters.get('strategy'),
            'scope': parameters.get('scope', []),
        }

        return self._create_request('audit_templates', audit_template)

    @base.handle_errors
    def delete_audit_template(self, audit_template_uuid):
        """Deletes an audit template having the specified UUID.

        :param audit_template_uuid: The unique identifier of the audit template
        :return: A tuple with the server response and the response body.
        """

        return self._delete_request('audit_templates', audit_template_uuid)

    @base.handle_errors
    def update_audit_template(self, audit_template_uuid, patch):
        """Update the specified audit template.

        :param audit_template_uuid: The unique identifier of the audit template
        :param patch: List of dicts representing json patches.
        :return: A tuple with the server response and the updated audit
            template.
        """

        return self._patch_request('audit_templates',
                                   audit_template_uuid, patch)

    # ### AUDITS ### #

    @base.handle_errors
    def list_audits(self, **kwargs):
        """List all existing audit templates."""
        return self._list_request('audits', **kwargs)

    @base.handle_errors
    def list_audits_detail(self, **kwargs):
        """Lists details of all existing audit templates."""
        return self._list_request('/audits/detail', **kwargs)

    @base.handle_errors
    def show_audit(self, audit_uuid):
        """Gets a specific audit template.

        :param audit_uuid: Unique identifier of the audit template
        :return: Serialized audit template as a dictionary
        """
        return self._show_request('audits', audit_uuid)

    @base.handle_errors
    def create_audit(self, audit_template_uuid, **kwargs):
        """Create an audit with the specified parameters

        :param audit_template_uuid: Audit template ID used by the audit
        :return: A tuple with the server response and the created audit
        """
        audit = {'audit_template_uuid': audit_template_uuid}
        audit.update(kwargs)
        if not audit['state']:
            del audit['state']

        return self._create_request('audits', audit)

    @base.handle_errors
    def delete_audit(self, audit_uuid):
        """Deletes an audit having the specified UUID

        :param audit_uuid: The unique identifier of the audit
        :return: A tuple with the server response and the response body
        """

        return self._delete_request('audits', audit_uuid)

    @base.handle_errors
    def update_audit(self, audit_uuid, patch):
        """Update the specified audit.

        :param audit_uuid: The unique identifier of the audit
        :param patch: List of dicts representing json patches.
        :return: Tuple with the server response and the updated audit
        """

        return self._patch_request('audits', audit_uuid, patch)

    # ### ACTION PLANS ### #

    @base.handle_errors
    def list_action_plans(self, **kwargs):
        """List all existing action plan"""
        return self._list_request('action_plans', **kwargs)

    @base.handle_errors
    def list_action_plans_detail(self, **kwargs):
        """Lists details of all existing action plan"""
        return self._list_request('/action_plans/detail', **kwargs)

    @base.handle_errors
    def show_action_plan(self, action_plan_uuid):
        """Gets a specific action plan

        :param action_plan_uuid: Unique identifier of the action plan
        :return: Serialized action plan as a dictionary
        """
        return self._show_request('/action_plans', action_plan_uuid)

    @base.handle_errors
    def delete_action_plan(self, action_plan_uuid):
        """Deletes an action plan having the specified UUID

        :param action_plan_uuid: The unique identifier of the action_plan
        :return: A tuple with the server response and the response body
        """

        return self._delete_request('/action_plans', action_plan_uuid)

    @base.handle_errors
    def delete_action_plans_by_audit(self, audit_uuid):
        """Deletes an action plan having the specified UUID

        :param audit_uuid: The unique identifier of the related Audit
        """

        action_plans = self.list_action_plans(audit_uuid=audit_uuid)[1]

        for action_plan in action_plans:
            self.delete_action_plan(action_plan['uuid'])

    @base.handle_errors
    def update_action_plan(self, action_plan_uuid, patch):
        """Update the specified action plan

        :param action_plan_uuid: The unique identifier of the action_plan
        :param patch: List of dicts representing json patches.
        :return: Tuple with the server response and the updated action_plan
        """

        return self._patch_request('/action_plans', action_plan_uuid, patch)

    @base.handle_errors
    def start_action_plan(self, action_plan_uuid):
        """Start the specified action plan

        :param action_plan_uuid: The unique identifier of the action_plan
        :return: Tuple with the server response and the updated action_plan
        """

        return self._patch_request(
            '/action_plans', action_plan_uuid,
            [{'path': '/state', 'op': 'replace', 'value': 'PENDING'}])

    # ### GOALS ### #

    @base.handle_errors
    def list_goals(self, **kwargs):
        """List all existing goals"""
        return self._list_request('/goals', **kwargs)

    @base.handle_errors
    def list_goals_detail(self, **kwargs):
        """Lists details of all existing goals"""
        return self._list_request('/goals/detail', **kwargs)

    @base.handle_errors
    def show_goal(self, goal):
        """Gets a specific goal

        :param goal: UUID or Name of the goal
        :return: Serialized goal as a dictionary
        """
        return self._show_request('/goals', goal)

    # ### ACTIONS ### #

    @base.handle_errors
    def list_actions(self, **kwargs):
        """List all existing actions"""
        return self._list_request('/actions', **kwargs)

    @base.handle_errors
    def list_actions_detail(self, **kwargs):
        """Lists details of all existing actions"""
        return self._list_request('/actions/detail', **kwargs)

    @base.handle_errors
    def show_action(self, action_uuid):
        """Gets a specific action

        :param action_uuid: Unique identifier of the action
        :return: Serialized action as a dictionary
        """
        return self._show_request('/actions', action_uuid)

    # ### STRATEGIES ### #

    @base.handle_errors
    def list_strategies(self, **kwargs):
        """List all existing strategies"""
        return self._list_request('/strategies', **kwargs)

    @base.handle_errors
    def list_strategies_detail(self, **kwargs):
        """Lists details of all existing strategies"""
        return self._list_request('/strategies/detail', **kwargs)

    @base.handle_errors
    def show_strategy(self, strategy):
        """Gets a specific strategy

        :param strategy_id: Name of the strategy
        :return: Serialized strategy as a dictionary
        """
        return self._show_request('/strategies', strategy)

    # ### SCORING ENGINE ### #

    @base.handle_errors
    def list_scoring_engines(self, **kwargs):
        """List all existing scoring_engines"""
        return self._list_request('/scoring_engines', **kwargs)

    @base.handle_errors
    def list_scoring_engines_detail(self, **kwargs):
        """Lists details of all existing scoring_engines"""
        return self._list_request('/scoring_engines/detail', **kwargs)

    @base.handle_errors
    def show_scoring_engine(self, scoring_engine):
        """Gets a specific scoring_engine

        :param scoring_engine: UUID or Name of the scoring_engine
        :return: Serialized scoring_engine as a dictionary
        """
        return self._show_request('/scoring_engines', scoring_engine)

    # ### SERVICES ### #

    @base.handle_errors
    def list_services(self, **kwargs):
        """List all existing services"""
        return self._list_request('/services', **kwargs)

    @base.handle_errors
    def list_services_detail(self, **kwargs):
        """Lists details of all existing services"""
        return self._list_request('/services/detail', **kwargs)

    @base.handle_errors
    def show_service(self, service):
        """Gets a specific service

        :param service: Name of the service
        :return: Serialized service as a dictionary
        """
        return self._show_request('/services', service)

    # ### DATA MODEL ### #

    @base.handle_errors
    def list_data_models(self, **kwargs):
        """List data models"""
        return self._list_request('/data_model', **kwargs)
