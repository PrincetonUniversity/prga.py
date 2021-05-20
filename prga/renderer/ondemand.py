# -*- encoding: ascii -*-

from ..core.common import ModuleView, ModuleClass, PrimitiveClass, PrimitivePortClass, NetClass, IOType
from ..prog import ProgDataBitmap, ProgDataValue
from ..netlist import Module, NetUtils, ModuleUtils, PortDirection, TimingArcType
from ..exception import PRGAInternalError
from ..util import uno

from math import floor, log2

import logging
_logger = logging.getLogger(__name__)

__all__ = ['OnDemandCellLibrary']

# ----------------------------------------------------------------------------
# -- On-Demand Cell Libraries ------------------------------------------------
# ----------------------------------------------------------------------------
class OnDemandCellLibrary(object):
    """A host class for retrieving and creating on-demand cells."""

    @classmethod
    def create_memory(cls, context, addr_width, data_width, *,
            name = None, vpr_model = None, memory_type = "1r1w", **kwargs):
        """Create a single-mode RAM.

        Args:
            context (`Context`):
            addr_width (:obj:`int`): Width of the address port\(s\)
            data_width (:obj:`int`): Width of the data port\(s\)

        Keyword Args:
            name (:obj:`str`): Name of the memory module. Default: "ram_{memory_type}_a{addr_width}d{data_width}"
            vpr_model (:obj:`str`): Name of the VPR model. Default: "m_ram_{memory_type}"
            memory_type (:obj:`str`): ``"1r1w"``, ``"1r1w_init"``, ``"1rw"`` or ``"2rw"``. Default is ``"1r1w"``.
                ``"1r1w_init"`` memories are initializable and may be used as ROMs, but they are not supported by all
                programming circuitry types
            **kwargs: Additional attributes assigned to the primitive

        Returns:
            ``Module``:
        """
        name = uno(name, "ram_{}_a{}d{}".format(memory_type, addr_width, data_width))
        if memory_type == "1r1w_init":  # very different way of handling this

            # create a custom initializable primitive first
            bdr = context.build_primitive(name = name + ".init",
                    vpr_model = uno(vpr_model, "m_ram_1r1w_init_a{}d{}".format(addr_width, data_width)),
                    primitive_class = PrimitiveClass.blackbox_memory,
                    verilog_template = "bram/init/1r1w.lib.tmpl.v",
                    bram_rule_template = "bram/init/1r1w.tmpl.rule",
                    techmap_template = "bram/init/1r1w.techmap.tmpl.v",
                    parameters = { "INIT": data_width << addr_width, },
                    abstract_only = True)
            clk   = bdr.create_clock("clk")

            inputs, outputs = [], []
            inputs.append(  bdr.create_input("we",    1) )
            inputs.append(  bdr.create_input("waddr", addr_width) )
            inputs.append(  bdr.create_input("din",   data_width) )
            inputs.append(  bdr.create_input("raddr", addr_width) )
            outputs.append( bdr.create_output("dout", data_width) )

            for i in inputs:
                bdr.create_timing_arc("seq_end",   clk, i)
            for o in outputs:
                bdr.create_timing_arc("seq_start", clk, o)

            init = bdr.commit()

            # multimode wrapper
            bdr = context.build_multimode(name,
                    memory_type = memory_type, 
                    **kwargs)
            bdr.create_clock("clk")
            bdr.create_input("we",    1)
            bdr.create_input("waddr", addr_width)
            bdr.create_input("din",   data_width)
            bdr.create_input("raddr", addr_width)
            bdr.create_output("dout", data_width)

            # mode (1): RAM w/ INIT
            if True:
                mode = bdr.build_mode( "init" )
                core = mode.instantiate( init, "i_ram" )

                for k, p in mode.ports.items():
                    if p.direction.is_input:
                        mode.connect(p, core.pins[k])
                    else:
                        mode.connect(core.pins[k], p)

                mode.commit()

            # mode (2): RAM w/o INIT
            if True:
                mode = bdr.build_mode( "noinit" )
                core = mode.instantiate( cls.create_memory( context, addr_width, data_width ), "i_ram" )

                for k, p in mode.ports.items():
                    if p.direction.is_input:
                        mode.connect(p, core.pins[k])
                    else:
                        mode.connect(core.pins[k], p)

                mode.commit()

            return bdr.commit()

        if memory_type == "1r1w":
            kwargs.setdefault("verilog_template", "bram/1r1w.lib.tmpl.v")
            kwargs.setdefault("bram_rule_template", "bram/1r1w.tmpl.rule")
            kwargs.setdefault("techmap_template", "bram/1r1w.techmap.tmpl.v")

        elif memory_type in ("1rw", "2rw"):
            kwargs.setdefault("verilog_template", "bram/lib.tmpl.v")
            kwargs.setdefault("bram_rule_template", "bram/tmpl.rule")
            kwargs.setdefault("techmap_template", "bram/techmap.tmpl.v")

        else:
            raise PRGAAPIError("Unsupported memory type: {}. Supported values are: 1r1w, 1r1w_init, 1rw, 2rw"
                    .format(memory_type))

        m = context._add_module(Module(name,
            is_cell = True,
            view = ModuleView.abstract,
            module_class = ModuleClass.primitive,
            primitive_class = PrimitiveClass.memory,
            vpr_model = uno(vpr_model, "m_ram_{}".format(memory_type)),
            memory_type = memory_type,
            **kwargs))

        clk = ModuleUtils.create_port(m, "clk", 1, PortDirection.input_,
                is_clock = True, port_class = PrimitivePortClass.clock)
        i, o = PortDirection.input_, PortDirection.output
        inputs, outputs = [], []

        if memory_type == "1rw":
            inputs.append(ModuleUtils.create_port(m, "we", 1, i,
                port_class = PrimitivePortClass.write_en))
            inputs.append(ModuleUtils.create_port(m, "addr", addr_width, i,
                port_class = PrimitivePortClass.address))
            inputs.append(ModuleUtils.create_port(m, "data", data_width, i,
                port_class = PrimitivePortClass.data_in))
            outputs.append(ModuleUtils.create_port(m, "out", data_width, o,
                port_class = PrimitivePortClass.data_out))

        elif memory_type == "2rw":
            inputs.append(ModuleUtils.create_port(m, "we1", 1, i,
                port_class = PrimitivePortClass.write_en1))
            inputs.append(ModuleUtils.create_port(m, "addr1", addr_width, i,
                port_class = PrimitivePortClass.address1))
            inputs.append(ModuleUtils.create_port(m, "data1", data_width, i,
                port_class = PrimitivePortClass.data_in1))
            outputs.append(ModuleUtils.create_port(m, "out1", data_width, o,
                port_class = PrimitivePortClass.data_out1))
            inputs.append(ModuleUtils.create_port(m, "we2", 1, i,
                port_class = PrimitivePortClass.write_en2))
            inputs.append(ModuleUtils.create_port(m, "addr2", addr_width, i,
                port_class = PrimitivePortClass.address2))
            inputs.append(ModuleUtils.create_port(m, "data2", data_width, i,
                port_class = PrimitivePortClass.data_in2))
            outputs.append(ModuleUtils.create_port(m, "out2", data_width, o,
                port_class = PrimitivePortClass.data_out2))

        elif memory_type == "1r1w":
            inputs.append(ModuleUtils.create_port(m, "we", 1, i,
                port_class = PrimitivePortClass.write_en1))
            inputs.append(ModuleUtils.create_port(m, "waddr", addr_width, i,
                port_class = PrimitivePortClass.address1))
            inputs.append(ModuleUtils.create_port(m, "din", data_width, i,
                port_class = PrimitivePortClass.data_in1))
            inputs.append(ModuleUtils.create_port(m, "raddr", addr_width, i,
                port_class = PrimitivePortClass.address2))
            outputs.append(ModuleUtils.create_port(m, "dout", data_width, o,
                port_class = PrimitivePortClass.data_out2))

        for i in inputs:
            NetUtils.create_timing_arc(TimingArcType.seq_end, clk, i)
        for o in outputs:
            NetUtils.create_timing_arc(TimingArcType.seq_start, clk, o)

        return m

    @classmethod
    def _create_memory_design(cls, context, abstract):
        """Create design-view for memories."""
        if abstract.memory_type == "1r1w":
            lbdr = context.build_design_view_primitive(abstract.name,
                    key = abstract.key,
                    verilog_template = "bram/1r1w.sim.tmpl.v")
            lbdr.instantiate(
                    context.database[ModuleView.design, "prga_ram_1r1w_byp"],
                    "i_ram",
                    verilog_parameters = {
                        "DATA_WIDTH": len(lbdr.ports["din"]),
                        "ADDR_WIDTH": len(lbdr.ports["waddr"]),
                        })
            lbdr.create_prog_port("prog_done", 1, "input")
            lbdr.commit()

        elif abstract.memory_type == "1r1w_init":
            _logger.warning("No design view available for primitive '{}'".format(abstract.name))

        else:
            context.build_design_view_primitive(abstract.name,
                    key = abstract.key,
                    verilog_template = "bram/sim.tmpl.v").commit()

    @classmethod
    def create_multimode_memory(cls, context, core_addr_width, data_width, *,
            addr_width = None, name = None, memory_type = "1r1w", **kwargs):
        """Create a multi-mode RAM.

        Args:
            context (`Context`):
            core_addr_width (:obj:`int`): The address width of the single-mode, 1R1W RAM core behind the multi-mode
                logic
            data_width (:obj:`int`): The data width of the single-mode, 1R1W RAM core behind the multi-mode logic

        Keyword Args:
            name (:obj:`str`): Name of the multi-mode primitive. ``"fracram_a{addr_width}d{data_width}"`` by default.
            addr_width (:obj:`int`): The maximum address width. See notes for more information
            memory_type (:obj:`str`): ``"1r1w"`` or ``"1r1w_init"``. Default is ``"1r1w"``.
                ``"1r1w_init"`` memories are initializable and may be used as ROMs, but they are not supported by all
                programming circuitry types
            **kwargs: Additional attributes assigned to the primitive

        Returns:
            `Module`: Abstract view of the multi-modal primitive
        
        Notes:
            This method builds a multi-mode, fracturable 1R1W RAM. For example,
            ``create_multimode_memory(ctx, 9, 64)`` creates a multimode primitive with the following modes:
            ``512x64b``, ``1K32b``, ``2K16b``, ``4K8b``, ``8K4b``, ``16K2b``, and ``32K1b``.

            If 1b is not the desired smallest data width, change ``addr_width`` to a number between
            ``core_addr_width`` and ``core_addr_width + floor(log2(data_width))``.

            When ``data_width`` is not a power of 2, the actual data width of each mode is determined by the actual
            address width. For example, ``create_multimode_memory(ctx, 9, 72)`` creates the following modes:
            ``512x72b``, ``1K36b``, ``2K18b``, ``4K9b``, ``8K4b``, ``16K2b``, ``32K1b``. Note that instead of a
            ``9K4b``, we got a ``8K4b``.
        """
        if memory_type not in ("1r1w", "1r1w_init"):
            raise PRGAInternalError("Invalid memory type. Supported values are: '1r1w', '1r1w_init'")

        default_addr_width = core_addr_width + int(floor(log2(data_width)))
        addr_width = uno(addr_width, default_addr_width)

        if not (core_addr_width <= addr_width <= default_addr_width):
            raise PRGAInternalError("Invalid addr_width ({}). Valid numbers {} <= addr_width <= {}"
                    .format(addr_width, core_addr_width, default_addr_width))

        name = uno(name, "fracram_{}_a{}d{}".format(memory_type, addr_width, data_width))
        multimode = context.build_multimode(name,
                core_addr_width = core_addr_width,
                memory_type = memory_type + "_frac")
        multimode.create_clock("clk")
        multimode.create_input("waddr", addr_width)
        multimode.create_input("din", data_width)
        multimode.create_input("we", 1)
        multimode.create_input("raddr", addr_width)
        multimode.create_output("dout", data_width)

        for mode_addr_width in range(core_addr_width, addr_width + 1):
            mode_name = None

            if mode_addr_width >= 40:
                mode_name = "{}T".format(2 ** (mode_addr_width - 40))
            elif mode_addr_width >= 30:
                mode_name = "{}G".format(2 ** (mode_addr_width - 30))
            elif mode_addr_width >= 20:
                mode_name = "{}M".format(2 ** (mode_addr_width - 20))
            elif mode_addr_width >= 10:
                mode_name = "{}K".format(2 ** (mode_addr_width - 10))
            else:
                mode_name = "{}x".format(2 ** mode_addr_width)

            mode_data_width = data_width // (2 ** (mode_addr_width - core_addr_width))
            mode_name += str(mode_data_width) + "b"

            mode = multimode.build_mode(mode_name)

            core = mode.instantiate(
                    cls.create_memory(context, mode_addr_width, mode_data_width,
                        name = name + ".ram_{}_a{}d{}".format(memory_type, mode_addr_width, mode_data_width),
                        memory_type = memory_type, techmap_order = 1. + 1 / float(mode_addr_width),
                        abstract_only = True,
                        ),
                    "i_ram",
                    )
            NetUtils.connect(mode.ports["clk"], core.pins["clk"])
            NetUtils.connect(mode.ports["waddr"][:mode_addr_width], core.pins["waddr"])
            NetUtils.connect(mode.ports["din"][:mode_data_width], core.pins["din"])
            NetUtils.connect(mode.ports["we"], core.pins["we"])
            NetUtils.connect(mode.ports["raddr"][:mode_addr_width], core.pins["raddr"])
            NetUtils.connect(core.pins["dout"], mode.ports["dout"][0:mode_data_width])

            mode.commit()

        return multimode.commit()

    @classmethod
    def _get_or_create_multimode_memory_ctrl(cls, context, abstract):
        """Create the design-view controller for a multi-mode memory."""

        name = "fracbramctrl_a{}d{}c{}m{}".format(
                len(abstract.ports["waddr"]),
                len(abstract.ports["din"]),
                abstract.core_addr_width,
                len(abstract.modes))
        if design := context.database.get( (ModuleView.design, name) ):
            return design

        prog_data_width = len(abstract.modes).bit_length()
        modes = {}
        for value, (mode_name, mode) in enumerate(abstract.modes.items(), 1):
            prog_enable = ProgDataValue(value, (0, prog_data_width))
            modes[mode_name] = prog_enable, len(mode.instances["i_ram"].pins["waddr"]) - abstract.core_addr_width

        return context._add_module(Module(name,
            is_cell = True, 
            view = ModuleView.design,
            module_class = ModuleClass.aux,
            verilog_template = "bram/fracbramctrl.tmpl.v",
            addr_width = len(abstract.ports["waddr"]),
            data_width = len(abstract.ports["din"]),
            core_addr_width = abstract.core_addr_width,
            prog_data_width = prog_data_width,
            modes = modes))

    @classmethod
    def _create_multimode_memory_design(cls, context, abstract):
        """Create design-view for a multi-mode memory."""

        ctrl = cls._get_or_create_multimode_memory_ctrl(context, abstract)

        lbdr = context.build_design_view_primitive(abstract.name,
                key = abstract.key,
                core_addr_width = abstract.core_addr_width,
                verilog_template = "bram/fracbram.tmpl.v")
        lbdr.create_prog_port("prog_done", 1,                    PortDirection.input_)
        lbdr.create_prog_port("prog_data", ctrl.prog_data_width, PortDirection.input_)
        lbdr.instantiate(context.database[ModuleView.design, "prga_ram_1r1w_byp"],
                "i_ram",
                verilog_parameters = {
                    "DATA_WIDTH": "DATA_WIDTH",
                    "ADDR_WIDTH": "CORE_ADDR_WIDTH",
                    })
        lbdr.instantiate(ctrl, "i_ctrl")

        for mode_name, (prog_enable, _) in ctrl.modes.items():
            abstract.modes[mode_name].prog_enable = prog_enable

        lbdr.commit()

    @classmethod
    def create_multiplier(cls, context, width_a, width_b = None, *,
            name = None):
        """Create a basic combinational multiplier.

        Args:
            context (`Context`):
            width_a (:obj:`int`): Width of the multiplier/multiplicand
            width_b (:obj:`int`): Width of the other multiplier/multiplicand. Equal to ``width_a`` if not set.

        Keyword Args:
            name (:obj:`str`): Name of the primitive. ``"mul_a{width_a}b{width_b}"`` by default.

        Returns:
            `Module`: User view of the multiplier
        """
        width_b = uno(width_b, width_a)

        name = uno(name, "mul_a{}b{}".format(width_a, width_b))
        ubdr = context.build_primitive(name,
                techmap_template = "mul/techmap.tmpl.v",
                verilog_template = "mul/lib.tmpl.v",
                vpr_model = "m_mul_a{}b{}".format(width_a, width_b),
                parameters = { "SIGNED": 1, },
                prog_parameters = { "SIGNED": ProgDataBitmap( (1, 1) ), },
                prog_enable = ProgDataValue(1, (0, 1)),
                )

        inputs = [
                ubdr.create_input("a", width_a),
                ubdr.create_input("b", width_b),
                ]
        output = ubdr.create_output("x", width_a + width_b)
        for i in inputs:
            ubdr.create_timing_arc(TimingArcType.comb_matrix, i, output)

        return ubdr.commit()

    @classmethod
    def _create_multiplier_design(cls, context, abstract):
        """Create design-view for multipliers."""

        lbdr = context.build_design_view_primitive(abstract.name,
                key = abstract.key,
                verilog_template = "mul/mul.tmpl.v" )
        lbdr.create_prog_port("prog_done", 1, PortDirection.input_)
        lbdr.create_prog_port("prog_data", 2, PortDirection.input_)
        lbdr.commit()

    @classmethod
    def install_design(cls, context):
        """Install the design-view for on-demand modules into ``context``.

        Args:
            context (`Context`):
        """

        # find all abstract-only primitives, and see if we can automatically create design-views for them
        abstracts = []
        for module in context.primitives.values():
            if (not getattr(module, "abstract_only", False)
                    and (ModuleView.design, module.key) not in context.database):
                abstracts.append(module)

        abstract_only = []
        for abstract in abstracts:
            if abstract.primitive_class.is_memory:
                cls._create_memory_design(context, abstract)
            elif (abstract.primitive_class.is_multimode
                    and getattr(abstract, "memory_type", None) == "1r1w_frac"):
                cls._create_multimode_memory_design(context, abstract)
            elif (abstract.primitive_class.is_custom
                    and getattr(abstract, "techmap_template", None) == "mul/techmap.tmpl.v"
                    and getattr(abstract, "verilog_template", None) == "mul/lib.tmpl.v"):
                cls._create_multiplier_design(context, abstract)
            else:
                abstract_only.append(abstract)

        for abstract in abstract_only:
            _logger.warning("No design view available for primitive '{}'".format(abstract.name))
