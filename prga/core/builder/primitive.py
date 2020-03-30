# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseBuilder
from ..common import ModuleClass, PrimitiveClass, PrimitivePortClass, NetClass, ModuleView
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...exception import PRGAAPIError, PRGAInternalError

from abc import abstractproperty
from collections import OrderedDict

__all__ = ["LogicalPrimitiveBuilder", "PrimitiveBuilder", 'MultimodeBuilder']

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
        elif self._module.primitive_class.is_memory:
            raise PRGAAPIError("Ports are pre-defined and fixed for memory primitive '{}'"
                .format(self._module))
        return ModuleUtils.create_port(self._module, name, 1, PortDirection.input_,
                is_clock = True, **kwargs)

    def create_input(self, name, width, *, clock = None, **kwargs):
        """Create an input in the primitive.

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
        elif self._module.primitive_class.is_memory:
            raise PRGAAPIError("Ports are pre-defined and fixed for memory primitive '{}'"
                .format(self._module))
        return ModuleUtils.create_port(self._module, name, width, PortDirection.input_,
                clock = clock, **kwargs)

    def create_output(self, name, width, *, clock = None, **kwargs):
        """Create an output in the primitive.

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
        elif self._module.primitive_class.is_memory:
            raise PRGAAPIError("Ports are pre-defined and fixed for memory primitive '{}'"
                .format(self._module))
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

    def add_combinational_path(self, sources, sinks):
        """Create combinational connections between ports in the primitive."""
        NetUtils.connect(sources, sinks, fully = True)

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
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.custom,
                **kwargs)

    @classmethod
    def new_memory(cls, name, addr_width, data_width, *, single_port = False, **kwargs):
        """Create a new memory primitive."""
        kwargs.setdefault("techmap_template", "memory.techmap.tmpl.v")
        kwargs.setdefault("lib_template", "memory.lib.tmpl.v")
        kwargs.setdefault("mem_infer_rule_template", "builtin.tmpl.rule")
        m = Module(name,
                ports = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.memory,
                **kwargs)
        ModuleUtils.create_port(m, "clk", 1, PortDirection.input_,
                is_clock = True, port_class = PrimitivePortClass.clock)
        if single_port:
            ModuleUtils.create_port(m, "we", 1, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.write_en)
            ModuleUtils.create_port(m, "addr", addr_width, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.address)
            ModuleUtils.create_port(m, "data", data_width, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.data_in)
            ModuleUtils.create_port(m, "out", data_width, PortDirection.output,
                    clock = "clk", port_class = PrimitivePortClass.data_out)
        else:
            ModuleUtils.create_port(m, "we1", 1, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.write_en1)
            ModuleUtils.create_port(m, "addr1", addr_width, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.address1)
            ModuleUtils.create_port(m, "data1", data_width, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.data_in1)
            ModuleUtils.create_port(m, "out1", data_width, PortDirection.output,
                    clock = "clk", port_class = PrimitivePortClass.data_out1)
            ModuleUtils.create_port(m, "we2", 1, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.write_en2)
            ModuleUtils.create_port(m, "addr2", addr_width, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.address2)
            ModuleUtils.create_port(m, "data2", data_width, PortDirection.input_,
                    clock = "clk", port_class = PrimitivePortClass.data_in2)
            ModuleUtils.create_port(m, "out2", data_width, PortDirection.output,
                    clock = "clk", port_class = PrimitivePortClass.data_out2)
        return m

    def create_input(self, name, width, *, clock = None, vpr_combinational_sinks = tuple(), **kwargs):
        """Create an input in the primitive.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Width of the port

        Keyword Args:
            clock (:obj:`str`): Clock of the port
            vpr_combinational_sinks (:obj:`Sequence` [:obj:`str` ]): Output ports in this primitive to which combinational
                paths exist from this port
            **kwargs: Additional attributes to be associated with the port
        """
        if vpr_combinational_sinks:
            kwargs["vpr_combinational_sinks"] = tuple(set(vpr_combinational_sinks))
        super(PrimitiveBuilder, self).create_input(name, width, clock = clock, **kwargs)

    def commit(self, *, dont_create_logical_counterpart = False):
        m = super(PrimitiveBuilder, self).commit()
        # additional checks: combinational sinks
        for p in itervalues(self.ports):
            if p.direction.is_input and not p.is_clock:
                for sink_name in getattr(p, "vpr_combinational_sinks", tuple()):
                    sink = self.ports.get(sink_name)
                    if sink is None:
                        raise PRGAAPIError("Combinational sink '{}' of input port '{}' not found in primitive '{}'"
                                .format(sink_name, p, self._module))
                    elif not sink.direction.is_output:
                        raise PRGAAPIError("Combinational sink '{}' of input port '{}' is not an output"
                                .format(sink_name, p))
        if self._module.primitive_class.is_memory and not dont_create_logical_counterpart:
            self._context.create_logical_primitive(self._module.name,
                    verilog_template = "memory.tmpl.v").commit()
        return m

    def create_logical_counterpart(self, *, non_leaf = False, **kwargs):
        """`LogicalPrimitiveBuilder`: Create a builder for the logical counterpart of this module."""
        self.commit()
        return self._context.create_logical_primitive(self._module.name, non_leaf = non_leaf, **kwargs)

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

    def connect(self, sources, sinks, *, fully = False, pack_patterns = tuple()):
        """Connect ``sources`` to ``sinks``."""
        if not pack_patterns:
            NetUtils.connect(sources, sinks, fully = fully)
        else:
            NetUtils.connect(sources, sinks, fully = fully, pack_patterns = pack_patterns)

    def commit(self):
        return self._module

