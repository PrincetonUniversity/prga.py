# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...netlist.module.util import ModuleUtils
from ...util import Object

__all__ = []

# ----------------------------------------------------------------------------
# -- Base Builder for All Modules --------------------------------------------
# ----------------------------------------------------------------------------
class BaseBuilder(Object):
    """Base class for all module builders.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    __slots__ = ['_context', '_module']
    def __init__(self, context, module):
        self._context = context
        self._module = module

    @property
    def module(self):
        """`Module`: The module being built."""
        return self._module

    @property
    def ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Port` ]: Proxy to ``module.ports``."""
        return self._module.ports

    def commit(self):
        """Commit and return the module.
        
        Returns:
            `Module`:
        """
        return self._module
