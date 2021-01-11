# -*- encoding: ascii -*-

from .base import AbstractPass
from ..netlist import PortDirection, Module, ModuleUtils, NetUtils, TimingArcType
from ..core.common import ModuleClass, NetClass, IOType, ModuleView, SegmentID, BlockPinID, Position
from ..core.builder import ArrayBuilder
from ..prog import ProgDataValue
from ..util import Object, uno
from ..exception import PRGAInternalError, PRGAAPIError

from itertools import chain
from networkx.exception import NetworkXError

import logging
_logger = logging.getLogger(__name__)

__all__ = ['SwitchDelegate', 'Translation']

# ----------------------------------------------------------------------------
# -- Switch Delegate ---------------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchDelegate(Object):
    """Switch delegate choosing design-view switch modules for instantiation.
    
    Args:
        context (`Context`):
    """

    __slots__ = ['context']

    def __init__(self, context):
        self.context = context

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    def get_switch(self, width, module = None):
        """Get a switch module with ``width`` input bits.

        Args:
            width (:obj:`int`): Number of inputs needed
            module (`Module`): The module in which the switch is going to be added

        Returns:
            `Module`: Switch module found

        Note:
            The returned switch may have more than ``width`` input bits
        """
        key = (ModuleClass.switch, width)

        # check if the switch is already added
        try:
            return self.context.database[ModuleView.design, key]
        except KeyError:
            pass

        # create and add new switch module
        switch = self.context._database[ModuleView.design, key] = Module(
                "sw" + str(width),
                is_cell = True,
                view = ModuleView.design,
                key = key,
                module_class = ModuleClass.switch,
                verilog_template = "builtin/switch.tmpl.v")

        # ports and timing arcs
        i = ModuleUtils.create_port(switch, 'i', width, PortDirection.input_, net_class = NetClass.switch)
        o = ModuleUtils.create_port(switch, 'o', 1,     PortDirection.output, net_class = NetClass.switch)
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, i, o)

        ModuleUtils.create_port(switch, "prog_done", 1, PortDirection.input_, net_class = NetClass.prog)
        ModuleUtils.create_port(switch, "prog_data", width.bit_length(), PortDirection.input_,
                net_class = NetClass.prog)
        switch.prog_enable = tuple(
                ProgDataValue(i + 1, (0, len(switch.ports["prog_data"])))
                for i in range(width))

        # return module
        return switch

