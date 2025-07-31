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
        "openstack_type",
        default="devstack",
        choices=["devstack", "podified"],
        help="Type of OpenStack deployment.",
    ),
    # Proxy host configuration
    cfg.StrOpt(
        "proxy_host_address",
        default="",
        help="A proxy host to run extra commands for some datasources.",
    ),
    cfg.StrOpt(
        "proxy_host_user",
        default="",
        help="User of the proxy host to run extra commands for "
             "some datasources.",
    ),
    cfg.StrOpt(
        "proxy_host_pkey",
        default="",
        help="Path to a private key to access the proxy host.",
    ),
    cfg.StrOpt(
        "proxy_host_pkey_type",
        default="rsa",
        help="Private key type to be used to access the proxy host.",
    ),
    # Prometheus datasource configuration
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
    cfg.BoolOpt(
        "prometheus_ssl_enabled",
        default=False,
        help="Whether or not SSL is enabled in prometheus server.",
    ),
    cfg.StrOpt(
        "prometheus_ssl_cert_dir",
        default="",
        help="Path to directory that constains certificates needed to "
             "interact with the Prometheus server.",
    ),
    cfg.StrOpt(
        "prometheus_fqdn_label",
        default="fqdn",
        help="The label that Prometheus uses to store the fqdn of "
             "exporters.",
    ),
    # Podified control plane configuration
    cfg.StrOpt(
        "podified_kubeconfig_path",
        default="",
        help="Path to a kubeconfig file, to run 'oc' commands in a "
             "podified control plane environment."
    ),
    cfg.StrOpt(
        "podified_namespace",
        default="openstack",
        help="Namespace where OpenStack is deployed in a podified "
             "control plane environment."
    ),
    cfg.IntOpt(
        "real_workload_period",
        default=120,
        help="In real-data test cases, the period of time during which "
             "the load will be executed in seconds."
    ),
    cfg.StrOpt(
        "min_microversion",
        default=None,
        help="Lower version of the test target microversion range. "
             "The format is 'X.Y', where 'X' and 'Y' are int values."
    ),
    cfg.StrOpt(
        "max_microversion",
        default=None,
        help="Upper version of the test target microversion range. "
             "The format is 'X.Y', where 'X' and 'Y' are int values."
    ),
]
