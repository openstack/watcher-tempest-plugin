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

import json

from oslo_log import log

from watcher_tempest_plugin.services import base

LOG = log.getLogger(__name__)


class PromtoolClient:
    """Promtool client to push/query metrics to/from Prometheus."""

    def __init__(self, url, promtool_path="promtool",
                 openstack_type="devstack",
                 proxy_host_address=None, proxy_host_user=None,
                 proxy_host_pkey=None, proxy_host_pkey_type='rsa',
                 podified_ns=None, podified_kubeconfig=None,
                 prometheus_ssl_cert=None,
                 prometheus_fqdn_label="fqdn"):

        # Podified Control Plane
        self.is_podified = ("podified" == openstack_type)
        LOG.debug(f"Configuring PromtoolClient for {openstack_type} "
                  " deployment.")

        if proxy_host_address and proxy_host_user:
            self.client = base.SshCmdClient(
                host=proxy_host_address,
                username=proxy_host_user,
                pkey=(proxy_host_pkey or None),
                pkey_type=proxy_host_pkey_type,
            )
        else:
            self.client = base.SubProcessCmdClient()

        if self.is_podified:
            self.podified_ns = podified_ns
            self.oc_cmd = ['oc']
            if podified_kubeconfig:
                self.oc_cmd.insert(0, f"KUBECONFIG={podified_kubeconfig}")
            if podified_ns:
                self.oc_cmd += ['-n', self.podified_ns]
            # podified control plane will run promtool inside
            # prometheus container
            self.prometheus_pod = self.get_prometheus_pod()
            cmd_prefix = self.oc_cmd + ["rsh", self.prometheus_pod]
            self.client.cmd_prefix = " ".join(cmd_prefix)

        self.prometheus_url = url
        self.prometheus_write_url = url + "/api/v1/write"
        # active targets
        self.prometheus_targets_url = url + "/api/v1/targets?state=active"
        self.prometheus_fqdn_label = prometheus_fqdn_label
        self.promtool_cmd = [promtool_path]
        if prometheus_ssl_cert:
            self.promtool_cmd.insert(0, f"SSL_CERT_DIR={prometheus_ssl_cert}")
        # Map hostnames and fqdn to prometheus instances
        self._prometheus_instances = {}

    @property
    def prometheus_instances(self):
        if not self._prometheus_instances:
            self._build_host_fqdn_maps()
        return self._prometheus_instances

    def _build_host_fqdn_maps(self):
        # NOTE(dviroel): Promtool does not support 'targets'
        # endpoint. curl is preferred here since this command
        # will run inside a container in podified deployments.
        cmd = ['curl', '-k', '-s', self.prometheus_targets_url]

        out = self.client.exec_cmd(cmd)

        targets = json.loads(out)['data']['activeTargets']

        # 1. builds based on fqdn
        self._prometheus_instances = {
            fqdn: instance for (fqdn, instance) in (
                (target['labels'].get(self.prometheus_fqdn_label),
                 target['labels'].get('instance'))
                for target in targets
                if target.get('labels', {}).get(self.prometheus_fqdn_label)
            )
        }
        # 2. update with hostname
        host_instance_map = {
            host: instance for (host, instance) in (
                (fqdn.split('.')[0], inst)
                for fqdn, inst in self._prometheus_instances.items()
                if '.' in fqdn
            )
        }
        self._prometheus_instances.update(host_instance_map)

    def show_instant_measure(self, expr):
        """Sends instance query to Prometheus server.

        :param expr: promql query expression to be sent
          to Prometheus.

        :raises: SSHExecCommandFailed if command fails.
        :raises: TimeoutException if command doesn't end when
          timeout expires.
        :returns: Query response.
        """
        cmd = self.promtool_cmd + [
            "query", "instant", self.prometheus_url, expr]

        return self.client.exec_cmd(cmd)

    def add_measures(self, input_data):
        """Add measures resources with the specified parameters.

        :param input_data: metric data  in exposition format,
          to be pushed to prometheus.

        :raises: Exception when push metrics call doesn't return
         success.
        :raises: SSHExecCommandFailed if command fails.
        :raises: TimeoutException if command doesn't end when
          timeout expires.
        :returns: Stdout output generated by the command.
        """
        cmd = self.promtool_cmd + [
            "push", "metrics", self.prometheus_write_url]

        out = self.client.exec_cmd(cmd, input_data=input_data)

        LOG.debug(f"Promtool add_measures output: {out}")

        if "SUCCESS" not in out:
            raise Exception(f"Promtool failed to push metrics: {out}")

    def get_pods(self, labels={}, pod_state='Running'):
        """Retrive pods based on matching labels and pod status.

        :param labels: (Optional) A comma separeted list of labels,
          used to filter pods available in the namespace.
        :param pod_state: (Optional) Status of the pods, used to
          filter pods available in the namespace.

        :raises: Exception if the environment is not a podified
          deployment.
        :returns: A list of pod names or an empty list.
        """
        if not self.is_podified:
            raise Exception("This method is only available in a "
                            "podified deployment.")

        # pod_state as empty string can be used to get all pod states
        if pod_state:
            pod_state = f"--field-selector=status.phase={pod_state}"
        if labels:
            labels = f"-l {labels}"
        oc_cmd = " ".join(self.oc_cmd)
        pods_list = f"{oc_cmd} get pods -o=name {pod_state} {labels}"
        cut_pod = "cut -d'/' -f 2"

        pods_output = self.client.exec_cmd(
            f"{pods_list} | {cut_pod}; true")

        # output can be empty with len == 1
        if len(pods_output) <= 1:
            return []

        return [pod.strip() for pod in pods_output.splitlines()]

    def get_prometheus_pod(self):
        """Returns the name of a prometheus pod.

        :raises: Exception if no prometheus pod is found.
        :returns: Name of a prometheus pod.
        """
        labels = "app.kubernetes.io/name=prometheus"
        LOG.debug("Getting prometheus service pod names.")
        pods = self.get_pods(labels)

        if not pods:
            raise Exception("Could not find a prometheus service pod.")

        LOG.debug(f"Prometheus service found. Running on pod {pods[0]}")
        return pods[0]
