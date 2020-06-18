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
    def counterpart(self):
        """`Module`: The user counterpart of the primitive being built if we're building logical view."""
        raise NotImplementedError

    def create_clock(self, name, **kwargs):
        """Create a clock in the primitive.

        Args:
            name (:obj:`str`): Name of the clock

        Keyword Args:
            **kwargs: Additional attributes to be associated with the port

        Returns:
            `Port`:
        """
        if self._module.view.is_logical:
            if self.counterpart is not None:
                raise PRGAInternalError("Cannot create user-available ports in the logical view of {}"
                    .format(self._module))
            else:
                kwargs["net_class"] = NetClass.primitive
        elif self._module.primitive_class.is_memory:
            raise PRGAAPIError("Ports are pre-defined and immutable for memory primitive '{}'"
                .format(self._module))
        return ModuleUtils.create_port(self._module, name, 1, PortDirection.input_,
                is_clock = True, **kwargs)

    def create_input(self, name, width, **kwargs):
        """Create an input in the primitive.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Width of the port

        Keyword Args:
            **kwargs: Additional attributes to be associated with the port

        Returns:
            `Port`:
        """
        if self._module.view.is_logical:
            if self.counterpart is not None:
                raise PRGAInternalError("Cannot create user-available ports in the logical view of {}"
                        .format(self._module))
            else:
                kwargs["net_class"] = NetClass.primitive
        elif self._module.primitive_class.is_memory:
            raise PRGAAPIError("Ports are pre-defined and immutable for memory primitive '{}'"
                .format(self._module))
        return ModuleUtils.create_port(self._module, name, width, PortDirection.input_, **kwargs)

    def create_output(self, name, width, **kwargs):
        """Create an output in the primitive.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Width of the port

        Keyword Args:
            **kwargs: Additional attributes to be associated with the port

        Returns:
            `Port`:
        """
        if self._module.view.is_logical:
            if self.counterpart is not None:
                raise PRGAInternalError("Cannot create user-available ports in the logical view of {}"
                        .format(self._module))
            else:
                kwargs["net_class"] = NetClass.primitive
        elif self._module.primitive_class.is_memory:
            raise PRGAAPIError("Ports are pre-defined and immutable for memory primitive '{}'"
                .format(self._module))
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output, **kwargs)

    def add_timing_arc(self, sources, sinks, **kwargs):
        """Create timing arcs from ``sources`` to ``sinks``.
        
        Args:
            sources: An input port, a subset of an input port, or a list of input ports/subsets
            sinks: An output port, a subset of an output port, or a list of output ports/subsets

        Keyword Args:
            **kwargs: Additional attributes to be associated with the timing arcs
        """
        if not self._module.is_cell:
            raise PRGAInternalError("Cannot add timing arc to {}".format(self._module))
        NetUtils.connect(sources, sinks, fully = True, **kwargs)

