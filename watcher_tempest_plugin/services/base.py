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

import abc
import functools
import subprocess

import urllib.parse as urlparse

from tempest.lib.common import rest_client


def handle_errors(f):
    """A decorator that allows to ignore certain types of errors."""

    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        param_name = 'ignore_errors'
        ignored_errors = kwargs.get(param_name, tuple())

        if param_name in kwargs:
            del kwargs[param_name]

        try:
            return f(*args, **kwargs)
        except ignored_errors:
            # Silently ignore errors
            pass

    return wrapper


class BaseClient(rest_client.RestClient, metaclass=abc.ABCMeta):
    """Base Tempest REST client for API."""

    URI_PREFIX = ''

    @abc.abstractmethod
    def serialize(self, object_dict):
        """Serialize an object."""
        raise NotImplementedError()

    @abc.abstractmethod
    def deserialize(self, object_str):
        """Deserialize an object."""
        raise NotImplementedError()

    def _get_uri(self, resource_name, uuid=None, permanent=False):
        """Get URI for a specific resource or object.

        :param resource_name: The name of the REST resource, e.g., 'audits'.
        :param uuid: The unique identifier of an object in UUID format.
        :return: Relative URI for the resource or object.
        """

        prefix = self.URI_PREFIX if not permanent else ''

        return '{pref}/{res}{uuid}'.format(pref=prefix,
                                           res=resource_name,
                                           uuid='/%s' % uuid if uuid else '')

    def _make_patch(self, allowed_attributes, **kw):
        """Create a JSON patch according to RFC 6902.

        :param allowed_attributes: An iterable object that contains a set of
            allowed attributes for an object.
        :param **kw: Attributes and new values for them.
        :return: A JSON path that sets values of the specified attributes to
            the new ones.
        """

        def get_change(kw, path='/'):
            for name, value in kw.items():
                if isinstance(value, dict):
                    for ch in get_change(value, path + '%s/' % name):
                        yield ch
                else:
                    if value is None:
                        yield {'path': path + name,
                               'op': 'remove'}
                    else:
                        yield {'path': path + name,
                               'value': value,
                               'op': 'replace'}

        patch = [ch for ch in get_change(kw)
                 if ch['path'].lstrip('/') in allowed_attributes]

        return patch

    def _list_request(self, resource, permanent=False, **kwargs):
        """Get the list of objects of the specified type.

        :param resource: The name of the REST resource, e.g., 'audits'.
        "param **kw: Parameters for the request.
        :return: A tuple with the server response and deserialized JSON list
                 of objects
        """

        uri = self._get_uri(resource, permanent=permanent)
        if kwargs:
            uri += "?%s" % urlparse.urlencode(kwargs)

        resp, body = self.get(uri)
        self.expected_success(200, int(resp['status']))

        return resp, self.deserialize(body)

    def _show_request(self, resource, uuid, permanent=False, **kwargs):
        """Gets a specific object of the specified type.

        :param uuid: Unique identifier of the object in UUID format.
        :return: Serialized object as a dictionary.
        """

        if 'uri' in kwargs:
            uri = kwargs['uri']
        else:
            uri = self._get_uri(resource, uuid=uuid, permanent=permanent)
        resp, body = self.get(uri)
        self.expected_success(200, int(resp['status']))

        return resp, self.deserialize(body)

    def _create_request(self, resource, object_dict, headers=None):
        """Create an object of the specified type.

        :param resource: The name of the REST resource, e.g., 'audits'.
        :param object_dict: A Python dict that represents an object of the
                            specified type.
        :return: A tuple with the server response and the deserialized created
                 object.
        """

        body = self.serialize(object_dict)
        uri = self._get_uri(resource)

        resp, body = self.post(uri, body=body, headers=headers)
        self.expected_success([200, 201, 202], int(resp['status']))

        return resp, self.deserialize(body)

    def _delete_request(self, resource, uuid, headers=None):
        """Delete specified object.

        :param resource: The name of the REST resource, e.g., 'audits'.
        :param uuid: The unique identifier of an object in UUID format.
        :return: A tuple with the server response and the response body.
        """

        uri = self._get_uri(resource, uuid)

        resp, body = self.delete(uri, headers=headers)
        self.expected_success(204, int(resp['status']))
        return resp, body

    def _patch_request(self, resource, uuid, patch_object):
        """Update specified object with JSON-patch.

        :param resource: The name of the REST resource, e.g., 'audits'.
        :param uuid: The unique identifier of an object in UUID format.
        :return: A tuple with the server response and the serialized patched
                 object.
        """

        uri = self._get_uri(resource, uuid)
        patch_body = self.serialize(patch_object)

        resp, body = self.patch(uri, body=patch_body)
        self.expected_success(200, int(resp['status']))
        return resp, self.deserialize(body)

    @handle_errors
    def get_api_description(self):
        """Retrieves all versions of the API."""

        return self._list_request('', permanent=True)

    @handle_errors
    def get_version_description(self, version='v1'):
        """Retrieves the description of the API.

        :param version: The version of the API. Default: 'v1'.
        :return: Serialized description of API resources.
        """

        return self._list_request(version, permanent=True)

    def _put_request(self, resource, put_object):
        """Update specified object with JSON-patch."""

        uri = self._get_uri(resource)
        put_body = self.serialize(put_object)

        resp, body = self.put(uri, body=put_body)
        self.expected_success(202, int(resp['status']))
        return resp, body


class SubProcessCmdClient:
    """Command execution client based on subprocess"""

    def exec_command(self, cmd, input_data=None, timeout=None):
        """Execute a command with an optional input data.

        :param input_data: data to be sent to process stdin
        :param timeout: communication timeout in seconds
        """
        sp = subprocess.Popen(cmd,
                              stdout=subprocess.PIPE,
                              stdin=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True)
        return sp.communicate(input=input_data, timeout=timeout)
