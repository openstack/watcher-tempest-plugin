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
    cfg.StrOpt("datasource",
               default="gnocchi",
               choices=["gnocchi", ""],
               help="Name of the data source used with the Watcher Service"
                    "gnocchi is a supported datasources. use ''"
                    "for no datasource"),
]
