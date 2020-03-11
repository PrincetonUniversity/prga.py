# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseBuilder
from ..common import ModuleClass, PrimitiveClass, ModuleView, NetClass
from ...netlist.module.instance import Instance
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...util import ReadonlyMappingProxy
from ...exception import PRGAInternalError

from collections import OrderedDict

__all__ = ["MultimodeBuilder"]


# ----------------------------------------------------------------------------
# -- Builder for One Mode in a Multi-mode Primitive --------------------------
# ----------------------------------------------------------------------------
class _ModeBuilder(BaseBuilder):
    """Mode builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    @classmethod
    def new(cls, parent, name, view, **kwargs):
        """Create a new mode for building."""
        if view.is_user:
            kwargs["allow_multisource"] = True
        # if view.is_logical:
        #     kwargs["ports"] = ReadonlyMappingProxy(parent.ports, lambda kv: kv[1].net_class.is_primitive)
        # else:
        #     kwargs["ports"] = ReadonlyMappingProxy(parent.ports)
        m = Module(parent.name + "." + name,
                ports = OrderedDict(), 
                instances = OrderedDict(),
                module_class = ModuleClass.mode,
                parent = parent,
                key = name,
                **kwargs)
        for key, port in iteritems(parent.ports):
            ModuleUtils.create_port(m, port.name, len(port), port.direction,
                    key = key, is_clock = port.is_clock)
        return m

    def instantiate(self, model, name, **kwargs):
        return ModuleUtils.instantiate(self._module, model, name, **kwargs)
        # instance = ModuleUtils.instantiate(self._module.parent, model, name,
        #         key = (self._module.key, name), **kwargs)
        # # ATTENTION: parent of the instance is not the mode
        # return self._module._instances.setdefault((self._module.key, name), instance)

    def connect(self, sources, sinks, *, fully = False, pack_patterns = tuple()):
        """Connect ``sources`` to ``sinks``."""
        if not pack_patterns:
            NetUtils.connect(sources, sinks, fully = fully)
        else:
            NetUtils.connect(sources, sinks, fully = fully, pack_patterns = pack_patterns)
        # if not pack_patterns:
        #     NetUtils.connect(sources, sinks, fully = fully, module = self._module)
        # else:
        #     NetUtils.connect(sources, sinks, fully = fully, module = self._module,
        #             pack_patterns = pack_patterns)

    def commit(self):
        return self._module

# ----------------------------------------------------------------------------
# -- Builder for Multi-mode Primitives ---------------------------------------
# ----------------------------------------------------------------------------
class MultimodeBuilder(BaseBuilder):
    """Multi-mode module builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built

    Keyword Args:
        view (`ModuleView`): The view of the module being built
    """

    __slots__ = ['_view']
    def __init__(self, context, module, *, view = ModuleView.user):
        super(MultimodeBuilder, self).__init__(context, module)
        self._view = view

    @property
    def view(self):
        return self._view

    @classmethod
    def new(cls, name, *, view = ModuleView.user, **kwargs):
        """Create a new multi-mode primitive for building."""
        if view.is_user:
            kwargs["primitive_class"] = PrimitiveClass.multimode
        elif view.is_logical:
            kwargs["allow_multisource"] = True
        return Module(name,
                ports = OrderedDict(),
                instances = OrderedDict(),
                module_class = ModuleClass.primitive,
                modes = OrderedDict(),
                **kwargs)

    def create_clock(self, name, **kwargs):
        """Create a clock in the multi-mode primitive.

        Args:
            name (:obj:`str`): Name of the clock

        Keyword Args:
            **kwargs: Additional attributes to be associated with the port
        """
        if self._view.is_logical:
            kwargs["net_class"] = NetClass.primitive
        return ModuleUtils.create_port(self._module, name, 1, PortDirection.input_,
                is_clock = True, **kwargs)

    def create_input(self, name, width, *, clock = None, **kwargs):
        """Create an input in the multi-mode primitive.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Width of the port

        Keyword Args:
            clock (:obj:`str`): Clock of the port
            **kwargs: Additional attributes to be associated with the port
        """
        if self._view.is_logical:
            kwargs["net_class"] = NetClass.primitive
        elif self._view.is_user and clock is not None:
            raise PRGAInternalError("Cannot assign clock to a multi-mode primitive ({}) port in user view"
                    .format(self._module))
        return ModuleUtils.create_port(self._module, name, width, PortDirection.input_,
                clock = clock, **kwargs)

    def create_output(self, name, width, *, clock = None, **kwargs):
        """Create an output in the multi-mode primitive.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Width of the port

        Keyword Args:
            clock (:obj:`str`): Clock of the port
            **kwargs: Additional attributes to be associated with the port
        """
        if self._view.is_logical:
            kwargs["net_class"] = NetClass.primitive
        elif self._view.is_user and clock is not None:
            raise PRGAInternalError("Cannot assign clock to a multi-mode primitive ({}) port in user view"
                    .format(self._module))
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output,
                clock = clock, **kwargs)

    def create_cfg_port(self, name, width, direction, *,
            is_clock = False, clock = None, **kwargs):
        """Create a configuration port."""
        if self._view.is_user:
            raise PRGAInternalError("Cannot create configuration port in user view")
        kwargs["net_class"] = NetClass.cfg
        return ModuleUtils.create_port(self._module, name, width, direction,
                is_clock = is_clock, clock = clock, **kwargs)

    def connect(self, sources, sinks, *, fully = False):
        """Create combinational connections between ports in the primitive."""
        NetUtils.connect(sources, sinks, fully = fully)

    def create_mode(self, name, **kwargs):
        """Create a new mode for this multi-mode primitive."""
        if name in self._module.modes:
            raise PRGAInternalError("Conflicting mode name: {}".format(name))
        mode = self._module.modes[name] = _ModeBuilder.new(self._module, name, self._view, **kwargs)
        return _ModeBuilder(self._context, mode)
