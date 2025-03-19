# -*- encoding: utf-8 -*-
# Copyright (c) 2025 Red Hat
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
from debtcollector import removals
import warnings

warnings.simplefilter("once", DeprecationWarning)
removals.removed_module(
    __name__,
    replacement="watcherclient.tests.client_functional",
    removal_version="2026.1",
    message=(
        "The 'watcher_tempest_plugin.tests.client_functional' module is "
        "deprecated and will be removed in version 2026.1. "
        "We recommend using watcherclient.tests.client_functional for "
        "running functional tests. "
    )
)
