#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Pelix remote services: JSON-RPC implementation

Based on a modified version of the 3rd-party package jsonrpclib.
A patched version of jsonrpclib will be released soon.

:author: Thomas Calmant
:copyright: Copyright 2013, isandlaTech
:license: Apache License 2.0
:version: 0.1.2
:status: Beta

..

    Copyright 2013 isandlaTech

    Licensed under the Apache License, Version 2.0 (the "License");
    you may not use this file except in compliance with the License.
    You may obtain a copy of the License at

        http://www.apache.org/licenses/LICENSE-2.0

    Unless required by applicable law or agreed to in writing, software
    distributed under the License is distributed on an "AS IS" BASIS,
    WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
    See the License for the specific language governing permissions and
    limitations under the License.

**TODO:**
* "system" methods (list, help, ...)
"""

# Module version
__version_info__ = (0, 1, 2)
__version__ = ".".join(str(x) for x in __version_info__)

# Documentation strings format
__docformat__ = "restructuredtext en"

# ------------------------------------------------------------------------------

# iPOPO decorators
from pelix.ipopo.decorators import ComponentFactory, Requires, Validate, \
    Invalidate, Property, Provides

# Pelix constants
import pelix.http
import pelix.remote.beans
from pelix.utilities import to_str

# Standard library
import logging
import uuid

# JSON-RPC module
import jsonrpclib
from jsonrpclib.SimpleJSONRPCServer import SimpleJSONRPCDispatcher

# ------------------------------------------------------------------------------

JSONRPC_CONFIGURATION = 'jsonrpc'
""" Remote Service configuration constant """

PROP_JSONRPC_URL = '{0}.url'.format(JSONRPC_CONFIGURATION)
""" JSON-RPC servlet URL """

_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------

class _JsonRpcServlet(SimpleJSONRPCDispatcher):
    """
    A JSON-RPC servlet that can be registered in the Pelix HTTP service

    Calls the dispatch method given in the constructor
    """
    def __init__(self, dispatch_method, encoding=None):
        """
        Sets up the servlet
        """
        SimpleJSONRPCDispatcher.__init__(self, encoding=encoding)

        # Register the system.* functions
        self.register_introspection_functions()

        # Make a link to the dispatch method
        self._dispatch_method = dispatch_method


    def _simple_dispatch(self, name, params):
        """
        Dispatch method
        """
        try:
            # Internal method
            return self.funcs[name](*params)

        except KeyError:
            # Other method
            return self._dispatch_method(name, params)


    def do_POST(self, request, response):
        """
        Handles a HTTP POST request

        :param request: The HTTP request bean
        :param request: The HTTP response handler
        """
        try:
            # Get the request content
            data = to_str(request.read_data())

            # Dispatch
            result = self._marshaled_dispatch(data, self._simple_dispatch)

            # Send the result
            response.send_content(200, result, 'application/json-rpc')

        except Exception as ex:
            response.send_content(500, "Internal error:\n{0}\n".format(ex),
                                  'text/plain')

# ------------------------------------------------------------------------------

@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JSONRPC_EXPORTER)
@Requires('_dispatcher', pelix.remote.SERVICE_DISPATCHER)
@Requires('_http', pelix.http.HTTP_SERVICE)
@Property('_path', pelix.http.HTTP_SERVLET_PATH, '/JSON-RPC')
@Property('_kinds', pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
          (JSONRPC_CONFIGURATION,))
class JsonRpcServiceExporter(object):
    """
    JSON-RPC Remote Services exporter
    """
    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Dispatcher
        self._dispatcher = None
        self._kinds = None

        # HTTP Service
        self._http = None
        self._path = None

        # JSON-RPC servlet
        self._servlet = None

        # Exported services: Name -> ExportEndpoint
        self.__endpoints = {}

        # Service Reference -> ExportEndpoint
        self.__registrations = {}


    def _dispatch(self, method, params):
        """
        Called by the servlet: calls the method of an exported service
        """
        # Get the best matching name
        matching = None
        len_found = 0
        for name in self.__endpoints:
            if len(name) > len_found and method.startswith(name + "."):
                # Better matching end point name (longer that previous one)
                matching = name
                len_found = len(matching)

        if matching is None:
            # No end point name match
            raise KeyError("No end point found for: {0}".format(method))

        # Extract the method name. (+1 for the trailing dot)
        method_name = method[len_found + 1:]

        # Call the dispatcher
        return self._dispatcher.dispatch(self._kinds, matching,
                                         method_name, params)


    def _compute_endpoint_name(self, reference):
        """
        Computes the end point name according to service properties

        :param reference: A ServiceReference object
        :return: The computed end point name
        """
        service_id = reference.get_property(pelix.framework.SERVICE_ID)
        endpoint_name = reference.get_property(pelix.remote.PROP_ENDPOINT_ID)

        # FIXME: Pelix compatibility
        if not endpoint_name:
            endpoint_name = reference.get_property(
                                                pelix.remote.PROP_ENDPOINT_NAME)

        if not endpoint_name:
            endpoint_name = 'service_{0}'.format(service_id)

        return endpoint_name


    def _export_service(self, reference):
        """
        Exports the given service

        :param reference: A ServiceReference object
        :return: True if the service has been exported, else False
        """
        # Compute the end point name
        endpoint_name = self._compute_endpoint_name(reference)
        if endpoint_name in self.__endpoints:
            # Already known end point
            _logger.error("Already known end point %s for JSON-RPC",
                          endpoint_name)
            return False

        # Get the service
        try:
            service = self._context.get_service(reference)
            if service is None:
                _logger.error("Invalid service for reference %s",
                              str(reference))

        except pelix.framework.BundleException as ex:
            _logger.error("Error retrieving the service to export: %s", ex)
            return False

        try:
            # Prepare properties
            properties = {PROP_JSONRPC_URL: self.get_access()}

            # Create the registration information
            endpoint = pelix.remote.beans.ExportEndpoint(str(uuid.uuid4()),
                                                         self._kinds,
                                                         endpoint_name,
                                                         reference, service,
                                                         properties)

        except ValueError:
            # Invalid end point
            return False

        try:
            # Register the end point
            self._dispatcher.add_endpoint(self._kinds, endpoint_name, endpoint)

        except KeyError as ex:
            _logger.error("Error registering end point: %s", ex)

        else:
            # Store informations
            self.__endpoints[endpoint_name] = endpoint
            self.__registrations[reference] = endpoint
            return True

        return False


    def _update_service(self, reference, old_properties):
        """
        Service properties updated
        """
        # Compute the new end point name
        new_name = self._compute_endpoint_name(reference)

        # Get the end point
        endpoint = self.__registrations[reference]
        if endpoint.name != new_name:
            # Name changed -> re-export the service
            self._unexport_service(reference)
            self._export_service(reference)

        else:
            # Notify the dispatcher
            self._dispatcher.update_endpoint(self._kinds, endpoint.name,
                                             endpoint, old_properties)


    def _unexport_service(self, reference):
        """
        Stops the export of the given service

        :param reference: A ServiceReference object
        """
        # Find the corresponding end point
        endpoint = self.__registrations.get(reference)
        if endpoint is not None:
            # Delete the registration
            del self.__registrations[reference]
            del self.__endpoints[endpoint.name]

            # Unregister the service from the dispatcher
            self._dispatcher.remove_endpoint(self._kinds, endpoint.name)


    def service_changed(self, event):
        """
        Called when a service event is triggered
        """
        kind = event.get_kind()
        svcref = event.get_service_reference()

        if kind == pelix.framework.ServiceEvent.REGISTERED:
            # Simply export the service
            self._export_service(svcref)

        elif kind == pelix.framework.ServiceEvent.MODIFIED:
            # Matching registering or updated service
            if svcref not in self.__registrations:
                # New match
                self._export_service(svcref)

            else:
                # Properties modification:
                # Re-export if endpoint.name has changed
                self._update_service(svcref, event.get_previous_properties())

        elif svcref in self.__registrations and \
                (kind == pelix.framework.ServiceEvent.UNREGISTERING or \
                 kind == pelix.framework.ServiceEvent.MODIFIED_ENDMATCH):
            # Service is updated or unregistering
            self._unexport_service(svcref)


    def get_access(self):
        """
        Retrieves the URL to access this component
        """
        port = self._http.get_access()[1]
        return "http://{{server}}:{0}{1}".format(port, self._path)


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        # Store the context
        self._context = context

        # Prepare the service filter
        ldapfilter = '(|(|({0}={2})({0}=\*))(&(!({0}=*))({1}=*)))' \
                    .format(pelix.remote.PROP_EXPORTED_CONFIGS,
                            pelix.remote.PROP_EXPORTED_INTERFACES,
                            JSONRPC_CONFIGURATION)

        # Export existing services
        existing_ref = self._context.get_all_service_references(None,
                                                                ldapfilter)
        if existing_ref is not None:
            for reference in existing_ref:
                self._export_service(reference)

        # Register a service listener, to update the exported services state
        self._context.add_service_listener(self, ldapfilter)

        # Create/register the servlet
        self._servlet = _JsonRpcServlet(self._dispatch)
        self._http.register_servlet(self._path, self._servlet)


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        # Unregister the service listener
        context.remove_service_listener(self)

        # Unregister the servlet
        self._http.unregister(None, self._servlet)

        # Remove all exports
        for reference in list(self.__registrations.keys()):
            self._unexport_service(reference)

        # Clean up the storage
        self.__endpoints.clear()
        self.__registrations.clear()

        # Clean up members
        self._servlet = None
        self._context = None

# ------------------------------------------------------------------------------

class _ServiceCallProxy(object):
    """
    Service call proxy
    """
    def __init__(self, name, url):
        """
        Sets up the call proxy

        :param name: End point name
        :param url: End point URL
        """
        self.__name = name
        self.__url = url


    def __getattr__(self, name):
        """
        Prefixes the requested attribute name by the endpoint name
        """
        # Make a proxy for this call
        # This is an ugly trick to handle multi-threaded calls, as the
        # underlying proxy re-uses the same connection when possible: sometimes
        # it means sending a request before retrieving a result
        proxy = jsonrpclib.jsonrpc.ServerProxy(self.__url)
        return getattr(proxy, "{0}.{1}".format(self.__name, name))


@ComponentFactory(pelix.remote.FACTORY_TRANSPORT_JSONRPC_IMPORTER)
@Provides(pelix.remote.SERVICE_ENDPOINT_LISTENER)
@Property('_kinds', pelix.remote.PROP_REMOTE_CONFIGS_SUPPORTED,
          (JSONRPC_CONFIGURATION,))
@Property('_listener_flag', pelix.remote.PROP_LISTEN_IMPORTED, True)
class JsonRpcServiceImporter(object):
    """
    JSON-RPC Remote Services importer
    """
    def __init__(self):
        """
        Sets up the exporter
        """
        # Bundle context
        self._context = None

        # Component properties
        self._kinds = None
        self._listener_flag = True

        # Registered services (end point -> reference)
        self.__registrations = {}


    def endpoint_added(self, endpoint):
        """
        An end point has been imported
        """
        configs = set(endpoint.configurations)
        if '*' not in configs and not configs.intersection(self._kinds):
            # Not for us
            return

        # Get the access URL
        access_url = endpoint.properties.get(PROP_JSONRPC_URL)
        if not access_url:
            # No URL information
            _logger.warning("No access URL given: %s", endpoint)
            return

        if endpoint.server is not None:
            # Server information given
            access_url = access_url.format(server=endpoint.server)

        # Register the service
        svc = _ServiceCallProxy(endpoint.name, access_url)
        svc_reg = self._context.register_service(endpoint.specifications, svc,
                                                 endpoint.properties)

        # Store references
        self.__registrations[endpoint.uid] = svc_reg


    def endpoint_updated(self, endpoint, old_properties):
        """
        An end point has been updated
        """
        if endpoint.uid not in self.__registrations:
            # Unknown end point
            return

        # Update service properties
        svc_reg = self.__registrations[endpoint.uid]
        svc_reg.set_properties(endpoint.properties)


    def endpoint_removed(self, endpoint):
        """
        An end point has been removed
        """
        if endpoint.uid not in self.__registrations:
            # Unknown end point
            return

        # Pop references
        svc_reg = self.__registrations.pop(endpoint.uid)

        # Unregister the service
        svc_reg.unregister()


    @Validate
    def validate(self, context):
        """
        Component validated
        """
        self._context = context


    @Invalidate
    def invalidate(self, context):
        """
        Component invalidated
        """
        self._context = None
