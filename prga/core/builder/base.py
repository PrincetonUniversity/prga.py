# -*- encoding: ascii -*-

from ...netlist import ModuleUtils, NetUtils
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

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Instance` ]: Proxy to ``module.instances``."""
        return self._module.instances

    def instantiate(self, model, name, **kwargs):
        """Add an instance to the module.
        
        Args:
            model (`Module`): Module to be instantiated
            name (:obj:`str`): Name of the instance

        Keyword Args:
            **kwargs: Custom attibutes assigned to the instance

        Returns:
            `Instance`:
        """
        return ModuleUtils.instantiate(self._module, model, name, **kwargs)

    def connect(self, sources, sinks, *, fully = False, **kwargs):
        """Connect ``sources`` to ``sinks``.
        
        Args:
            sources: Source nets, i.e., an input port, an output pin of an instance, a subset of the above, or a list
                of a combination of the above
            sinks: Sink nets, i.e., an output port, an input pin of an instance, a subset of the above, or a list
                of a combination of the above

        Keyword Args:
            fully (:obj:`bool`): If set to ``True``, connections are made between every source and every sink
            **kwargs: Additional attibutes assigned to all connections
        """
        NetUtils.connect(sources, sinks, fully = fully, **kwargs)

    def commit(self):
        """Commit and return the module.
        
        Returns:
            `Module`:
        """
        return self._module
