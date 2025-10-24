
# Copyright 2025 Red Hat, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.

from tempest.lib.common import api_version_request


def is_microversion_le(left, right):
    """Check if the left microversion is less or equal then the right one."""

    left_microversion = api_version_request.APIVersionRequest(left)
    right_microversion = api_version_request.APIVersionRequest(right)

    return left_microversion <= right_microversion
