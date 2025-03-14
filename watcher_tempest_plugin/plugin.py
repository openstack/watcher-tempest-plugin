# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
# License for the specific language governing permissions and limitations
# under the License.


import os

from tempest.test_discover import plugins

from watcher_tempest_plugin import config as watcher_config


class WatcherTempestPlugin(plugins.TempestPlugin):
    def load_tests(self):
        base_path = os.path.split(os.path.dirname(
            os.path.abspath(__file__)))[0]
        test_dir = "watcher_tempest_plugin/tests"
        full_test_dir = os.path.join(base_path, test_dir)
        return full_test_dir, base_path

    def register_opts(self, conf):
        conf.register_opt(watcher_config.service_option,
                          group='service_available')

        conf.register_group(watcher_config.optimization_group)
        conf.register_opts(watcher_config.OptimizationGroup,
                           watcher_config.optimization_group)

    def get_opt_lists(self):
        return [('service_available', [watcher_config.service_option]),
                (watcher_config.optimization_group.name,
                watcher_config.OptimizationGroup)
                ]