# ----------------------------------------------------------------------------
# -- Builder for Logical Views of Single-Mode Primitives ---------------------
# ----------------------------------------------------------------------------
class LogicalPrimitiveBuilder(_BasePrimitiveBuilder):
    """Logical-view primitive module builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
        counterpart (`Module`): The user-view of the same primitive
    """

    __slots__ = ["_counterpart"]
    def __init__(self, context, module, counterpart = None):
        super(LogicalPrimitiveBuilder, self).__init__(context, module)
        self._counterpart = counterpart

    @property
    def counterpart(self):
        return self._counterpart

    @classmethod
    def new(cls, name, *, not_cell = False, **kwargs):
        """Create a new custom primitive for building.
        
        Args:
            name (:obj:`str`): Name of the primitive

        Keyword Args:
            not_cell (:obj:`bool`): If set to ``True``, sub-modules can be added to the primitive
            **kwargs: Custom attibutes assigned to the primitive

        Returns:
            `Module`:
        """
        return Module(name,
                view = ModuleView.logical,
                is_cell = not not_cell,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.custom,
                **kwargs)

    @classmethod
    def new_from_user_view(cls, user_view, *, not_cell = False, **kwargs):
        """Create a new logical view from the user view of a primitive.
        
        Args:
            user_view (`Module`): User view of the primitive

        Keyword Args:
            not_cell (:obj:`bool`): If set to ``True``, the primitive is created so sub-modules can be added
            **kwargs: Custom attibutes assigned to the primitive

        Returns:
            `Module`:
        """
        m = Module(user_view.name,
                view = ModuleView.logical,
                is_cell = not not_cell,
                module_class = ModuleClass.primitive,
                **kwargs)
        for key, port in iteritems(user_view.ports):
            assert key == port.name
            ModuleUtils.create_port(m, key, len(port), port.direction,
                    is_clock = port.is_clock, net_class = NetClass.primitive)
        return m

    def create_cfg_port(self, name, width, direction, *, is_clock = False, **kwargs):
        """Create a configuration port.

        Args:
            name (:obj:`str`): Name of the configuration port
            width (:obj:`int`): Number of bits in this port
            direction (`PortDirection`): Direction of this port

        Keyword Args:
            is_clock (:obj:`bool`): Mark this port as a configuration clock
            **kwargs: Custom attibutes assigned to the port

        Returns:
            `Port`:
        """
        kwargs["net_class"] = NetClass.cfg
        return ModuleUtils.create_port(self._module, name, width, direction, is_clock = is_clock, **kwargs)

    def instantiate(self, model, name, **kwargs):
        """Add an instance to this primitive.
        
        Args:
            model (`Module`): Module to be instantiated
            name (:obj:`str`): Name of the instance

        Keyword Args:
            **kwargs: Custom attibutes assigned to the instance

        Returns:
            `Instance`:
        """
        if self._module.is_cell:
            raise PRGAInternalError("Cannot instantiate {} in {}".format(model, self._module))
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
            **kwargs: Additional attibutes to be associated with all connections
        """
        if self._module.is_cell:
            raise PRGAInternalError("Cannot connect {} and {} in {}".format(sources, sinks, self._module))
        NetUtils.connect(sources, sinks, fully = fully, **kwargs)

# ----------------------------------------------------------------------------
# -- Builder for User Views of Single-Mode Primitives ------------------------
# ----------------------------------------------------------------------------
class PrimitiveBuilder(_BasePrimitiveBuilder):
    """User-view primitive module builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    @property
    def counterpart(self):
        return None

    @classmethod
    def new(cls, name, **kwargs):
        """Create a new primitive in user view for building.
        
        Args:
            name (:obj:`str`): Name of the primitive

        Keyword Args:
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `Module`:
        """
        return Module(name,
                view = ModuleView.user,
                is_cell = True,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.custom,
                **kwargs)

    @classmethod
    def new_memory(cls, name, addr_width, data_width, *, single_port = False, **kwargs):
        """Create a new memory primitive in user view.
        
        Args:
            name (:obj:`str`): Name of the primitive
            addr_width (:obj:`int`): Width of the address port\(s\)
            data_width (:obj:`int`): Width of the data port\(s\)

        Keyword Args:
            single_port (:obj:`bool`): This method generates dual-port memory by default. Set this to ``True`` if a
                single-port memory is needed
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `Module`:
        """
        kwargs.setdefault("techmap_template", "memory.techmap.tmpl.v")
        kwargs.setdefault("lib_template", "memory.lib.tmpl.v")
        kwargs.setdefault("mem_infer_rule_template", "builtin.tmpl.rule")
        m = Module(name,
                view = ModuleView.user,
                is_cell = True,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.memory,
                **kwargs)
        clk = ModuleUtils.create_port(m, "clk", 1, PortDirection.input_,
                is_clock = True, port_class = PrimitivePortClass.clock)
        i, o = PortDirection.input_, PortDirection.output
        p = []
        if single_port:
            p.append(ModuleUtils.create_port(m, "we", 1, i, clock = "clk",
                port_class = PrimitivePortClass.write_en))
            p.append(ModuleUtils.create_port(m, "addr", addr_width, i, clock = "clk",
                port_class = PrimitivePortClass.address))
            p.append(ModuleUtils.create_port(m, "data", data_width, i, clock = "clk",
                port_class = PrimitivePortClass.data_in))
            p.append(ModuleUtils.create_port(m, "out", data_width, o, clock = "clk",
                port_class = PrimitivePortClass.data_out))
        else:
            p.append(ModuleUtils.create_port(m, "we1", 1, i, clock = "clk",
                port_class = PrimitivePortClass.write_en1))
            p.append(ModuleUtils.create_port(m, "addr1", addr_width, i, clock = "clk",
                port_class = PrimitivePortClass.address1))
            p.append(ModuleUtils.create_port(m, "data1", data_width, i, clock = "clk",
                port_class = PrimitivePortClass.data_in1))
            p.append(ModuleUtils.create_port(m, "out1", data_width, o, clock = "clk",
                port_class = PrimitivePortClass.data_out1))
            p.append(ModuleUtils.create_port(m, "we2", 1, i, clock = "clk",
                port_class = PrimitivePortClass.write_en2))
            p.append(ModuleUtils.create_port(m, "addr2", addr_width, i, clock = "clk",
                port_class = PrimitivePortClass.address2))
            p.append(ModuleUtils.create_port(m, "data2", data_width, i, clock = "clk",
                port_class = PrimitivePortClass.data_in2))
            p.append(ModuleUtils.create_port(m, "out2", data_width, o, clock = "clk",
                port_class = PrimitivePortClass.data_out2))
        NetUtils.connect(clk, p, fully = True)
        return m

    def create_input(self, name, width, *, clock = None, vpr_combinational_sinks = tuple(), **kwargs):
        """Create an input port in the primitive.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Number of bits in the port

        Keyword Args:
            clock (:obj:`str`): If set, marks the input port as a sequential endpoint clocked by the specified clock
            vpr_combinational_sinks (:obj:`Sequence` [:obj:`str` ]): Output ports in this primitive to which combinational
                paths exist from this port. See `combinational_sink_ports`_ for more information
            **kwargs: Additional attributes to be associated with the port

        Returns:
            `Port`:

        .. combinational_sink_ports:
            https://docs.verilogtorouting.org/en/latest/arch/reference/#tag-%3Cportname=
        """
        vpr_combinational_sinks = tuple(set(vpr_combinational_sinks))
        try:
            clk = None if clock is None else self._module.ports[clock]
            sinks = tuple(self._module.ports[s] for s in vpr_combinational_sinks)
        except KeyError as e:
            raise PRGAInternalError("Port '{}' not found in {}".format(e.args[0], self._module))
        if clock:
            if not clk.is_clock:
                raise PRGAInternalError("{} is not a clock".format(clk))
            kwargs["clock"] = clock
        if vpr_combinational_sinks:
            kwargs["vpr_combinational_sinks"] = vpr_combinational_sinks
        port = super(PrimitiveBuilder, self).create_input(name, width, **kwargs)
        if clk is not None:
            self.add_timing_arc(clk, port)
        for sink in sinks:
            self.add_timing_arc(port, sink)
        return port

    def create_output(self, name, width, *, clock = None, **kwargs):
        """Create an output port in the primitive.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Number of bits in this port

        Keyword Args:
            clock (:obj:`str`): If set, marks the output port as a sequential startpoint clocked by the specified clock
            **kwargs: Additional attributes to be associated with the port

        Returns:
            `Port`:
        """
        try:
            clk = None if clock is None else self._module.ports[clock]
        except KeyError as e:
            raise PRGAInternalError("Port '{}' not found in {}".format(e.args[0], self._module))
        if clock:
            if not clk.is_clock:
                raise PRGAInternalError("{} is not a clock".format(clk))
            kwargs["clock"] = clock
        port = super(PrimitiveBuilder, self).create_output(name, width, **kwargs)
        if clk is not None:
            self.add_timing_arc(clk, port)
        return port

    def commit(self, *, dont_create_logical_counterpart = False):
        """Commit the module.

        Keyword Args:
            dont_create_logical_counterpart (:obj:`bool`): If set to ``True``, the logical view of this module won't
                be created automatically

        Returns:
            `Module`:
        """
        m = super(PrimitiveBuilder, self).commit()
        if self._module.primitive_class.is_memory and not dont_create_logical_counterpart:
            self._context.create_logical_primitive(self._module.name,
                    verilog_template = "memory.tmpl.v").commit()
        return m

    def create_logical_counterpart(self, *, not_cell = False, **kwargs):
        """Create the logical view of this module.

        Keyword Args:
            not_cell (:obj:`bool`): If set to ``True``, sub-modules can be added to the logical view
            **kwargs: Additional attributes to be associated with the logical view

        Returns:
            `LogicalPrimitiveBuilder`:
        """
        self.commit()
        return self._context.create_logical_primitive(self._module.name, not_cell = not_cell, **kwargs)

