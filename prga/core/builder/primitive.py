# -*- encoding: ascii -*-

from .base import BaseBuilder
from ..common import ModuleClass, PrimitiveClass, PrimitivePortClass, NetClass, ModuleView
from ...netlist import PortDirection, TimingArcType, Module, NetUtils, ModuleUtils
from ...exception import PRGAAPIError, PRGAInternalError
from ...util import uno

from abc import abstractproperty

__all__ = ["DesignViewPrimitiveBuilder", "PrimitiveBuilder", 'MultimodeBuilder']

# ----------------------------------------------------------------------------
# -- Base Builder for Primitives ---------------------------------------------
# ----------------------------------------------------------------------------
class _BasePrimitiveBuilder(BaseBuilder):
    """Base class for abstract-/design- [multi-mode] primitive builder."""

    @abstractproperty
    def counterpart(self):
        """`Module`: The abstract view of the primitive if we're building design view."""
        raise NotImplementedError

    def create_clock(self, name, **kwargs):
        """Create a clock in the primitive.

        Args:
            name (:obj:`str`): Name of the clock

        Keyword Args:
            **kwargs: Additional attributes assigned to the port

        Returns:
            `Port`:
        """
        if self._module.view.is_design:
            if self.counterpart is not None:
                raise PRGAInternalError("Cannot create user-available ports in the design view of {}"
                    .format(self._module))
            else:
                kwargs["net_class"] = NetClass.user
        elif self._module.primitive_class.is_memory:
            raise PRGAAPIError("Ports are pre-defined and immutable for memory primitive '{}'"
                .format(self._module))
        return ModuleUtils.create_port(self._module, name, 1, PortDirection.input_, is_clock = True, **kwargs)

    def create_input(self, name, width, **kwargs):
        """Create an input in the primitive.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Width of the port

        Keyword Args:
            **kwargs: Additional attributes assigned to the port

        Returns:
            `Port`:
        """
        if self._module.view.is_design:
            if self.counterpart is not None:
                raise PRGAInternalError("Cannot create user-available ports in the design view of {}"
                        .format(self._module))
            else:
                kwargs["net_class"] = NetClass.user
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
            **kwargs: Additional attributes assigned to the port

        Returns:
            `Port`:
        """
        if self._module.view.is_design:
            if self.counterpart is not None:
                raise PRGAInternalError("Cannot create user-available ports in the design view of {}"
                        .format(self._module))
            else:
                kwargs["net_class"] = NetClass.user
        elif self._module.primitive_class.is_memory:
            raise PRGAAPIError("Ports are pre-defined and immutable for memory primitive '{}'"
                .format(self._module))
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output, **kwargs)

    def create_timing_arc(self, type_, source, sink, *, max_ = None, min_ = None):
        """Create a ``type_``-typed timing arc from ``source`` to ``sink``.

        Args:
            types (`TimingArcType` or :obj:`str`): Type of the timing arc
            source (`Port`): An input port or a clock in the current module
            sink (`Port`): A port in the current module

        Keyword Args:
            max_, min_: Refer to `TimingArc` for more information

        Returns:
            `TimingArc`: The created timing arc
        """
        return NetUtils.create_timing_arc(TimingArcType.construct(type_), source, sink, max_ = max_, min_ = min_)

# ----------------------------------------------------------------------------
# -- Builder for Design Views of Single-Mode Primitives ----------------------
# ----------------------------------------------------------------------------
class DesignViewPrimitiveBuilder(_BasePrimitiveBuilder):
    """Design-view primitive module builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
        counterpart (`Module`): The abstract view of the same primitive
    """

    __slots__ = ["_counterpart"]
    def __init__(self, context, module, counterpart = None):
        super(DesignViewPrimitiveBuilder, self).__init__(context, module)
        self._counterpart = counterpart

    @property
    def counterpart(self):
        return self._counterpart

    @classmethod
    def new(cls, name, *, not_cell = False, **kwargs):
        """Create a new custom primitive.
        
        Args:
            name (:obj:`str`): Name of the primitive

        Keyword Args:
            not_cell (:obj:`bool`): If set, the design-view primitive is not a cell module
            **kwargs: Additional attibutes assigned to the primitive

        Returns:
            `Module`:
        """
        kwargs.setdefault("primitive_class", PrimitiveClass.custom)

        return Module(name,
                is_cell = not not_cell,
                view = ModuleView.design,
                module_class = ModuleClass.primitive,
                **kwargs)

    @classmethod
    def new_from_abstract_view(cls, abstract, *, not_cell = False, **kwargs):
        """Create a new design view from the abstract view of a primitive.
        
        Args:
            abstract (`Module`): Abstract view of the primitive

        Keyword Args:
            not_cell (:obj:`bool`): If set, the design-view primitive is not a cell module
            **kwargs: Additional attibutes assigned to the primitive

        Returns:
            `Module`:
        """
        m = Module(abstract.name,
                is_cell = not not_cell,
                view = ModuleView.design,
                key = abstract.key,
                module_class = ModuleClass.primitive,
                primitive_class = abstract.primitive_class,
                **kwargs)
        for key, port in abstract.ports.items():
            assert key == port.name
            if (port_class := getattr(port, "port_class", None)) is None:
                ModuleUtils.create_port(m, key, len(port), port.direction,
                        is_clock = port.is_clock, net_class = NetClass.user)
            else:
                ModuleUtils.create_port(m, key, len(port), port.direction,
                        is_clock = port.is_clock, net_class = NetClass.user, port_class = port_class)
        return m

    def create_prog_port(self, name, width, direction, *, is_clock = False, **kwargs):
        """Create a programming port.

        Args:
            name (:obj:`str`): Name of the programming port
            width (:obj:`int`): Number of bits in this port
            direction (`PortDirection` or :obj:`str`): Direction of this port

        Keyword Args:
            is_clock (:obj:`bool`): Mark this port as a programming clock
            **kwargs: Custom attibutes assigned to the port

        Returns:
            `Port`:
        """
        kwargs["net_class"] = NetClass.prog
        return ModuleUtils.create_port(self._module, name, width,
                PortDirection.construct(direction), is_clock = is_clock, **kwargs)

# ----------------------------------------------------------------------------
# -- Builder for Abstract Views of Single-Mode Primitives --------------------
# ----------------------------------------------------------------------------
class PrimitiveBuilder(_BasePrimitiveBuilder):
    """Abstract view primitive module builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    @property
    def counterpart(self):
        return None

    @classmethod
    def new(cls, name, *, vpr_model = None, **kwargs):
        """Create a new primitive in abstract view for building.
        
        Args:
            name (:obj:`str`): Name of the primitive

        Keyword Args:
            vpr_model (:obj:`str`): Name of the VPR model. Default: "m_{name}"
            **kwargs: Additional attributes assigned to the primitive

        Returns:
            `Module`:
        """
        kwargs.setdefault("primitive_class", PrimitiveClass.custom)

        return Module(name,
                is_cell = True,
                view = ModuleView.abstract,
                module_class = ModuleClass.primitive,
                vpr_model = uno(vpr_model, "m_{}".format(name)),
                **kwargs)

    def build_design_view_counterpart(self, *, not_cell = False, **kwargs):
        """Build the design view of this module.

        Keyword Args:
            not_cell (:obj:`bool`): If set, the design-view primitive is not a cell module
            **kwargs: Additional attributes assigned to the design view

        Returns:
            `DesignViewPrimitiveBuilder`:
        """
        self.commit()
        return self._context.build_design_view_primitive(self._module.name, not_cell = not_cell, **kwargs)

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
            **kwargs: Additional attributes assigned to the mode

        Returns:
            `Module`:
        """
        m = Module(parent.name + "." + name,
                key = name,
                allow_multisource = True,
                module_class = ModuleClass.mode,
                parent = parent,
                **kwargs)
        for key, port in parent.ports.items():
            ModuleUtils.create_port(m, port.name, len(port), port.direction,
                    key = key, is_clock = port.is_clock)
        return m

    def instantiate(self, model, name, reps = None, **kwargs):
        """Instantiate ``model`` in the mode.

        Args:
            model (`Module`): Abstract view of the module to be instantiated
            name (:obj:`str`): Name of the instance. If ``reps`` is specified, each instance is named
                ``"{name}_i{index}"``
            reps (:obj:`int`): If set to a positive int, the specified number of instances are created, added to
                the mode, and returned. This affects the `num_pb`_ attribute in the output VPR specs

        Keyword Args:
            **kwargs: Additional attributes assigned to the instance\(s\)

        Returns:
            `Instance` or :obj:`tuple` [`Instance`]:

        .. _num\_pb:
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
            **kwargs: Additional attibutes assigned to all connections

        .. _pack\_pattern:
            https://docs.verilogtorouting.org/en/latest/arch/reference/#tag-%3Cportname=
        """
        if not vpr_pack_patterns:
            NetUtils.connect(sources, sinks, fully = fully, **kwargs)
        else:
            NetUtils.connect(sources, sinks, fully = fully, vpr_pack_patterns = vpr_pack_patterns, **kwargs)

# ----------------------------------------------------------------------------
# -- Builder for Abstract Views of Multi-Mode Primitives ---------------------
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
            **kwargs: Additional attibutes assigned to the primitive

        Returns:
            `Module`:
        """
        return Module(name,
                is_cell = True,
                view = ModuleView.abstract,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.multimode,
                modes = {},
                **kwargs)

    def build_mode(self, name, **kwargs):
        """Create a new mode for this multi-mode primitive.
        
        Args:
            name (:obj:`str`): Name of the mode

        Keyword Args:
            **kwargs: Additional attibutes assigned to the mode

        Returns:
            `_ModeBuilder`:
        """
        if name in self._module.modes:
            raise PRGAInternalError("Conflicting mode name: {}".format(name))
        mode = self._module.modes[name] = _ModeBuilder.new(self._module, name, **kwargs)
        return _ModeBuilder(self._context, mode)

    def build_design_view_counterpart(self, *, not_cell = False, **kwargs):
        """Build the design view of this primitive.

        Keyword Args:
            not_cell (:obj:`bool`): If set, sub-modules can be added into this design view
            **kwargs: Additional attibutes assigned to the primitive

        Returns:
            `DesignViewPrimitiveBuilder`:
        """
        self.commit()
        return self._context.build_design_view_primitive(self._module.name, not_cell = not_cell, **kwargs)
