# Copyright 2025 Red Hat, Inc.  All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

import fixtures

from watcher_tempest_plugin.services.infra_optim.v1.json import client


class APIMicroversionFixture(fixtures.Fixture):
    """API Microversion Fixture to set service microversion.

    This class provides the fixture to set and reset the microversion
    on service client. Service client has global variable to set the
    microversion for that service API request.
    This class can be used with useFixture: Example::

        def setUp(self):
            super(BaseInfraOptimTest, self).setUp()
            self.useFixture(api_microversion_fixture.APIMicroversionFixture(
                optimize_microversion=self.request_microversion))
    This class only supports the Resource Optimization service.

    :param str optimize_microversion: microvesion to be set on resource
                                      optimization service client
    """

    def __init__(self, optimize_microversion):
        self.optimize_microversion = optimize_microversion

    def _setUp(self):
        super(APIMicroversionFixture, self)._setUp()
        client.INFRA_OPTIM_VERSION = self.optimize_microversion
        self.addCleanup(self._reset_optimize_microversion)

    def _reset_optimize_microversion(self):
        client.INFRA_OPTIM_VERSION = None
