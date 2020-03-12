# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseBuilder
from ..common import ModuleClass, PrimitiveClass, NetClass, ModuleView
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...exception import PRGAInternalError

from abc import abstractproperty
from collections import OrderedDict

__all__ = ["LogicalPrimitiveBuilder", "PrimitiveBuilder"]

# ----------------------------------------------------------------------------
# -- Base Builder for Primitives ---------------------------------------------
# ----------------------------------------------------------------------------
class _BasePrimitiveBuilder(BaseBuilder):
    """Base class for user-/logical- [multi-mode] primitive builder."""

    @abstractproperty
    def view(self):
        """`ModuleView`: View of the primitive being built."""
        raise NotImplementedError

    @abstractproperty
    def counterpart(self):
        """`AbstractModule`: The user counterpart of the primitive being built if we're building logical view."""
        raise NotImplementedError

    def create_clock(self, name, **kwargs):
        """Create a clock in the primitive.

        Args:
            name (:obj:`str`): Name of the clock

        Keyword Args:
            **kwargs: Additional attributes to be associated with the port
        """
        if self.view.is_logical:
            if self.counterpart is not None:
                raise PRGAInternalError(("Cannot create user-available ports in logical module {} "
                        "with a specified user counterpart").format(self._module))
            else:
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
        if self.view.is_logical:
            if self.counterpart is not None:
                raise PRGAInternalError(("Cannot create user-available ports in logical module {} "
                        "with a specified user counterpart").format(self._module))
            else:
                kwargs["net_class"] = NetClass.primitive
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
        if self.view.is_logical:
            if self.counterpart is not None:
                raise PRGAInternalError(("Cannot create user-available ports in logical module {} "
                        "with a specified user counterpart").format(self._module))
            else:
                kwargs["net_class"] = NetClass.primitive
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output,
                clock = clock, **kwargs)

# ----------------------------------------------------------------------------
# -- Builder for Logical Views of Single-Mode Primitives ---------------------
# ----------------------------------------------------------------------------
class LogicalPrimitiveBuilder(_BasePrimitiveBuilder):
    """Logical-view primitive module builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
        counterpart (`AbstractModule`): The user-view of the same primitive
    """

    __slots__ = ["_counterpart"]
    def __init__(self, context, module, counterpart = None):
        super(LogicalPrimitiveBuilder, self).__init__(context, module)
        self._counterpart = counterpart

    @property
    def view(self):
        return ModuleView.logical

    @property
    def counterpart(self):
        return self._counterpart

    @classmethod
    def new(cls, name, *, non_leaf = False, **kwargs):
        """Create a new custom primitive for building."""
        if non_leaf:
            kwargs["instances"] = OrderedDict()
        return Module(name,
                ports = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.custom,
                **kwargs)

    @classmethod
    def new_from_user_view(cls, user_view, *, non_leaf = False, **kwargs):
        """Create a new logical view from the user view of a primitive."""
        if non_leaf:
            kwargs["instances"] = OrderedDict()
        m = Module(user_view.name,
                ports = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.custom,
                **kwargs)
        for key, port in iteritems(user_view.ports):
            assert key == port.name
            ModuleUtils.create_port(m, key, len(port), port.direction,
                    is_clock = port.is_clock, clock = port.clock, net_class = NetClass.primitive)
        return m

    def create_cfg_port(self, name, width, direction, *,
            is_clock = False, clock = None, **kwargs):
        """Create a configuration port."""
        kwargs["net_class"] = NetClass.cfg
        return ModuleUtils.create_port(self._module, name, width, direction,
                is_clock = is_clock, clock = clock, **kwargs)

    def connect(self, sources, sinks, *, fully = False):
        """Create combinational connections between ports in the primitive."""
        NetUtils.connect(sources, sinks, fully = fully)

    def instantiate(self, model, name, **kwargs):
        """Add a sub-instance to this primitive."""
        return ModuleUtils.instantiate(self._module, model, name, **kwargs)

# ----------------------------------------------------------------------------
# -- Builder for User Views of Single-Mode Primitives ------------------------
# ----------------------------------------------------------------------------
class PrimitiveBuilder(_BasePrimitiveBuilder):
    """User-view primitive module builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    @property
    def view(self):
        return ModuleView.user

    @property
    def counterpart(self):
        return None

    @classmethod
    def new(cls, name, **kwargs):
        """Create a new custom primitive for building."""
        return Module(name,
                ports = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.custom,
                **kwargs)

    def add_combinational_path(self, sources, sinks):
        """Add a combinational path from ``sources`` to ``sinks``."""
        NetUtils.connect(sources, sinks, fully = True)

    def create_logical_counterpart(self, *, non_leaf = False, **kwargs):
        """`LogicalPrimitiveBuilder`: Create a builder for the logical counterpart of this module."""
        self.commit()
        return self._context.create_logical_primitive(self._module.name, non_leaf = non_leaf, **kwargs)