# ----------------------------------------------------------------------------
# -- Builder for One Mode in a Multi-mode Primitive --------------------------
# ----------------------------------------------------------------------------
class _ModeBuilder(BaseBuilder):
    """Mode builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    @classmethod
    def new(cls, parent, name, **kwargs):
        """Create a new mode in the multi-mode primitive.

        Args:
            parent (`Module`): The multi-mode primitive that this mode belongs to
            name (:obj:`str`): Name of this mode

        Keyword Args:
            **kwargs: Additional attributes to be associated with the mode

        Returns:
            `Module`:
        """
        m = Module(parent.name + "." + name,
                allow_multisource = True,
                module_class = ModuleClass.mode,
                parent = parent,
                key = name,
                **kwargs)
        for key, port in iteritems(parent.ports):
            ModuleUtils.create_port(m, port.name, len(port), port.direction,
                    key = key, is_clock = port.is_clock)
        return m

    def instantiate(self, model, name, reps = None, **kwargs):
        """Instantiate ``model`` in the mode.

        Args:
            model (`Module`): User view of the module to be instantiated
            name (:obj:`str`): Name of the instance. If ``reps`` is specified, each instance is named
                ``"{name}_i{index}"``
            reps (:obj:`int`): If set to a positive int, the specified number of instances are created, added to
                the mode, and returned. This affects the `num_pb`_ attribute in the output VPR specs

        Keyword Args:
            **kwargs: Additional attributes to be associated with the instance\(s\)

        Returns:
            `Instance` or :obj:`tuple` [`Instance`]:

        .. num_pb:
            https://docs.verilogtorouting.org/en/latest/arch/reference/#tag-%3Cportname=
        """
        if reps is None:
            return ModuleUtils.instantiate(self._module, model, name, **kwargs)
        else:
            return tuple(ModuleUtils.instantiate(self._module, model, '{}_i{}'.format(name, i),
                key = (name, i), vpr_num_pb = reps, **kwargs) for i in range(reps))

    def connect(self, sources, sinks, *, fully = False, vpr_pack_patterns = tuple(), **kwargs):
        """Connect ``sources`` to ``sinks``.
        
        Args:
            sources: Source nets, i.e., an input port, an output pin of an instance, a subset of the above, or a list
                of a combination of the above
            sinks: Sink nets, i.e., an output port, an input pin of an instance, a subset of the above, or a list
                of a combination of the above

        Keyword Args:
            fully (:obj:`bool`): If set to ``True``, connections are made between every source and every sink
            vpr_pack_patterns (:obj:`Sequence` [:obj:`str`]): Add `pack_pattern`_ tags to the connections
            **kwargs: Additional attibutes to be associated with all connections

        .. pack_pattern:
            https://docs.verilogtorouting.org/en/latest/arch/reference/#tag-%3Cportname=
        """
        if not vpr_pack_patterns:
            NetUtils.connect(sources, sinks, fully = fully, **kwargs)
        else:
            NetUtils.connect(sources, sinks, fully = fully, vpr_pack_patterns = vpr_pack_patterns, **kwargs)

# ----------------------------------------------------------------------------
# -- Builder for User Views of Multi-Mode Primitives -------------------------
# ----------------------------------------------------------------------------
class MultimodeBuilder(_BasePrimitiveBuilder):
    """Multi-mode module builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    @property
    def counterpart(self):
        return None

    @classmethod
    def new(cls, name, **kwargs):
        """Create a new multi-mode primitive.
        
        Args:
            name (:obj:`str`): Name of the primitive

        Keyword Args:
            **kwargs: Additional attibutes to be associated with the primitive

        Returns:
            `Module`:
        """
        return Module(name,
                view = ModuleView.user,
                is_cell = True,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.multimode,
                modes = OrderedDict(),
                **kwargs)

    def create_mode(self, name, **kwargs):
        """Create a new mode for this multi-mode primitive.
        
        Args:
            name (:obj:`str`): Name of the mode

        Keyword Args:
            **kwargs: Additional attibutes to be associated with the mode

        Returns:
            `_ModeBuilder`:
        """
        if name in self._module.modes:
            raise PRGAInternalError("Conflicting mode name: {}".format(name))
        mode = self._module.modes[name] = _ModeBuilder.new(self._module, name, **kwargs)
        return _ModeBuilder(self._context, mode)

    def create_logical_counterpart(self, *, not_cell = False, **kwargs):
        """Create the logical view of this primitive.

        Keyword Args:
            not_cell (:obj:`bool`): If set, sub-modules can be added into this logical view
            **kwargs: Additional attibutes to be associated with the primitive

        Returns:
            `LogicalPrimitiveBuilder`:
        """
        self.commit()
        return self._context.create_logical_primitive(self._module.name, not_cell = not_cell, **kwargs)
