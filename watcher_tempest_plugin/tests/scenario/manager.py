# Copyright 2012 OpenStack Foundation
# Copyright 2013 IBM Corp.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from tempest.common import waiters
from tempest import config
from tempest.lib.common.utils import data_utils
from tempest.lib.common.utils import test_utils
import tempest.scenario.manager

CONF = config.CONF


class ScenarioTest(tempest.scenario.manager.ScenarioTest):
    """Base class for scenario tests. Uses tempest own clients. """

    credentials = ['primary', 'admin']

    @classmethod
    def skip_checks(cls):
        super(ScenarioTest, cls).skip_checks()
        if not CONF.service_available.watcher:
            raise cls.skipException('Watcher support is required')

    @classmethod
    def setup_clients(cls):
        super(ScenarioTest, cls).setup_clients()
        # Clients (in alphabetical order)
        cls.flavors_client = cls.os_primary.flavors_client
        cls.compute_floating_ips_client = (
            cls.os_primary.compute_floating_ips_client)
        cls.image_client = cls.os_primary.image_client_v2
        # Compute image client
        cls.compute_images_client = cls.os_primary.compute_images_client
        cls.keypairs_client = cls.os_primary.keypairs_client
        # Nova security groups client
        cls.compute_security_groups_client = (
            cls.os_primary.compute_security_groups_client)
        cls.compute_security_group_rules_client = (
            cls.os_primary.compute_security_group_rules_client)
        cls.servers_client = cls.os_primary.servers_client
        cls.interface_client = cls.os_primary.interfaces_client
        # Neutron network client
        cls.networks_client = cls.os_primary.networks_client
        cls.ports_client = cls.os_primary.ports_client
        cls.routers_client = cls.os_primary.routers_client
        cls.subnets_client = cls.os_primary.subnets_client
        cls.floating_ips_client = cls.os_primary.floating_ips_client
        cls.security_groups_client = cls.os_primary.security_groups_client
        cls.security_group_rules_client = (
            cls.os_primary.security_group_rules_client)

        cls.volumes_client = cls.os_primary.volumes_client_latest
        cls.snapshots_client = cls.os_primary.snapshots_client_latest

    # ## Test functions library
    #
    # The create_[resource] functions only return body and discard the
    # resp part which is not used in scenario tests

    def create_volume(self, name=None, imageRef=None, size=1,
                      volume_type=None, clients=None):

        if clients is None:
            clients = self.os_primary

        if imageRef:
            image = self.image_client.show_image(imageRef)
            min_disk = image.get('min_disk')
            size = max(size, min_disk)

        if name is None:
            name = data_utils.rand_name(self.__class__.__name__ + "-volume")
        volumes_client = clients.volumes_client_latest
        params = {'name': name,
                  'imageRef': imageRef,
                  'volume_type': volume_type,
                  'size': size or CONF.volume.volume_size}
        volume = volumes_client.create_volume(**params)['volume']
        self.addCleanup(volumes_client.wait_for_resource_deletion,
                        volume['id'])
        self.addCleanup(test_utils.call_and_ignore_notfound_exc,
                        volumes_client.delete_volume, volume['id'])
        self.assertEqual(name, volume['name'])
        waiters.wait_for_volume_resource_status(volumes_client,
                                                volume['id'], 'available')
        volume = volumes_client.show_volume(volume['id'])['volume']
        return volume

    def create_volume_type(self, clients=None, name=None, backend_name=None):
        if clients is None:
            clients = self.os_admin
        if name is None:
            class_name = self.__class__.__name__
            name = data_utils.rand_name(class_name + '-volume-type')

        volumes_client = clients.volume_types_client_latest
        extra_specs = {}
        if backend_name:
            extra_specs = {"volume_backend_name": backend_name}

        volume_type = volumes_client.create_volume_type(
            name=name, extra_specs=extra_specs)['volume_type']
        self.addCleanup(volumes_client.delete_volume_type, volume_type['id'])
        return volume_type
