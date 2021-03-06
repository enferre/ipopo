.. _api:

API
===

This part of the documentation covers all the core classes and
services of iPOPO.

.. _api_bundlecontext:

BundleContext Object
-------------------- 

The bundle context is the link between a bundle and the framework.
It's by the context that you can register services, install other
bundles.

.. autoclass:: pelix.framework.BundleContext
   :members:
   :inherited-members:


Framework Object
----------------

The Framework object is a singleton and can be accessed using
:meth:`get_bundle(0) <pelix.framework.BundleContext.get_bundle>`.
This class inherits the methods from :class:`pelix.framework.Bundle`.

.. autoclass:: pelix.framework.Framework
   :members:

Bundle Object
-------------

This object gives access to the description of an installed bundle.
It is useful to check the path of the source module, the version, etc.

.. autoclass:: pelix.framework.Bundle
   :members:
   :inherited-members:
