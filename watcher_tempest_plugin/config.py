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

from oslo_config import cfg


service_option = cfg.BoolOpt("watcher",
                             default=True,
                             help="Whether or not watcher is expected to be "
                                  "available")

optimization_group = cfg.OptGroup(name="optimize",
                                  title="Watcher Service Options")

OptimizationGroup = [
    cfg.StrOpt(
        "datasource",
        default="gnocchi",
        choices=["gnocchi", "prometheus", ""],
        help="Name of the data source used with the Watcher Service. "
             "Tempest will retrieve and add metrics from/to this data "
             "source when running Strategy tests. When running "
             "tests that do not require instance or host metrics, "
             "you can define this option to an empty string."),
    cfg.StrOpt(
        "prometheus_host",
        default="127.0.0.1",
        help="The hostname or IP address for the prometheus server.",
    ),
    cfg.StrOpt(
        "prometheus_port",
        default="9090",
        help="The port number used by the prometheus server.",
    ),
    cfg.StrOpt(
        "prometheus_promtool",
        default="promtool",
        help="The promtool binary path in the host.",
    ),
]