# ----------------------------------------------------------------------------
# -- Builder for Logical Views of Multi-Mode Primitives ----------------------
# ----------------------------------------------------------------------------
class _LogicalMultimodeBuilder(BaseBuilder):
    """Logical multi-mode module builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
        counterpart (`AbstractModule`): The user-view of the same primitive

    Keyword Args:
        non_leaf (:obj:`bool`): If the module is not a leaf module
    """

    __slots__ = ["_counterpart", '_non_leaf']
    def __init__(self, context, module, counterpart = None, *, non_leaf = False):
        super(_LogicalMultimodeBuilder, self).__init__(context, module)
        self._counterpart = counterpart
        self._non_leaf = non_leaf

    @property
    def view(self):
        return ModuleView.logical

    @property
    def counterpart(self):
        return None

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: Proxy to the module instances."""
        return self._module.instances

    @classmethod
    def new(cls, user_view, *, non_leaf = False, **kwargs):
        """Create a new logical view from the user view of a primitive."""
        if not non_leaf:
            kwargs["instances"] = OrderedDict()
        m = Module(user_view.name,
                ports = OrderedDict(), 
                module_class = ModuleClass.primitive,
                allow_multisource = True,
                modes = OrderedDict(),
                **kwargs)
        for key, port in iteritems(user_view.ports):
            assert key == port.name
            ModuleUtils.create_port(m, port.name, len(port), port.direction,
                    key = key, is_clock = port.is_clock, net_class = NetClass.primitive)
        for mode_name, mode in iteritems(user_view.modes):
            assert mode_name == mode.key
            m.modes[mode_name] = _ModeBuilder.new(m, mode_name, ModuleView.logical)
        return m

    def create_cfg_port(self, name, width, direction, *,
            is_clock = False, clock = None, **kwargs):
        """Create a configuration port."""
        kwargs["net_class"] = NetClass.cfg
        return ModuleUtils.create_port(self._module, name, width, direction,
                is_clock = is_clock, clock = clock, **kwargs)

    def instantiate(self, model, name, **kwargs):
        if self._non_leaf:
            raise PRGAInternalError("Cannot instantiate sub-modules in leaf module '{}'"
                    .format(self._module))
        return ModuleUtils.instantiate(self._module, model, name, **kwargs)

    def add_combinational_path(self, sources, sinks):
        """Add a combinational path from ``sources`` to ``sinks``."""
        NetUtils.connect(sources, sinks, fully = True)

    def edit_mode(self, mode, **kwargs):
        """`_ModeBuilder`: Edit the specified mode."""
        try:
            mode = self._module.modes[mode]
        except KeyError:
            raise PRGAInternalError("'{}' does not have mode '{}'".format(mode))
        for k, v in iteritems(kwargs):
            setattr(mode, k, v)
        return _ModeBuilder(self._context, mode)

# ----------------------------------------------------------------------------
# -- Builder for User Views of Multi-Mode Primitives -------------------------
# ----------------------------------------------------------------------------
class MultimodeBuilder(_BasePrimitiveBuilder):
    """Multi-mode module builder.

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
        """Create a new multi-mode primitive for building."""
        return Module(name,
                ports = OrderedDict(),
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.multimode,
                modes = OrderedDict(),
                **kwargs)

    def create_mode(self, name, **kwargs):
        """Create a new mode for this multi-mode primitive."""
        if name in self._module.modes:
            raise PRGAInternalError("Conflicting mode name: {}".format(name))
        mode = self._module.modes[name] = _ModeBuilder.new(self._module, name, self.view, **kwargs)
        return _ModeBuilder(self._context, mode)

    def create_logical_counterpart(self, *, non_leaf = False, **kwargs):
        """`LogicalPrimitiveBuilder`: Create a builder for the logical counterpart of this module."""
        self.commit()
        m = self._context._database.get( (ModuleView.logical, self._module.name) )
        if m is None:
            m = self._context._database[ModuleView.logical, self._module.name] = _LogicalMultimodeBuilder.new(
                    self._module, non_leaf = non_leaf, **kwargs)
        return _LogicalMultimodeBuilder(self._context, m)
