# -*- encoding: ascii -*-

from ..core.common import ModuleView, ModuleClass, PrimitiveClass, PrimitivePortClass, NetClass, IOType
from ..netlist import Module, NetUtils, ModuleUtils, PortDirection, TimingArcType

# ----------------------------------------------------------------------------
# -- Builtin Cell Libraries --------------------------------------------------
# ----------------------------------------------------------------------------
class BuiltinCellLibrary(object):
    """A host class for built-in cells."""

    @classmethod
    def register(cls, context, dont_add_logical_primitives = tuple()):
        """Register designs shipped with PRGA into ``context`` database.

        Args:
            context (`Context`):
        """
        if not isinstance(dont_add_logical_primitives, set):
            dont_add_logical_primitives = set(iter(dont_add_logical_primitives))

        # register built-in primitives: LUTs
        for i in range(2, 9):
            name = "lut" + str(i)

            # user
            umod = context._database[ModuleView.user, name] = Module(name,
                    is_cell = True,
                    view = ModuleView.user,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.lut)
            in_ = ModuleUtils.create_port(umod, 'in', i, PortDirection.input_,
                    port_class = PrimitivePortClass.lut_in)
            out = ModuleUtils.create_port(umod, 'out', 1, PortDirection.output,
                    port_class = PrimitivePortClass.lut_out)
            NetUtils.create_timing_arc(TimingArcType.comb_matrix, in_, out)

            # logical
            if name not in dont_add_logical_primitives:
                lmod = context._database[ModuleView.logical, name] = Module(name,
                        is_cell = True,
                        view = ModuleView.logical,
                        module_class = ModuleClass.primitive, 
                        primitive_class = PrimitiveClass.lut,
                        verilog_template = "builtin/lut.tmpl.v")
                in_ = ModuleUtils.create_port(lmod, 'in', i, PortDirection.input_,
                        net_class = NetClass.user, port_class = PrimitivePortClass.lut_in)
                out = ModuleUtils.create_port(lmod, 'out', 1, PortDirection.output,
                        net_class = NetClass.user, port_class = PrimitivePortClass.lut_out)
                NetUtils.create_timing_arc(TimingArcType.comb_matrix, in_, out)
                ModuleUtils.create_port(lmod, "prog_done", 1,          PortDirection.input_, net_class = NetClass.prog)
                ModuleUtils.create_port(lmod, "prog_data", 2 ** i + 1, PortDirection.input_, net_class = NetClass.prog)

                # mark programming data bitmap
                umod.prog_data_map = {
                        "$lut":     (None, 0, 2 ** i),  # value, base, length
                        "$enable":  (1, 2 ** i, 1),     # value, base, length
                        }

        # register flipflops
        if True:
            name = "flipflop"

            # user
            umod = context._database[ModuleView.user, name] = Module(name,
                    is_cell = True,
                    view = ModuleView.user,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.flipflop)
            clk = ModuleUtils.create_port(umod, "clk", 1, PortDirection.input_, is_clock = True,
                    port_class = PrimitivePortClass.clock)
            D = ModuleUtils.create_port(umod, "D", 1, PortDirection.input_,
                    port_class = PrimitivePortClass.D)
            Q = ModuleUtils.create_port(umod, "Q", 1, PortDirection.output,
                    port_class = PrimitivePortClass.Q)
            NetUtils.create_timing_arc(TimingArcType.seq_end, clk, D)
            NetUtils.create_timing_arc(TimingArcType.seq_start, clk, Q)

            # logical
            if name not in dont_add_logical_primitives:
                lmod = context._database[ModuleView.logical, name] = Module(name,
                        is_cell = True,
                        view = ModuleView.logical,
                        module_class = ModuleClass.primitive,
                        primitive_class = PrimitiveClass.flipflop,
                        verilog_template = "builtin/flipflop.tmpl.v")
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
                umod.prog_data_map = {
                        "$enable":  (1, 0, 1),          # value, base, length
                        }

        # register single-mode I/O
        for name in ("inpad", "outpad"):
            # user
            umod = context._database[ModuleView.user, name] = Module(name,
                    is_cell = True,
                    view = ModuleView.user,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass[name])
            if name == "inpad":
                ModuleUtils.create_port(umod, "inpad", 1, PortDirection.output)
            else:
                ModuleUtils.create_port(umod, "outpad", 1, PortDirection.input_)

            # logical
            if name not in dont_add_logical_primitives:
                lmod = context._database[ModuleView.logical, name] = Module(name,
                        is_cell = True,
                        view = ModuleView.logical,
                        module_class = ModuleClass.primitive,
                        primitive_class = PrimitiveClass[name],
                        verilog_template = "builtin/{}.tmpl.v".format(name))
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
                umod.prog_data_map = {
                        "$enable": (1, 0, 1),           # value, base, length
                        }

        # register dual-mode I/O
        if True:
            # user
            ubdr = context.build_multimode("iopad")
            ubdr.create_input("outpad", 1)
            ubdr.create_output("inpad", 1)

            # user modes
            mode_input = ubdr.build_mode("mode_input")
            inst = mode_input.instantiate(
                    context.database[ModuleView.user, "inpad"],
                    "i_pad")
            mode_input.connect(inst.pins["inpad"], mode_input.ports["inpad"])
            mode_input.commit()

            mode_output = ubdr.build_mode("mode_output")
            inst = mode_output.instantiate(
                    context.database[ModuleView.user, "outpad"],
                    "o_pad")
            mode_output.connect(mode_output.ports["outpad"], inst.pins["outpad"])
            mode_output.commit()

            # logical
            if name not in dont_add_logical_primitives:
                lbdr = ubdr.build_logical_counterpart(verilog_template = "builtin/iopad.tmpl.v")
                ipin = ModuleUtils.create_port(lbdr.module, "ipin", 1, PortDirection.input_,
                        net_class = NetClass.io, key = IOType.ipin)
                opin = ModuleUtils.create_port(lbdr.module, "opin", 1, PortDirection.output,
                        net_class = NetClass.io, key = IOType.opin)
                oe = ModuleUtils.create_port(lbdr.module, "oe", 1, PortDirection.output,
                        net_class = NetClass.io, key = IOType.oe)
                NetUtils.create_timing_arc(TimingArcType.comb_bitwise, ipin, lbdr.ports["inpad"])
                NetUtils.create_timing_arc(TimingArcType.comb_bitwise, lbdr.ports["outpad"], opin)
                lbdr.create_prog_port("prog_done", 1, PortDirection.input_, net_class = NetClass.prog)
                lbdr.create_prog_port("prog_data", 2, PortDirection.input_, net_class = NetClass.prog)

                lbdr.commit()

                # mark programming data bitmap
                ubdr.module.modes["mode_input"].instances["i_pad"].prog_data_map = {
                        "$reduce": 0,                   # merge into parent bitmap
                        "$enable":  (1, 0, 2),          # value, base, length
                        }
                ubdr.module.modes["mode_output"].instances["o_pad"].prog_data_map = {
                        "$reduce": 0,                   # merge into parent bitmap
                        "$enable":  (2, 0, 2),          # value, base, length
                        }
            else:
                ubdr.commit()

        # register simple buffers
        for name in ("prga_simple_buf", "prga_simple_bufr", "prga_simple_bufe", "prga_simple_bufre"):
            if name in dont_add_logical_primitives:
                continue
            buf = context._database[ModuleView.logical, name] = Module(name,
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "stdlib/{}.v".format(name))
            ModuleUtils.create_port(buf, "C", 1, PortDirection.input_, is_clock = True)
            if name in ("prga_simple_bufr", "prga_simple_bufre"):
                ModuleUtils.create_port(buf, "R", 1, PortDirection.input_)
            if name in ("prga_simple_bufe", "prga_simple_bufre"):
                ModuleUtils.create_port(buf, "E", 1, PortDirection.input_)
            ModuleUtils.create_port(buf, "D", 1, PortDirection.input_)
            ModuleUtils.create_port(buf, "Q", 1, PortDirection.output)

        # register auxiliary designs
        for d in ("prga_ram_1r1w", "prga_fifo", "prga_fifo_resizer", "prga_fifo_lookahead_buffer",
                "prga_fifo_adapter", "prga_byteaddressable_reg", "prga_tokenfifo", "prga_valrdy_buf"):
            context._database[ModuleView.logical, d] = Module(d,
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "stdlib/{}.v".format(d))
        for d in ("prga_ram_1r1w_dc", "prga_async_fifo", "prga_async_tokenfifo", "prga_clkdiv"):
            context._database[ModuleView.logical, d] = Module(d,
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "cdclib/{}.v".format(d))

        # module dependencies
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_fifo"],
                context._database[ModuleView.logical, "prga_ram_1r1w"], "ram")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_fifo"],
                context._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_fifo_resizer"],
                context._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_fifo_adapter"],
                context._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_async_fifo"],
                context._database[ModuleView.logical, "prga_ram_1r1w_dc"], "ram")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_async_fifo"],
                context._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")

        # add headers
        context._add_verilog_header("prga_utils.vh", "stdlib/include/prga_utils.tmpl.vh")
