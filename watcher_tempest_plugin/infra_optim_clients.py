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

import abc

from oslo_serialization import jsonutils as json
from tempest import clients
from tempest.common import credentials_factory as creds_factory
from tempest import config
from tempest.lib.common import rest_client
from tempest.lib.services.placement import placement_client

from watcher_tempest_plugin.services.infra_optim.v1.json import client as ioc
from watcher_tempest_plugin.services.metric.v1.json import client as gc

CONF = config.CONF


class BaseManager(clients.Manager, metaclass=abc.ABCMeta):

    def __init__(self, credentials):
        super(BaseManager, self).__init__(credentials)
        self.io_client = ioc.InfraOptimClientJSON(
            self.auth_provider, 'infra-optim', CONF.identity.region)
        self.gn_client = gc.GnocchiClientJSON(
            self.auth_provider, 'metric', CONF.identity.region)
        self.placement_client = ExtendPlacementClient(
            self.auth_provider, 'placement', CONF.identity.region)


class AdminManager(BaseManager):
    def __init__(self):
        super(AdminManager, self).__init__(
            creds_factory.get_configured_admin_credentials(),
        )


class ExtendPlacementClient(placement_client.PlacementClient):

    def list_provider_traits(self, rp_uuid):
        """List resource provider traits.

        For full list of available parameters, please refer to the official
        API reference:
        https://docs.openstack.org/api-ref/placement/#
        list-resource-provider-traits-detail
        """
        url = '/resource_providers/%s/traits' % rp_uuid
        resp, body = self.get(url)
        self.expected_success(200, resp.status)
        body = json.loads(body)
        return rest_client.ResponseBody(resp, body)
