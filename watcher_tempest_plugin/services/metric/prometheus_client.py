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

from watcher_tempest_plugin.services import base


class PromtoolClient:
    """Promtool client to push/query metrics to/from Prometheus."""

    def __init__(self, url, promtool_path="promtool"):
        # NOTE: only subprocess client is support for now.
        #  A ssh client can be added to execute promtool in
        #  a proxy host
        self.client = base.SubProcessCmdClient()
        self.prometheus_url = url
        self.prometheus_write_url = url + "/api/v1/write"
        self.promtool_path = promtool_path

    def show_instant_measure(self, expr):
        """Sends instance query to Prometheus server.

        :param expr: promql query expression to be sent
          to Prometheus.
        """

        cmd = [self.promtool_path,
               "query", "instant",
               self.prometheus_url, expr]

        out, err = self.client.exec_command(cmd)

        if len(err) > 1:
            raise Exception(err)
        return out

    def add_measures(self, input_data):
        """Add measures resources with the specified parameters.

        :param input_data: metric data  in exposition format,
          to be pushed to prometheus.
        """
        cmd = [self.promtool_path,
               "push", "metrics",
               self.prometheus_write_url]

        out, err = self.client.exec_command(cmd, input_data=input_data)

        if "SUCCESS" not in out or len(err) > 1:
            raise Exception(err)