# ----------------------------------------------------------------------------
# -- Translation Pass --------------------------------------------------------
# ----------------------------------------------------------------------------
class Translation(AbstractPass):
    """Translate modules in abstract view to design view.

    Args:
        top (`Module`): Top-level array in abstract view. The top array from the context is selected by default

    Keyword Args:
        create_blackbox_for_undefined_primitives (:obj:`bool`): `Translation` does not know how to translate
            primitives. By default, if the design view is not defined for a primitive, an error is raised.
            If ``create_blackbox_for_undefined_primitives`` is set to ``True``, an empty design view is created in
            this case.
    """

    __slots__ = ['top', 'create_blackbox_for_undefined_primitives']
    def __init__(self, top = None, *, create_blackbox_for_undefined_primitives = False):
        self.top = top
        self.create_blackbox_for_undefined_primitives = create_blackbox_for_undefined_primitives

    @property
    def key(self):
        return "translation"

    @classmethod
    def _get_or_create_io(cls, module, iotype, position = Position(0, 0), subtile = 0):
        if module.module_class.is_io_block:
            if (port := module.ports.get(iotype)) is None:
                port = ModuleUtils.create_port(module,
                        iotype.case("ipin", "opin", "oe"),
                        1,
                        iotype.case(PortDirection.input_, PortDirection.output, PortDirection.output),
                        key = iotype,
                        net_class = NetClass.io)
            return port
        else:
            if (port := module.ports.get( (iotype, position, subtile) )) is None:
                port = ModuleUtils.create_port(module,
                        '{}_x{}y{}_{}'.format(iotype.name, *position, subtile),
                        1,
                        iotype.case(PortDirection.input_, PortDirection.output, PortDirection.output),
                        key = (iotype, position, subtile),
                        net_class = NetClass.io)
            return port

    def _process_module(self, module, context, *, disable_coalesce = False, is_top = False):
        # shortcut if the module is already processed
        if (design := context._database.get((ModuleView.design, module.key))) is not None:
            return design

        # make sure the abstract module is tranlatible
        if not (module.module_class.is_slice or
                module.module_class.is_block or
                module.module_class.is_routing_box or
                module.module_class.is_tile or
                module.module_class.is_array): 
            if self.create_blackbox_for_undefined_primitives and module.module_class.is_primitive:
                pass
            else:
                raise PRGAInternalError("Cannot translate module '{}'. Its module class is {:r}"
                        .format(module, module.module_class))

        # prepare the arguments for creating a new module
        kwargs = {
                'view': ModuleView.design,
                'module_class': module.module_class,
                'key': module.key,
                }

        # propagate attributes
        if module.module_class.is_primitive:
            kwargs["primitive_class"] = module.primitive_class
            kwargs["is_cell"] = True
        elif not disable_coalesce and module.coalesce_connections:
            kwargs['coalesce_connections'] = True

        if (module.module_class.is_block or 
                module.module_class.is_tile or 
                module.module_class.is_array):
            kwargs["width"] = module.width
            kwargs["height"] = module.height

        # create design module
        design = Module(module.name, **kwargs)

        # translate ports
        for port in module.ports.values():
            attrs = {"key": port.key, "is_clock": port.is_clock}
            if module.module_class.is_primitive:
                attrs["net_class"] = NetClass.user
                if (port_class := getattr(port, "port_class", None)) is not None:
                    attrs["port_class"] = port_class
            elif module.module_class.is_slice:
                attrs["net_class"] = NetClass.user
            elif module.module_class.is_block:
                if (global_ := getattr(port, "global_", None)) is not None:
                    attrs["net_class"] = NetClass.global_
                    attrs["global_"] = global_
                else:
                    attrs["net_class"] = NetClass.block
            elif module.module_class.is_routing_box:
                if port.key.node_type.is_segment:
                    attrs["net_class"] = NetClass.segment
                else:
                    attrs["net_class"] = NetClass.bridge
            elif module.module_class.is_array or module.module_class.is_tile:
                attrs["net_class"] = NetClass.bridge
            if "net_class" not in attrs:
                raise NotImplementedError("Could not deduct net class of {}".format(port))
            ModuleUtils.create_port(design, port.name, len(port), port.direction, **attrs)

        # translate instances
        for instance in module.instances.values():
            design_model = self._process_module(instance.model, context,
                    disable_coalesce = disable_coalesce or not design.coalesce_connections)
            design_instance = ModuleUtils.instantiate(design, design_model, instance.name, key = instance.key)

        # translate connections
        if module.module_class.is_primitive:
            pass
        else:
            # abstract connections
            for usink in ModuleUtils._iter_nets(module):
                if not usink.is_sink:
                    continue
                lsink = NetUtils._dereference(design, NetUtils._reference(usink))
                if module.coalesce_connections:
                    usrc = NetUtils.get_source(usink, return_const_if_unconnected = True)
                    NetUtils.connect(NetUtils._dereference(design, NetUtils._reference(usrc)), lsink)
                elif not module.allow_multisource:
                    usrc = NetUtils.get_source(usink, return_const_if_unconnected = True)
                    NetUtils.connect([NetUtils._dereference(design, NetUtils._reference(i)) for i in usrc], lsink)
                else:
                    for i, bit in enumerate(usink):
                        if len(usrcs := NetUtils.get_multisource(bit)) == 0:
                            continue
                        bitref = NetUtils._reference(bit)

                        if (len(usrcs) == 1
                                # always instantiate switch for switch boxes
                                and not module.module_class.is_switch_box 
                                # always instantiate switch for non-clock primitive inputs 
                                and not (usink.net_type.is_pin and usink.instance.model.module_class.is_primitive
                                    and not usink.model.is_clock)):

                            # direct connect (no programmability)
                            NetUtils.connect(NetUtils._dereference(design, NetUtils._reference(usrcs)), lsink[i])
                            continue

                        switch_model = context.switch_delegate.get_switch(len(usrcs), design)
                        switch_name = ["i_sw"]
                        if usink.net_type.is_pin:
                            switch_name.append( usink.instance.name )
                            switch_name.append( usink.model.name )
                        else:
                            switch_name.append( usink.name )
                        if bit.net_type.is_bit:
                            switch_name.append( str(i) )
                        switch = ModuleUtils.instantiate(design, switch_model, "_".join(switch_name),
                                key = (ModuleClass.switch, bitref))
                        NetUtils.connect(
                                [NetUtils._dereference(design, NetUtils._reference(usrc)) for usrc in usrcs], 
                                switch.pins["i"])
                        NetUtils.connect(switch.pins["o"], lsink[i])

            # design connections
            for net in ModuleUtils._iter_nets(design):
                # global wire?
                if net.net_type.is_pin and (global_ := getattr(net.model, "global_", None)) is not None:
                    if not is_top:
                        if (port := design.ports.get(global_.name)) is None:
                            port = ModuleUtils.create_port(design, global_.name, global_.width,
                                    PortDirection.input_, net_class = NetClass.global_, global_ = global_)
                        NetUtils.connect(port, net)
                    elif ((tile := ArrayBuilder.get_hierarchical_root(module, global_.bound_to_position)) is None or
                            (iob := tile.model.instances.get(global_.bound_to_subtile)) is None or
                            'inpad' not in iob.pins):
                        raise PRGAInternalError("Global wire '{}' bound to subtile {} at {} but no IO input found"
                                .format(global_.name, global_.bound_to_subtile, global_.bound_to_position))
                    else:
                        NetUtils.connect(self._get_or_create_io(design, IOType.ipin,
                            global_.bound_to_position, global_.bound_to_subtile), net)
                # IO?
                elif net.net_type.is_pin and net.model.net_class.is_io:
                    port = None
                    if net.instance.model.module_class.is_primitive:
                        port = self._get_or_create_io(design, net.model.key)
                    elif net.instance.model.module_class.is_io_block:
                        port = self._get_or_create_io(design, net.model.key, subtile = net.instance.key)
                    else:
                        iotype, pos, subtile = net.model.key
                        port = self._get_or_create_io(design, iotype, pos + net.instance.key, subtile)
                    if port.direction.is_input:
                        NetUtils.connect(port, net)
                    else:
                        NetUtils.connect(net, port)

        # add to the database
        context._database[ModuleView.design, module.key] = design
        _logger.info(" .. Translated: {}".format(module))
        return design

    def run(self, context, renderer = None):
        top = uno(self.top, context.top)
        if top is None:
            raise PRGAAPIError("Top-level array not set yet.")
        # recursively process modules
        system_top = self._process_module(top, context, is_top = True)
        if top is context.top:
            context.system_top = system_top
