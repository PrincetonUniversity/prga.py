__doc__ = """
Classes for modules and instances.

Notes:
    1. Parameterization is tricky and must be used with care:
        * First of all, parameterizations share the same key as the prototype. Indexing into the database with this
          key always returns the prototype, so an extra parameterization look-up is needed if a specific
          parameterization is wanted.
        * Secondly, it's OK to add new ports/instances to the prototype after parameterizations are created. However,
          removing ports/instances is harder to deal with and therefore not supported.
        * Thirdly, when parameterizations are created, custom attributes on the ports/instances are NOT carried over
          to their counterparts.
"""
