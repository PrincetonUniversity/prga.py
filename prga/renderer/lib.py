# -*- encoding: ascii -*-

from ..core.common import ModuleView, ModuleClass, PrimitiveClass, PrimitivePortClass, NetClass, IOType
from ..prog import ProgDataBitmap, ProgDataValue
from ..netlist import Module, NetUtils, ModuleUtils, PortDirection, TimingArcType
from ..exception import PRGAInternalError
from ..util import uno

from itertools import product
from math import floor, log2
import re

import logging

_logger = logging.getLogger(__name__)
_reprog_memory_mode = re.compile("^\d+[TGMKx]\d+b$")

__all__ = ['BuiltinCellLibrary']

# ----------------------------------------------------------------------------
# -- Builtin Cell Libraries --------------------------------------------------
# ----------------------------------------------------------------------------
class BuiltinCellLibrary(object):
    """A host class for built-in cells."""

    @classmethod
    def _install_m_adder(cls, context):
        ubdr = context.build_primitive("adder",
                techmap_template = "builtin/adder.techmap.tmpl.v",
                verilog_template = "builtin/adder.lib.tmpl.v",
                vpr_model = "m_adder",
                parameters = { "CIN_MODE": 2, },    # parameter name: bit width
                )
        inputs = [
                ubdr.create_input("a", 1),
                ubdr.create_input("b", 1),
                ubdr.create_input("cin", 1),
                ubdr.create_input("cin_fabric", 1),
                ]
        outputs = [
                ubdr.create_output("cout", 1),
                ubdr.create_output("s", 1),
                ubdr.create_output("cout_fabric", 1),
                ]
        for i, o in product(inputs, outputs):
            ubdr.create_timing_arc(TimingArcType.comb_bitwise, i, o)

        ubdr.commit()

    @classmethod
    def _annotate_m_adder(cls, context):
        adder = context.primitives["adder"]
        adder.prog_parameters = { "CIN_MODE": ProgDataBitmap( (0, 2) ), }

    @classmethod
    def _install_m_dffe(cls, context):
        ubdr = context.build_primitive('dffe',
                techmap_template = "builtin/dffe.techmap.tmpl.v",
                premap_commands = "dffsr2dff; dff2dffe",
                verilog_template = "builtin/dffe.lib.tmpl.v",
                vpr_model = "m_dffe",
                parameters = { "ENABLE_CE": 1, },
                )
        clock = ubdr.create_clock("C")
        for input_ in (
                ubdr.create_input("D", 1),
                ubdr.create_input("E", 1),
                ):
            ubdr.create_timing_arc(TimingArcType.seq_end, clock, input_)
        ubdr.create_timing_arc(TimingArcType.seq_start, clock, ubdr.create_output("Q", 1))

        ubdr.commit()

    @classmethod
    def _install_dffe(cls, context):
        lbdr = context.build_design_view_primitive("dffe", verilog_template = "builtin/dffe.tmpl.v")

        NetUtils.create_timing_arc(TimingArcType.seq_start, lbdr.ports["C"], lbdr.ports["Q"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["C"], lbdr.ports["D"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["C"], lbdr.ports["E"])

        lbdr.create_prog_port("prog_done", 1, PortDirection.input_)
        lbdr.create_prog_port("prog_data", 2, PortDirection.input_)

        lbdr.commit()

        lbdr.counterpart.prog_enable = ProgDataValue(1, (0, 1))
        lbdr.counterpart.prog_parameters = { "ENABLE_CE": ProgDataBitmap( (1, 1) ), }

    @classmethod
    def _install_m_luts(cls, context):
        for i in range(2, 9):
            name = "lut" + str(i)

            # abstract
            umod = context._add_module(Module(name,
                    is_cell = True,
                    view = ModuleView.abstract,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.lut))
            in_ = ModuleUtils.create_port(umod, 'in', i, PortDirection.input_,
                    port_class = PrimitivePortClass.lut_in)
            out = ModuleUtils.create_port(umod, 'out', 1, PortDirection.output,
                    port_class = PrimitivePortClass.lut_out)
            NetUtils.create_timing_arc(TimingArcType.comb_matrix, in_, out)

    @classmethod
    def _install_luts(cls, context):
        for i in range(2, 9):
            name = "lut" + str(i)

            lmod = context._add_module(Module(name,
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.primitive, 
                primitive_class = PrimitiveClass.lut,
                verilog_template = "builtin/lut.tmpl.v"))
            in_ = ModuleUtils.create_port(lmod, 'in', i, PortDirection.input_,
                    net_class = NetClass.user, port_class = PrimitivePortClass.lut_in)
            out = ModuleUtils.create_port(lmod, 'out', 1, PortDirection.output,
                    net_class = NetClass.user, port_class = PrimitivePortClass.lut_out)
            NetUtils.create_timing_arc(TimingArcType.comb_matrix, in_, out)
            ModuleUtils.create_port(lmod, "prog_done", 1,          PortDirection.input_, net_class = NetClass.prog)
            ModuleUtils.create_port(lmod, "prog_data", 2 ** i + 1, PortDirection.input_, net_class = NetClass.prog)

            # mark programming data bitmap
            umod = context.primitives[name]
            umod.prog_enable = ProgDataValue(1, (2 ** i, 1))
            umod.prog_parameters = { "LUT": ProgDataBitmap( (0, 2 ** i) ) }

    @classmethod
    def _install_m_flipflop(cls, context):
        # abstract
        umod = context._add_module(Module("flipflop",
                is_cell = True,
                view = ModuleView.abstract,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.flipflop))
        clk = ModuleUtils.create_port(umod, "clk", 1, PortDirection.input_, is_clock = True,
                port_class = PrimitivePortClass.clock)
        D = ModuleUtils.create_port(umod, "D", 1, PortDirection.input_,
                port_class = PrimitivePortClass.D)
        Q = ModuleUtils.create_port(umod, "Q", 1, PortDirection.output,
                port_class = PrimitivePortClass.Q)
        NetUtils.create_timing_arc(TimingArcType.seq_end, clk, D)
        NetUtils.create_timing_arc(TimingArcType.seq_start, clk, Q)

    @classmethod
    def _install_flipflop(cls, context):
        # design
        lmod = context._add_module(Module("flipflop",
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.primitive,
                primitive_class = PrimitiveClass.flipflop,
                verilog_template = "builtin/flipflop.tmpl.v"))
        clk = ModuleUtils.create_port(lmod, "clk", 1, PortDirection.input_, is_clock = True,
                net_class = NetClass.user, port_class = PrimitivePortClass.clock)
        D = ModuleUtils.create_port(lmod, "D", 1, PortDirection.input_,
                net_class = NetClass.user, port_class = PrimitivePortClass.D)
        Q = ModuleUtils.create_port(lmod, "Q", 1, PortDirection.output,
                net_class = NetClass.user, port_class = PrimitivePortClass.Q)
        NetUtils.create_timing_arc(TimingArcType.seq_end, clk, D)
        NetUtils.create_timing_arc(TimingArcType.seq_start, clk, Q)
        ModuleUtils.create_port(lmod, "prog_done", 1, PortDirection.input_, net_class = NetClass.prog)
        ModuleUtils.create_port(lmod, "prog_data", 1, PortDirection.input_, net_class = NetClass.prog)

        # mark programming data bitmap
        context.primitives["flipflop"].prog_enable = ProgDataValue(1, (0, 1))

    @classmethod
    def _install_m_io(cls, context):
        # register single-mode I/O
        for name in ("inpad", "outpad"):
            # abstract
            umod = context._add_module(Module(name,
                    is_cell = True,
                    view = ModuleView.abstract,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass[name]))
            if name == "inpad":
                ModuleUtils.create_port(umod, "inpad", 1, PortDirection.output)
            else:
                ModuleUtils.create_port(umod, "outpad", 1, PortDirection.input_)

        # register dual-mode I/O
        if True:
            # abstract
            ubdr = context.build_multimode("iopad")
            ubdr.create_input("outpad", 1)
            ubdr.create_output("inpad", 1)

            # abstract modes
            mode_input = ubdr.build_mode("mode_input")
            inst = mode_input.instantiate(
                    context.database[ModuleView.abstract, "inpad"],
                    "i_pad")
            mode_input.connect(inst.pins["inpad"], mode_input.ports["inpad"])
            mode_input.commit()

            mode_output = ubdr.build_mode("mode_output")
            inst = mode_output.instantiate(
                    context.database[ModuleView.abstract, "outpad"],
                    "o_pad")
            mode_output.connect(mode_output.ports["outpad"], inst.pins["outpad"])
            mode_output.commit()

            ubdr.commit()

    @classmethod
    def _install_io(cls, context):
        # register single-mode I/O
        for name in ("inpad", "outpad"):
            # design
            lmod = context._add_module(Module(name,
                    is_cell = True,
                    view = ModuleView.design,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass[name],
                    verilog_template = "builtin/{}.tmpl.v".format(name)))
            if name == "inpad":
                u = ModuleUtils.create_port(lmod, "inpad", 1, PortDirection.output, net_class = NetClass.user)
                l = ModuleUtils.create_port(lmod, "ipin", 1, PortDirection.input_,
                        net_class = NetClass.io, key = IOType.ipin)
                NetUtils.create_timing_arc(TimingArcType.comb_bitwise, l, u)
            else:
                u = ModuleUtils.create_port(lmod, "outpad", 1, PortDirection.input_, net_class = NetClass.user)
                l = ModuleUtils.create_port(lmod, "opin", 1, PortDirection.output,
                        net_class = NetClass.io, key = IOType.opin)
                NetUtils.create_timing_arc(TimingArcType.comb_bitwise, u, l)
            ModuleUtils.create_port(lmod, "prog_done", 1, PortDirection.input_, net_class = NetClass.prog)
            ModuleUtils.create_port(lmod, "prog_data", 1, PortDirection.input_, net_class = NetClass.prog)

            # mark programming data bitmap
            context.primitives[name].prog_enable = ProgDataValue(1, (0, 1))

        # register dual-mode I/O
        if True:
            lbdr = context.build_design_view_primitive("iopad", verilog_template = "builtin/iopad.tmpl.v")
            ipin = ModuleUtils.create_port(lbdr.module, "ipin", 1, PortDirection.input_,
                    net_class = NetClass.io, key = IOType.ipin)
            opin = ModuleUtils.create_port(lbdr.module, "opin", 1, PortDirection.output,
                    net_class = NetClass.io, key = IOType.opin)
            oe = ModuleUtils.create_port(lbdr.module, "oe", 1, PortDirection.output,
                    net_class = NetClass.io, key = IOType.oe)
            NetUtils.create_timing_arc(TimingArcType.comb_bitwise, ipin, lbdr.ports["inpad"])
            NetUtils.create_timing_arc(TimingArcType.comb_bitwise, lbdr.ports["outpad"], opin)
            lbdr.create_prog_port("prog_done", 1, PortDirection.input_)
            lbdr.create_prog_port("prog_data", 2, PortDirection.input_)

            lbdr.commit()

            # mark programming data bitmap
            i = lbdr.counterpart.modes["mode_input"].instances["i_pad"]
            i.prog_enable = ProgDataValue(1, (0, 2))
            i.prog_bitmap = ProgDataBitmap( (0, 2) )

            o = lbdr.counterpart.modes["mode_output"].instances["o_pad"]
            o.prog_enable = ProgDataValue(2, (0, 2))
            o.prog_bitmap = ProgDataBitmap( (0, 2) )

    @classmethod
    def _install_m_fle6(cls, context):
        ubdr = context.build_multimode("fle6")
        ubdr.create_clock("clk")
        ubdr.create_input("in", 6)
        ubdr.create_input("cin", 1)
        ubdr.create_output("out", 2)
        ubdr.create_output("cout", 1)

        # abstract modes
        # mode (1): arith
        if True:
            mode = ubdr.build_mode("arith")
            adder = mode.instantiate(context.primitives["adder"], "i_adder")
            luts = mode.instantiate(context.primitives["lut5"], "i_lut5", 2)
            ffs = mode.instantiate(context.primitives["flipflop"], "i_flipflop", 2)
            mode.connect(mode.ports["cin"], adder.pins["cin"], vpr_pack_patterns = ["carrychain"])
            mode.connect(mode.ports["in"][5], adder.pins["cin_fabric"])
            for i, (p, lut) in enumerate(zip(["a", "b"], luts)):
                mode.connect(mode.ports["in"][4:0], lut.pins["in"])
                # mode.connect(lut.pins["out"], adder.pins[p], vpr_pack_patterns = ["carrychain"])
                mode.connect(lut.pins["out"], adder.pins[p])
            for i, (p, ff) in enumerate(zip(["s", "cout_fabric"], ffs)):
                mode.connect(mode.ports["clk"], ff.pins["clk"])
                # mode.connect(adder.pins[p], ff.pins["D"], vpr_pack_patterns = ["carrychain"])
                mode.connect(adder.pins[p], ff.pins["D"])
                mode.connect(adder.pins[p], mode.ports["out"][i])
                mode.connect(ff.pins["Q"], mode.ports["out"][i])
            mode.connect(adder.pins["cout"], mode.ports["cout"], vpr_pack_patterns = ["carrychain"])
            mode.commit()

        # mode (2): LUT6x1
        if True:
            mode = ubdr.build_mode("lut6x1")
            lut = mode.instantiate(context.primitives["lut6"], "i_lut6")
            ff = mode.instantiate(context.primitives["flipflop"], "i_flipflop")
            mode.connect(mode.ports["clk"], ff.pins["clk"])
            mode.connect(mode.ports["in"], lut.pins["in"])
            mode.connect(lut.pins["out"], ff.pins["D"], vpr_pack_patterns = ["lut6_dff"])
            mode.connect(lut.pins["out"], mode.ports["out"][0])
            mode.connect(ff.pins["Q"], mode.ports["out"][0])
            mode.commit()

        # mode (3): LUT5x2
        if True:
            mode = ubdr.build_mode("lut5x2")
            for i, (lut, ff) in enumerate(zip(
                mode.instantiate(context.primitives["lut5"], "i_lut5", 2),
                mode.instantiate(context.primitives["flipflop"], "i_flipflop", 2)
                )):
                mode.connect(mode.ports["clk"], ff.pins["clk"])
                mode.connect(mode.ports["in"][4:0], lut.pins["in"])
                mode.connect(lut.pins["out"], ff.pins["D"], vpr_pack_patterns = ["lut5_i{}_dff".format(i)])
                mode.connect(lut.pins["out"], mode.ports["out"][i])
                mode.connect(ff.pins["Q"], mode.ports["out"][i])
            mode.commit()

        ubdr.commit()

    @classmethod
    def _install_fle6(cls, context):
        lbdr = context.build_design_view_primitive("fle6", verilog_template = "fle6/fle6.tmpl.v")
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["in"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["cin"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["in"], lbdr.ports["cout"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["cin"], lbdr.ports["cout"])
        NetUtils.create_timing_arc(TimingArcType.seq_start, lbdr.ports["clk"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["clk"], lbdr.ports["in"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["clk"], lbdr.ports["cin"])
        lbdr.create_prog_port("prog_done", 1, PortDirection.input_)
        lbdr.create_prog_port("prog_data", 70, PortDirection.input_)

        lbdr.commit()

        # mark programming data bitmap
        # mode (1): arith
        mode = lbdr.counterpart.modes["arith"]
        mode.prog_enable = ProgDataValue(1, (68, 2))

        adder = mode.instances["i_adder"]
        adder.prog_bitmap = ProgDataBitmap( (64, 2) )

        for i, p in enumerate(["s", "cout_fabric"]):
            conn = NetUtils.get_connection(mode.instances["i_flipflop", i].pins["Q"],
                    mode.ports["out"][i], skip_validations = True)
            conn.prog_enable = ProgDataValue(0, (66 + i, 1))

            conn = NetUtils.get_connection(adder.pins[p], mode.ports["out"][i], skip_validations = True)
            conn.prog_enable = ProgDataValue(1, (66 + i, 1))

        for i in range(2):
            lut = mode.instances["i_lut5", i]
            lut.prog_bitmap = ProgDataBitmap( (32 * i, 32) )
            lut.prog_enable = None

            ff = mode.instances["i_flipflop", i]
            ff.prog_bitmap = None
            ff.prog_enable = None

        # mode (2): lut6x1
        mode = lbdr.counterpart.modes["lut6x1"]
        mode.prog_enable = ProgDataValue(2, (68, 2))

        lut = mode.instances["i_lut6"]
        lut.prog_bitmap = ProgDataBitmap( (0, 64) )
        lut.prog_enable = None

        ff = mode.instances["i_flipflop"]
        ff.prog_bitmap = None
        ff.prog_enable = None

        conn = NetUtils.get_connection(ff.pins["Q"], mode.ports["out"][0], skip_validations = True)
        conn.prog_enable = ProgDataValue(0, (66, 1))

        conn = NetUtils.get_connection(lut.pins["out"], mode.ports["out"][0], skip_validations = True)
        conn.prog_enable = ProgDataValue(1, (66, 1))

        # mode (3): lut5x2
        mode = lbdr.counterpart.modes["lut5x2"]
        mode.prog_enable = ProgDataValue(3, (68, 2))

        for i in range(2):
            lut = mode.instances["i_lut5", i]
            lut.prog_bitmap = ProgDataBitmap( (32 * i, 32) )
            lut.prog_enable = None

            ff = mode.instances["i_flipflop", i]
            ff.prog_bitmap = None
            ff.prog_enable = None

            conn = NetUtils.get_connection(ff.pins["Q"], mode.ports["out"][i], skip_validations = True)
            conn.prog_enable = ProgDataValue(0, (66 + i, 1))

            conn = NetUtils.get_connection(lut.pins["out"], mode.ports["out"][i], skip_validations = True)
            conn.prog_enable = ProgDataValue(1, (66 + i, 1))

    @classmethod
    def _install_m_grady18v0(cls, context):
        # register a abstract-only mux2
        ubdr = context.build_primitive("grady18.mux2",
                verilog_template = "builtin/mux.lib.tmpl.v",
                techmap_template = "grady18/postlut.techmap.tmpl.v",
                techmap_order = -1.,    # post-lutmap techmap
                vpr_model = "m_mux2")
        inputs = [
                ubdr.create_input("i", 2),
                ubdr.create_input("sel", 1),
                ]
        output = ubdr.create_output("o", 1)
        for i in inputs:
            ubdr.create_timing_arc(TimingArcType.comb_matrix, i, output)
        mux2 = ubdr.commit()

        # register a abstract-only multi-mode primitive: "grady18.ble5"
        ubdr = context.build_multimode("grady18.ble5", key = "grady18:v0.ble5")
        ubdr.create_clock("clk")
        ubdr.create_input("in", 5)
        ubdr.create_input("cin", 1)
        ubdr.create_output("out", 1)
        ubdr.create_output("cout", 1)
        ubdr.create_output("cout_fabric", 1)

        # abstract modes
        # mode (1): arith
        if True:
            mode = ubdr.build_mode("arith")
            adder = mode.instantiate(context.primitives["adder"], "i_adder")
            luts = mode.instantiate(context.primitives["lut4"], "i_lut4", 2)
            ff = mode.instantiate(context.primitives["flipflop"], "i_flipflop")
            mode.connect(mode.ports["clk"], ff.pins["clk"])
            mode.connect(mode.ports["cin"], adder.pins["cin"], vpr_pack_patterns = ["carrychain"])
            mode.connect(mode.ports["in"][4], adder.pins["cin_fabric"])
            for i, (p, lut) in enumerate(zip(["a", "b"], luts)):
                mode.connect(mode.ports["in"][3:0], lut.pins["in"])
                # mode.connect(lut.pins["out"], adder.pins[p], vpr_pack_patterns = ["carrychain"])
                mode.connect(lut.pins["out"], adder.pins[p])
            mode.connect(adder.pins["s"], ff.pins["D"], vpr_pack_patterns = ["carrychain"])
            mode.connect(adder.pins["s"], mode.ports["out"])
            mode.connect(ff.pins["Q"], mode.ports["out"])
            mode.connect(adder.pins["cout"], mode.ports["cout"], vpr_pack_patterns = ["carrychain"])
            mode.connect(adder.pins["cout_fabric"], mode.ports["cout_fabric"])
            mode.commit()

        # mode (2): lut5
        if True:
            mode = ubdr.build_mode("lut5")
            lut = mode.instantiate(context.primitives["lut5"], "i_lut5")
            ff = mode.instantiate(context.primitives["flipflop"], "i_flipflop")
            mode.connect(mode.ports["clk"], ff.pins["clk"])
            mode.connect(mode.ports["in"], lut.pins["in"])
            mode.connect(lut.pins["out"], ff.pins["D"], vpr_pack_patterns = ["lut5_dff"])
            mode.connect(lut.pins["out"], mode.ports["out"])
            mode.connect(ff.pins["Q"], mode.ports["out"])
            mode.commit()

        ble5 = ubdr.commit()

        # build FLE8
        ubdr = context.build_multimode("grady18", emulate_luts = (6, ), key = "grady18:v0")
        ubdr.create_clock("clk")
        ubdr.create_input("in", 8)
        ubdr.create_input("cin", 1)
        ubdr.create_output("out", 2)
        ubdr.create_output("cout", 1)
        ubdr.create_output("cout_fabric", 2)

        # abstract modes
        # mode (1): ble5x2
        if True:
            mode = ubdr.build_mode("ble5x2")
            ble5s = mode.instantiate(ble5, "i_ble5", 2)
            for i, inst in enumerate(ble5s):
                mode.connect(mode.ports["clk"], inst.pins["clk"])
                mode.connect(mode.ports["in"][6], inst.pins["in"][4])
                mode.connect(inst.pins["out"], mode.ports["out"][i])
                mode.connect(inst.pins["cout_fabric"], mode.ports["cout_fabric"][i])
            mode.connect(mode.ports["in"][3:0], ble5s[0].pins["in"][3:0])
            mode.connect(mode.ports["cin"], ble5s[0].pins["cin"], vpr_pack_patterns = ["carrychain"])
            mode.connect(mode.ports["in"][5:4], ble5s[1].pins["in"][3:2])
            mode.connect(mode.ports["in"][1:0], ble5s[1].pins["in"][1:0])
            mode.connect(ble5s[0].pins["cout"], ble5s[1].pins["cin"], vpr_pack_patterns = ["carrychain"])
            mode.connect(ble5s[1].pins["cout"], mode.ports["cout"], vpr_pack_patterns = ["carrychain"])
            mode.commit()

        # mode (2): lut6x1
        if True:
            mode = ubdr.build_mode("lut6x1")
            mux = mode.instantiate(context.primitives["grady18.mux2"], "i_mux2") 
            mode.connect(mode.ports["in"][7], mux.pins["sel"])
            for i, lut in enumerate(mode.instantiate(context.primitives["lut5"], "i_lut5", 2)):
                mode.connect(mode.ports["in"][0:2],                 lut.pins["in"][0:2])
                mode.connect(mode.ports["in"][2 + 2 * i:4 + 2 * i], lut.pins["in"][2:4])
                mode.connect(mode.ports["in"][6],                   lut.pins["in"][4])
                mode.connect(lut.pins["out"], mux.pins["i"][i], vpr_pack_patterns = ["lut6"])
            ff = mode.instantiate(context.primitives["flipflop"], "i_flipflop")
            mode.connect(mux.pins["o"], ff.pins["D"])
            mode.connect(mode.ports["clk"], ff.pins["clk"])
            mode.connect(mux.pins["o"], mode.ports["out"][0])
            mode.connect(ff.pins["Q"],  mode.ports["out"][0])
            mode.commit()

        ubdr.commit()

    @classmethod
    def _install_grady18v0(cls, context):
        lbdr = context.build_design_view_primitive("grady18", key = "grady18:v0",
                verilog_template = "grady18/grady18.tmpl.v")
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["in"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["cin"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["in"], lbdr.ports["cout"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["cin"], lbdr.ports["cout"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["in"], lbdr.ports["cout_fabric"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["cin"], lbdr.ports["cout_fabric"])
        NetUtils.create_timing_arc(TimingArcType.seq_start, lbdr.ports["clk"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["clk"], lbdr.ports["in"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["clk"], lbdr.ports["cin"])
        lbdr.create_prog_port("prog_done", 1, PortDirection.input_)
        lbdr.create_prog_port("prog_data", 74, PortDirection.input_)

        lbdr.commit()

        # mark programming data bitmap
        # BLE5
        ble5 = context.primitives["grady18:v0.ble5"]

        # mode (1): arith
        mode = ble5.modes["arith"]
        mode.prog_enable = ProgDataValue(1, (34, 2))

        adder = mode.instances["i_adder"]
        adder.prog_bitmap = ProgDataBitmap( (32, 2) )

        conn = NetUtils.get_connection(adder.pins["s"], mode.ports["out"], skip_validations = True)
        conn.prog_enable = ProgDataValue(1, (36, 1))

        ff = mode.instances["i_flipflop"]
        ff.prog_bitmap = None
        ff.prog_enable = None

        conn = NetUtils.get_connection(ff.pins["Q"], mode.ports["out"], skip_validations = True)
        conn.prog_enable = ProgDataValue(0, (36, 1))

        for i in range(2):
            lut = mode.instances["i_lut4", i]
            lut.prog_bitmap = ProgDataBitmap( (16 * i, 16) )
            lut.prog_enable = None

        # mode (2): lut5
        mode = ble5.modes["lut5"]
        mode.prog_enable = ProgDataValue(2, (34, 2))

        lut = mode.instances["i_lut5"]
        lut.prog_bitmap = ProgDataBitmap( (0, 32) )
        lut.prog_enable = None

        conn = NetUtils.get_connection(lut.pins["out"], mode.ports["out"], skip_validations = True)
        conn.prog_enable = ProgDataValue(1, (36, 1))

        ff = mode.instances["i_flipflop"]
        ff.prog_bitmap = None
        ff.prog_enable = None

        conn = NetUtils.get_connection(ff.pins["Q"], mode.ports["out"], skip_validations = True)
        conn.prog_enable = ProgDataValue(0, (36, 1))

        # FLE8
        # mode (1): ble5x2
        mode = lbdr.counterpart.modes["ble5x2"]
        mode.prog_enable = None

        for i in range(2):
            inst = mode.instances["i_ble5", i]
            inst.prog_bitmap = ProgDataBitmap( (i * 37, 37) )

        # # mode (2): lut6
        mode = lbdr.counterpart.modes["lut6x1"]
        mode.prog_enable = ProgDataValue(0xf, ((34, 2), (71, 2)))

        for i in range(2):
            lut = mode.instances["i_lut5", i]
            lut.prog_bitmap = ProgDataBitmap( (37 * i, 32) )
            lut.prog_enable = None

        conn = NetUtils.get_connection(mode.instances["i_mux2"].pins["o"], mode.ports["out"][0])
        conn.prog_enable = ProgDataValue(1, (36, 1))

        ff = mode.instances["i_flipflop"]
        ff.prog_bitmap = None
        ff.prog_enable = None

        conn = NetUtils.get_connection(ff.pins["Q"], mode.ports["out"][0])
        conn.prog_enable = ProgDataValue(0, (36, 1))

    @classmethod
    def _install_m_grady18(cls, context):
        # register a abstract-only multi-mode primitive: "grady18.ble5"
        ubdr = context.build_multimode("grady18.ble5")
        ubdr.create_clock("clk")
        ubdr.create_input("in", 5)
        ubdr.create_input("cin", 1)
        ubdr.create_input("ce", 1)
        ubdr.create_output("out", 1)
        ubdr.create_output("cout", 1)

        # abstract modes
        # mode (1): arith
        if True:
            mode = ubdr.build_mode("arith")
            adder = mode.instantiate(context.primitives["adder"], "i_adder")
            luts = mode.instantiate(context.primitives["lut4"], "i_lut4", 2)
            ff = mode.instantiate(context.primitives["dffe"], "i_flipflop")
            mode.connect(mode.ports["clk"], ff.pins["C"])
            mode.connect(mode.ports["ce"], ff.pins["E"])
            mode.connect(mode.ports["cin"], adder.pins["cin"], vpr_pack_patterns = ["carrychain"])
            mode.connect(mode.ports["in"][4], adder.pins["cin_fabric"])
            for i, (p, lut) in enumerate(zip(["a", "b"], luts)):
                mode.connect(mode.ports["in"][3:0], lut.pins["in"])
                # mode.connect(lut.pins["out"], adder.pins[p], vpr_pack_patterns = ["carrychain"])
                mode.connect(lut.pins["out"], adder.pins[p])
            mode.connect(adder.pins["s"], ff.pins["D"], vpr_pack_patterns = ["carrychain"])
            mode.connect(adder.pins["s"], mode.ports["out"])
            mode.connect(ff.pins["Q"], mode.ports["out"])
            mode.connect(adder.pins["cout"], mode.ports["cout"], vpr_pack_patterns = ["carrychain"])
            mode.commit()

        # mode (2): lut5
        if True:
            mode = ubdr.build_mode("lut5")
            lut = mode.instantiate(context.primitives["lut5"], "i_lut5")
            ff = mode.instantiate(context.primitives["dffe"], "i_flipflop")
            mode.connect(mode.ports["clk"], ff.pins["C"])
            mode.connect(mode.ports["ce"], ff.pins["E"])
            mode.connect(mode.ports["in"], lut.pins["in"])
            mode.connect(lut.pins["out"], ff.pins["D"], vpr_pack_patterns = ["lut5_dff"])
            mode.connect(lut.pins["out"], mode.ports["out"])
            mode.connect(ff.pins["Q"], mode.ports["out"])
            mode.commit()

        ble5 = ubdr.commit()

        # build FLE8
        ubdr = context.build_multimode("grady18", emulate_luts = (6, ))
        ubdr.create_clock("clk")
        ubdr.create_input("in", 8)
        ubdr.create_input("ce", 1)
        ubdr.create_input("cin", 1)
        ubdr.create_output("out", 2)
        ubdr.create_output("cout", 1)

        # abstract modes
        # mode (1): ble5x2
        if True:
            mode = ubdr.build_mode("ble5x2")
            ble5s = mode.instantiate(ble5, "i_ble5", 2)
            for i, inst in enumerate(ble5s):
                mode.connect(mode.ports["clk"], inst.pins["clk"])
                mode.connect(mode.ports["ce"], inst.pins["ce"])
                mode.connect(mode.ports["in"][6], inst.pins["in"][4])
                mode.connect(inst.pins["out"], mode.ports["out"][i])
            mode.connect(mode.ports["in"][3:0], ble5s[0].pins["in"][3:0])
            mode.connect(mode.ports["cin"], ble5s[0].pins["cin"], vpr_pack_patterns = ["carrychain"])
            mode.connect(mode.ports["in"][5:4], ble5s[1].pins["in"][3:2])
            mode.connect(mode.ports["in"][1:0], ble5s[1].pins["in"][1:0])
            mode.connect(ble5s[0].pins["cout"], ble5s[1].pins["cin"], vpr_pack_patterns = ["carrychain"])
            mode.connect(ble5s[1].pins["cout"], mode.ports["cout"], vpr_pack_patterns = ["carrychain"])
            mode.commit()

        # mode (2): lut6x1
        if True:
            mode = ubdr.build_mode("lut6x1")
            mux = mode.instantiate(context.primitives["grady18.mux2"], "i_mux2") 
            mode.connect(mode.ports["in"][7], mux.pins["sel"])
            for i, lut in enumerate(mode.instantiate(context.primitives["lut5"], "i_lut5", 2)):
                mode.connect(mode.ports["in"][0:2],                 lut.pins["in"][0:2])
                mode.connect(mode.ports["in"][2 + 2 * i:4 + 2 * i], lut.pins["in"][2:4])
                mode.connect(mode.ports["in"][6],                   lut.pins["in"][4])
                mode.connect(lut.pins["out"], mux.pins["i"][i], vpr_pack_patterns = ["lut6"])
            ff = mode.instantiate(context.primitives["dffe"], "i_flipflop")
            mode.connect(mux.pins["o"], ff.pins["D"])
            mode.connect(mode.ports["clk"], ff.pins["C"])
            mode.connect(mode.ports["ce"], ff.pins["E"])
            mode.connect(mux.pins["o"], mode.ports["out"][0])
            mode.connect(ff.pins["Q"],  mode.ports["out"][0])
            mode.commit()

        ubdr.commit()

    @classmethod
    def _install_grady18(cls, context):
        lbdr = context.build_design_view_primitive("grady18", verilog_template = "grady18/grady18v2.tmpl.v")
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["in"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["cin"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["in"], lbdr.ports["cout"])
        NetUtils.create_timing_arc(TimingArcType.comb_matrix, lbdr.ports["cin"], lbdr.ports["cout"])
        NetUtils.create_timing_arc(TimingArcType.seq_start, lbdr.ports["clk"], lbdr.ports["out"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["clk"], lbdr.ports["in"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["clk"], lbdr.ports["ce"])
        NetUtils.create_timing_arc(TimingArcType.seq_end, lbdr.ports["clk"], lbdr.ports["cin"])
        lbdr.create_prog_port("prog_done", 1, PortDirection.input_)
        lbdr.create_prog_port("prog_data", 76, PortDirection.input_)

        lbdr.commit()

        # mark programming data bitmap
        # BLE5
        ble5 = context.primitives["grady18.ble5"]

        # mode (1): arith
        mode = ble5.modes["arith"]
        mode.prog_enable = ProgDataValue(1, (34, 2))

        adder = mode.instances["i_adder"]
        adder.prog_bitmap = ProgDataBitmap( (32, 2) )

        conn = NetUtils.get_connection(adder.pins["s"], mode.ports["out"], skip_validations = True)
        conn.prog_enable = ProgDataValue(1, (36, 1))

        ff = mode.instances["i_flipflop"]
        ff.prog_bitmap = ProgDataBitmap( (37, 1) )
        ff.prog_enable = None
        ff.prog_parameters = { "ENABLE_CE": ProgDataBitmap( (0, 1) ), }

        conn = NetUtils.get_connection(ff.pins["Q"], mode.ports["out"], skip_validations = True)
        conn.prog_enable = ProgDataValue(0, (36, 1))

        for i in range(2):
            lut = mode.instances["i_lut4", i]
            lut.prog_bitmap = ProgDataBitmap( (16 * i, 16) )
            lut.prog_enable = None

        # mode (2): lut5
        mode = ble5.modes["lut5"]
        mode.prog_enable = ProgDataValue(2, (34, 2))

        lut = mode.instances["i_lut5"]
        lut.prog_bitmap = ProgDataBitmap( (0, 32) )
        lut.prog_enable = None

        conn = NetUtils.get_connection(lut.pins["out"], mode.ports["out"], skip_validations = True)
        conn.prog_enable = ProgDataValue(1, (36, 1))

        ff = mode.instances["i_flipflop"]
        ff.prog_bitmap = ProgDataBitmap( (37, 1) )
        ff.prog_enable = None
        ff.prog_parameters = { "ENABLE_CE": ProgDataBitmap( (0, 1) ), }

        conn = NetUtils.get_connection(ff.pins["Q"], mode.ports["out"], skip_validations = True)
        conn.prog_enable = ProgDataValue(0, (36, 1))

        # FLE8
        # mode (1): ble5x2
        mode = lbdr.counterpart.modes["ble5x2"]
        mode.prog_enable = None

        for i in range(2):
            inst = mode.instances["i_ble5", i]
            inst.prog_bitmap = ProgDataBitmap( (i * 38, 38) )

        # # mode (2): lut6
        mode = lbdr.counterpart.modes["lut6x1"]
        mode.prog_enable = ProgDataValue(0xf, ((34, 2), (72, 2)))

        for i in range(2):
            lut = mode.instances["i_lut5", i]
            lut.prog_bitmap = ProgDataBitmap( (38 * i, 32) )
            lut.prog_enable = None

        conn = NetUtils.get_connection(mode.instances["i_mux2"].pins["o"], mode.ports["out"][0])
        conn.prog_enable = ProgDataValue(1, (36, 1))

        ff = mode.instances["i_flipflop"]
        ff.prog_bitmap = ProgDataBitmap( (37, 1) )
        ff.prog_enable = None
        ff.prog_parameters = { "ENABLE_CE": ProgDataBitmap( (0, 1) ), }

        conn = NetUtils.get_connection(ff.pins["Q"], mode.ports["out"][0])
        conn.prog_enable = ProgDataValue(0, (36, 1))

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
            bdr = context.build_primitive(name = name + "_init",
                    vpr_model = name + "_init",
                    primitive_class = PrimitiveClass.blackbox_memory,
                    verilog_template = "bram/init/1r1w.lib.tmpl.v",
                    bram_rule_template = "bram/init/1r1w.tmpl.rule",
                    techmap_template = "bram/init/1r1w.techmap.tmpl.v",
                    parameters = {
                        "INIT": data_width << addr_width,
                        })
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
            bdr = context.build_multimode(name, memory_type = memory_type)
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
                    "i_ram")
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
            addr_width = None, name = None):
        """Create a multi-mode RAM.

        Args:
            context (`Context`):
            core_addr_width (:obj:`int`): The address width of the single-mode, 1R1W RAM core behind the multi-mode
                logic
            data_width (:obj:`int`): The data width of the single-mode, 1R1W RAM core behind the multi-mode logic

        Keyword Args:
            name (:obj:`str`): Name of the multi-mode primitive. ``"fracram_a{addr_width}d{data_width}"`` by default.
            addr_width (:obj:`int`): The maximum address width. See notes for more information

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
        default_addr_width = core_addr_width + int(floor(log2(data_width)))
        addr_width = uno(addr_width, default_addr_width)

        if not (core_addr_width <= addr_width <= default_addr_width):
            raise PRGAInternalError("Invalid addr_width ({}). Valid numbers {} <= addr_width <= {}"
                    .format(addr_width, core_addr_width, default_addr_width))

        name = uno(name, "fracram_a{}d{}".format(addr_width, data_width))
        multimode = context.build_multimode(name,
                core_addr_width = core_addr_width,
                memory_type = "1r1w_frac")
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
                        techmap_order = 1. + 1 / float(mode_addr_width)),
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
            prog_enable = mode.prog_enable = ProgDataValue(value, (0, prog_data_width))
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
                parameters = {"DATA_WIDTH": "DATA_WIDTH", "ADDR_WIDTH": "CORE_ADDR_WIDTH"})
        lbdr.instantiate(ctrl, "i_ctrl")

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
    def install_abstract(cls, context):
        """Install the built-in abstract-view modules into ``context``.

        Args:
            context (`Context`):
        """

        # m_adder
        cls._install_m_adder(context)

        # m_dffe
        cls._install_m_dffe(context)

        # luts
        cls._install_m_luts(context)

        # D flip-flop
        cls._install_m_flipflop(context)

        # I/O
        cls._install_m_io(context)

        # FLE6
        cls._install_m_fle6(context)

        # grady'18
        cls._install_m_grady18v0(context)
        cls._install_m_grady18(context)

    @classmethod
    def install_design(cls, context):
        """Install the built-in design-view modules into ``context``.

        Args:
            context (`Context`):
        """

        # adder
        cls._annotate_m_adder(context)

        # dffe
        cls._install_dffe(context)

        # luts
        cls._install_luts(context)

        # basic flip-flop
        cls._install_flipflop(context)

        # IOs
        cls._install_io(context)

        # FLE6
        cls._install_fle6(context)

        # grady'18 FLE8, v0
        cls._install_grady18v0(context)

        # grady'18 FLE8, v1 (default)
        cls._install_grady18(context)

        # find all abstract-only primitives, and see if we can automatically create design-views for them
        abstracts = []
        for module in context.primitives.values():
            if (ModuleView.design, module.key) not in context.database:
                abstracts.append(module)

        abstract_only = []
        for abstract in abstracts:
            if abstract.primitive_class.is_memory:
                cls._create_memory_design(context, abstract)
            elif (abstract.primitive_class.is_multimode
                    and getattr(abstract, "memory_type", None) == "1r1w_frac"):
                    # and all(_reprog_memory_mode.match(mode_name) for mode_name in abstract.modes)):
                cls._create_multimode_memory_design(context, abstract)
            elif (abstract.primitive_class.is_custom
                    and getattr(abstract, "techmap_template", None) == "mul/techmap.tmpl.v"
                    and getattr(abstract, "verilog_template", None) == "mul/lib.tmpl.v"):
                cls._create_multiplier_design(context, abstract)
            else:
                abstract_only.append(abstract)

        for abstract in abstract_only:
            _logger.warning("No design view available for primitive '{}'".format(abstract.name))

    @classmethod
    def install_stdlib(cls, context):
        """Install standard PRGA designs/headers into ``context``.

        Args:
            context (`Context`):
        """
        # add headers
        context.add_verilog_header("prga_utils.vh", "stdlib/include/prga_utils.tmpl.vh")
        context.add_verilog_header("prga_axi4.vh", "stdlib/include/prga_axi4.tmpl.vh")

        # register simple buffers
        for name in ("prga_simple_buf", "prga_simple_bufr", "prga_simple_bufe", "prga_simple_bufre"):
            buf = context._add_module(Module(name,
                    is_cell = True,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "stdlib/{}.v".format(name)))
            ModuleUtils.create_port(buf, "C", 1, PortDirection.input_, is_clock = True)
            if name in ("prga_simple_bufr", "prga_simple_bufre"):
                ModuleUtils.create_port(buf, "R", 1, PortDirection.input_)
            if name in ("prga_simple_bufe", "prga_simple_bufre"):
                ModuleUtils.create_port(buf, "E", 1, PortDirection.input_)
            ModuleUtils.create_port(buf, "D", 1, PortDirection.input_)
            ModuleUtils.create_port(buf, "Q", 1, PortDirection.output)

        # register auxiliary designs
        for d in ("prga_ram_1r1w", "prga_ram_1r1w_byp", "prga_fifo", "prga_fifo_resizer", "prga_fifo_lookahead_buffer",
                "prga_fifo_adapter", "prga_byteaddressable_reg", "prga_tokenfifo", "prga_valrdy_buf"):
            context._add_module(Module(d,
                    is_cell = True,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "stdlib/{}.v".format(d)))
        for d in ("prga_ram_1r1w_dc", "prga_async_fifo", "prga_async_tokenfifo", "prga_clkdiv",
                "prga_valrdy_cdc", "prga_sync_basic", "prga_async_fifo_ptr"):
            context._add_module(Module(d,
                    is_cell = True,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "cdclib/{}.v".format(d)))
        # CDC v2
        for d in ("prga_async_fifo", ):
            context._add_module(Module(d,
                    is_cell = True,
                    key = "prga_async_fifo:v2",
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "cdclib/{}.v2.v".format(d)))

        # module dependencies
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_ram_1r1w_byp"],
                context.database[ModuleView.design, "prga_ram_1r1w"], "i_ram")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fifo"],
                context.database[ModuleView.design, "prga_ram_1r1w"], "ram")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fifo"],
                context.database[ModuleView.design, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fifo_resizer"],
                context.database[ModuleView.design, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fifo_adapter"],
                context.database[ModuleView.design, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_async_fifo"],
                context.database[ModuleView.design, "prga_ram_1r1w_dc"], "ram")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_async_fifo"],
                context.database[ModuleView.design, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_async_fifo_ptr"],
                context.database[ModuleView.design, "prga_sync_basic"], "prga_sync_basic")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_async_fifo:v2"],
                context.database[ModuleView.design, "prga_ram_1r1w_dc"], "prga_ram_1r1w_dc")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_async_fifo:v2"],
                context.database[ModuleView.design, "prga_async_fifo_ptr"], "prga_async_fifo_ptr")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_async_fifo:v2"],
                context.database[ModuleView.design, "prga_fifo_lookahead_buffer"], "prga_fifo_lookahead_buffer")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_valrdy_cdc"],
                context.database[ModuleView.design, "prga_async_fifo:v2"], "prga_async_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_valrdy_cdc"],
                context.database[ModuleView.design, "prga_fifo_resizer"], "prga_fifo_resizer")

        # header dependencies
        context.database[ModuleView.design, "prga_fifo_resizer"].verilog_dep_headers = ("prga_utils.vh", )
