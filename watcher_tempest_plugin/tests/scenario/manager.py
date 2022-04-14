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

from tempest import config
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
