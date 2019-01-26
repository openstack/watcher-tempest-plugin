# -*- encoding: utf-8 -*-
# Copyright (c) 2018 Servionica
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
from watcher_tempest_plugin.services import base


class GnocchiClientJSON(base.BaseClient):
    """Base Tempest REST client for Gnocchi API v1."""

    URI_PREFIX = 'v1'
    json_header = {'Content-Type': "application/json"}

    def serialize(self, object_dict):
        """Serialize a Gnocchi object."""
        return jsonutils.dumps(object_dict)

    def deserialize(self, object_str):
        """Deserialize a Gnocchi object."""
        if not object_str:
            return object_str
        return jsonutils.loads(object_str.decode('utf-8'))

    @base.handle_errors
    def create_resource(self, **kwargs):
        """Create a resource with the specified parameters

        :param kwargs: Resource body
        :return: A tuple with the server response and the created resource
        """
        resource_type = kwargs.pop('type', 'generic')
        return self._create_request('/resource/{type}'.format(
            type=resource_type), kwargs)

    @base.handle_errors
    def search_resource(self, **kwargs):
        """Search for resources with the specified parameters

        :param kwargs: Filter body
        :return: A tuple with the server response and the found resource
        """
        return self._create_request(
            '/search/resource/generic', kwargs, headers=self.json_header)

    @base.handle_errors
    def show_measures(self, metric_uuid, aggregation='mean'):
        return self._list_request(
            '/metric/{metric_uuid}/measures?aggregation={aggregation}&'
            'refresh=true'.format(metric_uuid=metric_uuid,
                                  aggregation=aggregation))

    @base.handle_errors
    def add_measures(self, metric_uuid, body):
        """Add measures for existed resource with the specified parameters

        :param metric_uuid: metric that stores measures
        :param body: list of measures to publish
        :return: A tuple with the server response and empty response body
        """
        return self._create_request(
            '/metric/{metric_uuid}/measures'.format(metric_uuid=metric_uuid),
            body,
            headers=self.json_header)

    @base.handle_errors
    def create_metric(self, **body):
        return self._create_request('/metric', body)

    @base.handle_errors
    def delete_metric(self, metric_uuid):
        return self._delete_request(
            '/metric', metric_uuid,
            headers=self.json_header)
