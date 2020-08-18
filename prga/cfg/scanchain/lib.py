# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...core.common import NetClass, ModuleClass, ModuleView, IOType, PrimitiveClass, PrimitivePortClass
from ...core.context import Context
from ...netlist import TimingArcType, PortDirection, Module, ModuleUtils, NetUtils
from ...passes.base import AbstractPass
from ...passes.translation import AbstractSwitchDatabase
# from ...passes.vpr import FASMDelegate
from ...renderer import FileRenderer
from ...util import Object, uno
from ...exception import PRGAInternalError, PRGAAPIError

import os
from collections import namedtuple
from itertools import chain

import logging
_logger = logging.getLogger(__name__)

__all__ = ['Scanchain']

ADDITIONAL_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- Switch Database ---------------------------------------------------------
# ----------------------------------------------------------------------------
class ScanchainSwitchDatabase(AbstractSwitchDatabase):
    """Switch database for scanchain configuration circuitry.
    
    Args:
        context (`Context`):
        cfg_width (:obj:`int`): Width of the scanchain
        entry (`Scanchain` or `Pktchain`): Provided by the caller of the constructor
    """

    __slots__ = ["context", "cfg_width", "entry"]
    def __init__(self, context, cfg_width, entry):
        self.context = context
        self.cfg_width = cfg_width
        self.entry = entry

    def get_switch(self, width, module = None):
        key = (ModuleClass.switch, width)
        try:
            return self.context._database[ModuleView.logical, key]
        except KeyError:
            pass
        try:
            cfg_bitcount = (width - 1).bit_length()
        except AttributeError:
            cfg_bitcount = len(bin(width - 1).lstrip('-0b'))
        switch = Module('sw' + str(width),
                is_cell = True,
                view = ModuleView.logical,
                key = key,
                module_class = ModuleClass.switch,
                cfg_bitcount = cfg_bitcount,
                verilog_template = "switch.tmpl.v")

        # switch inputs/outputs
        i = ModuleUtils.create_port(switch, 'i', width, PortDirection.input_, net_class = NetClass.switch)
        o = ModuleUtils.create_port(switch, 'o', 1, PortDirection.output, net_class = NetClass.switch)
        NetUtils.create_timing_arc(TimingArcType.delay, i, o, fully = True)

        # configuration circuits
        self.entry._get_or_create_cfg_ports(switch, self.cfg_width)
        ModuleUtils.instantiate(switch, Scanchain.get_cfg_data_cell(self.context, cfg_bitcount), "i_cfg_data")
        
        # add to database and return
        return self.context._database.setdefault((ModuleView.logical, key), switch)

# # ----------------------------------------------------------------------------
# # -- FASM Delegate -----------------------------------------------------------
# # ----------------------------------------------------------------------------
# class ScanchainFASMDelegate(FASMDelegate):
#     """FASM delegate for scanchain configuration circuitry.
#     
#     Args:
#         context (`Context`):
#     """
# 
#     __slots__ = ['context']
#     def __init__(self, context):
#         self.context = context
# 
#     def _instance_bitoffset(self, instance):
#         if instance is None:
#             return 0
#         cfg_bitoffset = 0
#         if instance:
#             for i in reversed(instance.hierarchy):
#                 if (offset := getattr(i, "cfg_bitoffset", None)) is None:
#                     return None
#                 cfg_bitoffset += offset
#         return cfg_bitoffset
# 
#     def _features_for_path(self, source, sink, instance = None):
#         # 1. get the cfg bit offset for ``instance``
#         cfg_bitoffset = self._instance_bitoffset(instance)
#         if cfg_bitoffset is None:
#             return tuple()
#         # 2. get the cfg bits for the connection
#         conn = NetUtils.get_connection(source, sink)
#         if conn is None:
#             return tuple()
#         else:
#             return tuple('b{}'.format(cfg_bitoffset + i) for i in conn.get("cfg_bits", tuple()))
# 
#     def fasm_mux_for_intrablock_switch(self, source, sink, instance = None):
#         return self._features_for_path(source, sink, instance)
# 
#     def fasm_prefix_for_intrablock_module(self, instance):
#         if instance.model.module_class.is_primitive and instance.model.primitive_class.is_lut:
#             return ''
#         offset = getattr(instance.hierarchy[0], "cfg_bitoffset", None)
#         if offset is None:
#             return ''
#         else:
#             return 'b{}'.format(offset)
# 
#     def fasm_features_for_mode(self, instance, mode):
#         cfg_bitoffset = self._instance_bitoffset(instance)
#         if cfg_bitoffset is None:
#             return tuple()
#         return tuple("b{}".format(cfg_bitoffset + i) for i in instance.model.modes[mode].cfg_mode_selection)
# 
#     def fasm_prefix_for_tile(self, instance):
#         if (cfg_bitoffset := self._instance_bitoffset(instance)) is None:
#             return tuple()
#         retval = []
#         for subtile, blkinst in enumerate(instance.model._instances.subtiles):
#             if (inst_bitoffset := getattr(blkinst, 'cfg_bitoffset', None)) is None:
#                 return tuple()
#             retval.append( 'b{}'.format(cfg_bitoffset + inst_bitoffset) )
#         return retval
# 
#     def fasm_lut(self, instance):
#         cfg_bitoffset = self._instance_bitoffset(instance)
#         if cfg_bitoffset is None:
#             return ''
#         return 'b{}[{}:0]'.format(str(cfg_bitoffset), instance.model.cfg_bitcount - 1)
# 
#     def fasm_params_for_primitive(self, instance):
#         cfg_bitoffset = self._instance_bitoffset(instance)
#         if cfg_bitoffset is None:
#             return {}
#         params = getattr(instance.model, "parameters", None)
#         if params is None:
#             return {}
#         fasm_params = {}
#         for key, value in iteritems(params):
#             settings = value.get("cfg")
#             if settings is None:
#                 continue
#             fasm_params[key] = "b{}[{}:0]".format(settings.cfg_bitoffset, settings.cfg_bitcount - 1)
#         return fasm_params
# 
#     def fasm_features_for_routing_switch(self, source, sink, instance = None):
#         return self._features_for_path(source, sink, instance)

# ----------------------------------------------------------------------------
# -- Scanchain Configuration Circuitry Main Entry ----------------------------
# ----------------------------------------------------------------------------
class Scanchain(Object):
    """Scanchain configuration circuitry entry point."""

    class PrimitiveParameter(namedtuple("PrimitiveParameter", "cfg_bitoffset cfg_bitcount", defaults = (1, ))):
        pass

    @classmethod
    def _get_or_create_cfg_ports(cls, module, cfg_width, *, enable_only = False, we_o = False):
        try:
            if enable_only:
                return module.ports['cfg_e']
            else:
                keys = ("cfg_clk", "cfg_e", "cfg_we", "cfg_i", "cfg_o")
                if we_o:
                    keys += ("cfg_we_o", )
                return {k: module.ports[k] for k in keys}
        except KeyError:
            if enable_only:
                return ModuleUtils.create_port(module, 'cfg_e', 1, PortDirection.input_,
                        net_class = NetClass.cfg)
            else:
                ports = {}
                cfg_clk = ModuleUtils.create_port(module, 'cfg_clk', 1, PortDirection.input_,
                        is_clock = True, net_class = NetClass.cfg)
                cfg_e = module.ports.get("cfg_e")
                if cfg_e is None:
                    cfg_e = ModuleUtils.create_port(module, 'cfg_e', 1, PortDirection.input_,
                            net_class = NetClass.cfg)
                ports["cfg_e"] = cfg_e
                ports["cfg_we"] = ModuleUtils.create_port(module, "cfg_we", 1, PortDirection.input_,
                        net_class = NetClass.cfg)
                if we_o:
                    ports["cfg_we_o"] = ModuleUtils.create_port(module, "cfg_we_o", 1, PortDirection.output,
                            net_class = NetClass.cfg)
                ports["cfg_i"] = ModuleUtils.create_port(module, 'cfg_i', cfg_width, PortDirection.input_,
                        net_class = NetClass.cfg)
                ports["cfg_o"] = ModuleUtils.create_port(module, 'cfg_o', cfg_width, PortDirection.output,
                        net_class = NetClass.cfg)
                ports["cfg_clk"] = cfg_clk
                return ports

    @classmethod
    def _register_primitives(cls, context, cfg_width, dont_add_primitive, dont_add_logical_primitive):
        if not isinstance(dont_add_primitive, set):
            dont_add_primitive = set(iter(dont_add_primitive))

        if not isinstance(dont_add_logical_primitive, set):
            dont_add_logical_primitive = set(iter(dont_add_logical_primitive)) | dont_add_primitive

        # register chain delimiter
        if "cfg_delim" not in dont_add_logical_primitive:
            delim = Module("cfg_delim",
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "cfg_delim.tmpl.v")
            cls._get_or_create_cfg_ports(delim, cfg_width, we_o = True)
            context._database[ModuleView.logical, "cfg_delim"] = delim
        
        # register enable register
        if "cfg_e_reg" not in dont_add_logical_primitive:
            ereg = Module("cfg_e_reg",
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "cfg_e_reg.tmpl.v")
            clk = ModuleUtils.create_port(ereg, "cfg_clk", 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.cfg)
            ei = ModuleUtils.create_port(ereg, "cfg_e_i", 1, PortDirection.input_,
                    net_class = NetClass.cfg)
            eo = ModuleUtils.create_port(ereg, "cfg_e", 1, PortDirection.output,
                    net_class = NetClass.cfg)
            context._database[ModuleView.logical, "cfg_e_reg"] = ereg

        # register luts (logical view)
        for i in range(2, 9):
            name = "lut" + str(i)
            if name in dont_add_logical_primitive:
                continue
            lut = Module(name,
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.lut,
                    cfg_bitcount = 2 ** i,
                    verilog_template = "lut.tmpl.v")

            # user ports
            in_ = ModuleUtils.create_port(lut, 'in', i, PortDirection.input_,
                    net_class = NetClass.user, port_class = PrimitivePortClass.lut_in)
            out = ModuleUtils.create_port(lut, 'out', 1, PortDirection.output,
                    net_class = NetClass.user, port_class = PrimitivePortClass.lut_out)
            NetUtils.create_timing_arc(TimingArcType.delay, in_, out, fully = True)

            # configuration data
            ModuleUtils.instantiate(lut, cls.get_cfg_data_cell(context, 2 ** i), "i_cfg_data")
            cls._get_or_create_cfg_ports(lut, cfg_width)

            # add to database
            context._database[ModuleView.logical, lut.key] = lut

            # modify built-in LUT
            context._database[ModuleView.user, lut.key].cfg_bitcount = 2 ** i

        # register flipflops (logical view)
        if "flipflop" not in dont_add_logical_primitive:
            flipflop = Module('flipflop',
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.flipflop,
                    verilog_template = "flipflop.tmpl.v")

            # user ports
            clk = ModuleUtils.create_port(flipflop, 'clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.user, port_class = PrimitivePortClass.clock)
            D = ModuleUtils.create_port(flipflop, 'D', 1, PortDirection.input_,
                    net_class = NetClass.user, port_class = PrimitivePortClass.D)
            Q = ModuleUtils.create_port(flipflop, 'Q', 1, PortDirection.output,
                    net_class = NetClass.user, port_class = PrimitivePortClass.Q)
            NetUtils.create_timing_arc((TimingArcType.setup, TimingArcType.hold), clk, D)
            NetUtils.create_timing_arc(TimingArcType.clk2q, clk, Q)

            # configuration ports
            cls._get_or_create_cfg_ports(flipflop, cfg_width, enable_only = True)

            # add to database
            context._database[ModuleView.logical, flipflop.key] = flipflop

        # register I/O (logical view)
        for name in ("inpad", "outpad", "iopad"):
            if name in dont_add_logical_primitive:
                continue
            kwargs = {
                    "is_cell": True,
                    "view": ModuleView.logical,
                    "module_class": ModuleClass.primitive,
                    "verilog_template": name + ".tmpl.v",
                    }
            if name == "inpad":
                kwargs["primitive_class"] = PrimitiveClass.inpad
                kwargs["cfg_bitcount"] = 1
            elif name == "outpad":
                kwargs["primitive_class"] = PrimitiveClass.outpad
                kwargs["cfg_bitcount"] = 1
            else:
                kwargs["primitive_class"] = PrimitiveClass.custom
                kwargs["cfg_bitcount"] = 2
            pad = Module(name, **kwargs)

            if name in ("inpad", "iopad"):
                ui = ModuleUtils.create_port(pad, "inpad", 1, PortDirection.output, net_class = NetClass.user)
                li = ModuleUtils.create_port(pad, "_ipin", 1, PortDirection.input_,
                        net_class = NetClass.io, key = IOType.ipin)
                NetUtils.create_timing_arc(TimingArcType.delay, li, ui)
            if name in ("outpad", "iopad"):
                uo = ModuleUtils.create_port(pad, "outpad", 1, PortDirection.input_, net_class = NetClass.user)
                lo = ModuleUtils.create_port(pad, "_opin", 1, PortDirection.output,
                        net_class = NetClass.io, key = IOType.opin)
                NetUtils.create_timing_arc(TimingArcType.delay, uo, lo)

            if name == "iopad":
                ModuleUtils.create_port(pad, "_oe", 1, PortDirection.output, net_class = NetClass.io, key = IOType.oe)
                ModuleUtils.instantiate(pad, cls.get_cfg_data_cell(context, 2), "i_cfg_data")
                userpad = context._database[ModuleView.user, pad.key]
                userpad.cfg_bitcount = 2
                userpad.modes["inpad"].cfg_mode_selection = (0, )
                userpad.modes["outpad"].cfg_mode_selection = (1, )
            else:
                ModuleUtils.instantiate(pad, cls.get_cfg_data_cell(context, 1), "i_cfg_data")
                userpad = context._database[ModuleView.user, pad.key]
                userpad.cfg_bitcount = 1

            # configuration ports
            cls._get_or_create_cfg_ports(pad, cfg_width)

            context._database[ModuleView.logical, pad.key] = pad

        # register fracturable LUT6
        if not ({"lut5", "lut6", "fraclut6"} & dont_add_primitive):
            # user view
            fraclut6 = context.build_multimode('fraclut6', cfg_bitcount = 65)
            fraclut6.create_input("in", 6)
            fraclut6.create_output("o6", 1)
            fraclut6.create_output("o5", 1)

            if True:
                mode = fraclut6.build_mode("lut6x1", cfg_mode_selection = (64, ))
                inst = mode.instantiate(context.primitives["lut6"], "LUT6A", cfg_bitoffset = 0)
                mode.connect(mode.ports["in"], inst.pins["in"])
                mode.connect(inst.pins["out"], mode.ports["o6"], vpr_pack_patterns = ("lut6_dff", ))
                mode.commit()

            if True:
                mode = fraclut6.build_mode("lut5x2", cfg_mode_selection = tuple())
                insts = mode.instantiate(context.primitives["lut5"], "LUT5", 2)
                insts[0].cfg_bitoffset = 0
                insts[1].cfg_bitoffset = 32
                mode.connect(mode.ports["in"][:5], insts[0].pins["in"])
                mode.connect(mode.ports["in"][:5], insts[1].pins["in"])
                mode.connect(insts[0].pins["out"], mode.ports["o6"], vpr_pack_patterns = ("lut5A_dff", ))
                mode.connect(insts[1].pins["out"], mode.ports["o5"], vpr_pack_patterns = ("lut5B_dff", ))
                mode.commit()

            # logical view
            if "fraclut6" not in dont_add_logical_primitive:
                fraclut6 = fraclut6.build_logical_counterpart(cfg_bitcount = 65, verilog_template = "fraclut6.tmpl.v")

                # timing arcs
                fraclut6.create_timing_arc(TimingArcType.delay, fraclut6.ports["in"], fraclut6.ports["o6"],
                        fully = True)
                fraclut6.create_timing_arc(TimingArcType.delay, fraclut6.ports["in"][:5], fraclut6.ports["o5"],
                        fully = True)

                # configuration data
                fraclut6.instantiate(cls.get_cfg_data_cell(context, 65), "i_cfg_data")
                cls._get_or_create_cfg_ports(fraclut6._module, cfg_width)

            fraclut6.commit()

        # register multi-mode flipflop
        if "mdff" not in dont_add_primitive:
            # user view
            mdff = context.build_primitive("mdff",
                    techmap_template = "mdff.techmap.tmpl.v",
                    verilog_template = "mdff.lib.tmpl.v",
                    premap_commands = (
                        "simplemap t:$dff t:$dffe t:$dffsr",
                        "dffsr2dff",
                        "dff2dffe",
                        "opt -full",
                        ),
                    parameters = {
                        "ENABLE_CE": {"default": "1'b0", "cfg": cls.PrimitiveParameter(0)},
                        "ENABLE_SR": {"default": "1'b0", "cfg": cls.PrimitiveParameter(1)},
                        "SR_SET":   {"default": "1'b0", "cfg": cls.PrimitiveParameter(2)},
                        },
                    cfg_bitcount = 3)
            clk = mdff.create_clock("clk")

            p = []
            p.append(mdff.create_input("D", 1))
            p.append(mdff.create_input("ce", 1))
            p.append(mdff.create_input("sr", 1))
            mdff.create_timing_arc((TimingArcType.setup, TimingArcType.hold), clk, p, fully = True)

            q = mdff.create_output("Q", 1)
            mdff.create_timing_arc(TimingArcType.clk2q, clk, q)

            # logical view
            if "mdff" not in dont_add_logical_primitive:
                mdff = mdff.build_logical_counterpart(cfg_bitcount = 3, verilog_template = "mdff.tmpl.v")

                # timing arcs
                mdff.create_timing_arc((TimingArcType.setup, TimingArcType.hold), mdff.ports["clk"],
                        [mdff.ports["D"], mdff.ports["ce"], mdff.ports["sr"]], fully = True)
                mdff.create_timing_arc(TimingArcType.clk2q, mdff.ports["clk"], mdff.ports["Q"])

                # configuration data
                mdff.instantiate(cls.get_cfg_data_cell(context, 3), "i_cfg_data")
                cls._get_or_create_cfg_ports(mdff._module, cfg_width)
            
            mdff.commit()

        # register adder
        if "adder" not in dont_add_primitive:
            # user view
            adder = context.build_primitive("adder",
                    techmap_template = "adder.techmap.tmpl.v",
                    verilog_template = "adder.lib.tmpl.v",
                    parameters = {
                        "CIN_FABRIC": {"default": "1'b0", "cfg": cls.PrimitiveParameter(0)},
                        },
                    cfg_bitcount = 1)
            i, o = [], []
            o.append(adder.create_output("cout", 1))
            o.append(adder.create_output("s", 1))
            o.append(adder.create_output("cout_fabric", 1))
            i.append(adder.create_input("a", 1))
            i.append(adder.create_input("b", 1))
            i.append(adder.create_input("cin", 1))
            i.append(adder.create_input("cin_fabric", 1))
            adder.create_timing_arc(TimingArcType.delay, i, o, fully = True)

            # logical view
            if "adder" not in dont_add_logical_primitive:
                adder = adder.build_logical_counterpart(cfg_bitcount = 1, verilog_template = "adder.tmpl.v")

                # timing arcs
                adder.create_timing_arc(TimingArcType.delay,
                        [adder.ports["a"], adder.ports["b"], adder.ports["cin"], adder.ports["cin_fabric"]],
                        [adder.ports["cout"], adder.ports["s"], adder.ports["cout_fabric"]],
                        fully = True)

                # configuration data
                adder.instantiate(cls.get_cfg_data_cell(context, 1), "i_cfg_data")
                cls._get_or_create_cfg_ports(adder._module, cfg_width)

            adder.commit()

        # register simplified stratix-IV FLE
        if not ({"lut5", "lut6", "adder", "flipflop", "fle6"} & dont_add_primitive):
            # user view
            fle6 = context.build_multimode('fle6', cfg_bitcount = 69)
            fle6.create_clock("clk")
            fle6.create_input("in", 6)
            fle6.create_input("cin", 1)
            fle6.create_output("out", 2)
            fle6.create_output("cout", 1)

            if True:
                mode = fle6.build_mode("lut6x1", cfg_mode_selection = tuple())
                lut = mode.instantiate(context.primitives["lut6"], "lut", cfg_bitoffset = 0)
                ff = mode.instantiate(context.primitives["flipflop"], "ff")
                mode.connect(mode.ports["clk"], ff.pins["clk"])
                mode.connect(mode.ports["in"], lut.pins["in"])
                mode.connect(lut.pins["out"], ff.pins["D"], vpr_pack_patterns = ["lut6_dff"])
                mode.connect(lut.pins["out"], mode.ports["out"][0], cfg_bits = (64, ))
                mode.connect(ff.pins["Q"], mode.ports["out"][0])
                mode.commit()

            if True:
                mode = fle6.build_mode("lut5x2", cfg_mode_selection = (66, ))
                luts = mode.instantiate(context.primitives["lut5"], "lut", 2)
                ffs = mode.instantiate(context.primitives["flipflop"], "ff", 2)
                for i, (lut, ff) in enumerate(zip(luts, ffs)):
                    lut.cfg_bitoffset = 32 * i
                    mode.connect(mode.ports["clk"], ff.pins["clk"])
                    mode.connect(mode.ports["in"][0:5], lut.pins["in"])
                    mode.connect(lut.pins["out"], ff.pins["D"], vpr_pack_patterns = ["lut5_i" + str(i) + "_dff"])
                    mode.connect(lut.pins["out"], mode.ports["out"][i], cfg_bits = (64 + i, ))
                    mode.connect(ff.pins["Q"], mode.ports["out"][i])
                mode.commit()

            if True:
                mode = fle6.build_mode("arithmetic", cfg_mode_selection = (66, 67))
                luts = mode.instantiate(context.primitives["lut5"], "lut", 2)
                ffs = mode.instantiate(context.primitives["flipflop"], "ff", 2)
                adder = mode.instantiate(context.primitives["adder"], "fa", cfg_bitoffset = 68)
                mode.connect(mode.ports["cin"], adder.pins["cin"], vpr_pack_patterns = ["carrychain"])
                mode.connect(mode.ports["in"][5], adder.pins["cin_fabric"])
                for i, (p, lut) in enumerate(zip(["a", "b"], luts)):
                    lut.cfg_bitoffset = 32 * i
                    mode.connect(mode.ports["in"][0:5], lut.pins["in"])
                    mode.connect(lut.pins["out"], adder.pins[p], vpr_pack_patterns = ["carrychain"])
                for i, (p, ff) in enumerate(zip(["s", "cout_fabric"], ffs)):
                    mode.connect(mode.ports["clk"], ff.pins["clk"])
                    mode.connect(adder.pins[p], ff.pins["D"], vpr_pack_patterns = ["carrychain"])
                    mode.connect(adder.pins[p], mode.ports["out"][i], cfg_bits = (64 + i, ))
                    mode.connect(ff.pins["Q"], mode.ports["out"][i])
                mode.connect(adder.pins["cout"], mode.ports["cout"], vpr_pack_patterns = ["carrychain"])
                mode.commit()

            # logical view
            if "fle6" not in dont_add_logical_primitive:
                fle6 = fle6.build_logical_counterpart(cfg_bitcount = 69, verilog_template = "fle6.tmpl.v")

                # timing arcs
                fle6.create_timing_arc(TimingArcType.delay,
                        [fle6.ports["in"], fle6.ports["cin"]],
                        [fle6.ports["out"], fle6.ports["cout"]],
                        fully = True)
                fle6.create_timing_arc((TimingArcType.setup, TimingArcType.hold),
                        fle6.ports["clk"],
                        [fle6.ports["in"], fle6.ports["cin"]],
                        fully = True)
                fle6.create_timing_arc(TimingArcType.clk2q,
                        fle6.ports["clk"],
                        [fle6.ports["out"], fle6.ports["cout"]],
                        fully = True)

                # configuration ports
                fle6.instantiate(cls.get_cfg_data_cell(context, 69), "i_cfg_data")
                cls._get_or_create_cfg_ports(fle6._module, cfg_width)

            fle6.commit()

    @classmethod
    def get_cfg_data_cell(cls, context, data_width):
        """Get the configuration module for ``data_width`` bits.

        Args:
            context (`Context`):
            data_width (:obj:`int`): Width of the data port
        
        Returns:
            `Module`:
        """
        key = ("cfg_data", data_width)
        if (module := context.database.get( (ModuleView.logical, key) )) is None:
            module = Module("cfg_data_d{}".format(data_width),
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "cfg_data.tmpl.v",
                    key = key,
                    cfg_bitcount = data_width)
            cfg_clk = cls._get_or_create_cfg_ports(module, context.summary.scanchain["cfg_width"])["cfg_clk"]
            cfg_d = ModuleUtils.create_port(module, "cfg_d", data_width, PortDirection.output,
                    net_class = NetClass.cfg)
            context._database[ModuleView.logical, key] = module
        return module

    @classmethod
    def new_context(cls, cfg_width = 1, *, dont_add_primitive = tuple(), dont_add_logical_primitive = tuple()):
        """Create a new context.

        Args:
            cfg_width (:obj:`int`): Width of the scanchain

        Keyword Args:
            dont_add_primitive (:obj:`Sequence` [:obj:`str` ]): A list of primitives (user view) and all primitives
                depending on them that are excluded when creating the context
            dont_add_logical_primitive (:obj:`Sequence` [:obj:`str` ]): A list of primitives (logical view) and all
                primitives depending on them that are excluded when creating the context

        Returns:
            `Context`:
        """
        context = Context("scanchain")
        context.summary.scanchain = {"cfg_width": cfg_width}
        context._switch_database = ScanchainSwitchDatabase(context, cfg_width, cls)
        # context._fasm_delegate = ScanchainFASMDelegate(context)
        cls._register_primitives(context, cfg_width, dont_add_primitive, dont_add_logical_primitive)
        return context

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        """Create a new file renderer.

        Args:
            additional_template_search_paths (:obj:`Sequence` [:obj:`str` ]): Additional paths where the renderer
                should search for template files

        Returns:
            `FileRenderer`:
        """
        r = FileRenderer()
        r.template_search_paths.insert(0, ADDITIONAL_TEMPLATE_SEARCH_PATH)
        r.template_search_paths.extend(additional_template_search_paths)
        return r

    @classmethod
    def complete_scanchain(cls, context, logical_module = None, *,
            iter_instances = lambda m: itervalues(m.instances),
            timing_enclosure = lambda m: m.module_class.is_block or m.module_class.is_routing_box):
        """Inject the scanchain.
        
        Args:
            context (`Context`):
            logical_module (`Module`): The module (logical view) in which scanchain is injected. If not specified, the
                top-level array in ``context`` is selected

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module
            timing_enclosure (:obj:`Function` [`Module` ] -> :obj:`bool`): A function used to determine if
                configuration enable signals should be registered for one configuration cycle in a module. This is
                necessary because the configuration enable signal may control millions of registers across the entire
                FPGA. This super high-fanout net, if not registered, will be very slow to drive

        This method calls itself recursively to process all the instances (sub-modules).
        """
        cfg_width = context.summary.scanchain["cfg_width"]
        module = uno(logical_module, context.database[ModuleView.logical, context.top.key])
        # connecting scanchain ports
        cfg_bitoffset = 0
        cfg_nets = {}
        instances_snapshot = tuple(iter_instances(module))
        for instance in instances_snapshot:
            if instance.model.module_class not in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.cfg):
                if not hasattr(instance.model, 'cfg_bitcount'):
                    cls.complete_scanchain(context, instance.model, iter_instances = iter_instances)
            # enable pin
            if (inst_cfg_e := instance.pins.get("cfg_e")) is None:
                continue
            if (cfg_e := cfg_nets.get("cfg_e")) is None:
                if timing_enclosure(module):
                    ereg = ModuleUtils.instantiate(module,
                            context.database[ModuleView.logical, "cfg_e_reg"],
                            "_i_cfg_ereg")
                    NetUtils.connect(cls._get_or_create_cfg_ports(module, cfg_width, enable_only = True),
                            ereg.pins["cfg_e_i"])
                    cfg_e = cfg_nets["cfg_e"] = ereg.pins["cfg_e"]
                    for k, v in iteritems(cls._get_or_create_cfg_ports(module, cfg_width)):
                        cfg_nets.setdefault(k, v)
                    NetUtils.connect(cfg_nets["cfg_clk"], ereg.pins["cfg_clk"])
                else:
                    cfg_e = cfg_nets["cfg_e"] = cls._get_or_create_cfg_ports(module, cfg_width,
                            enable_only = True)
            NetUtils.connect(cfg_e, inst_cfg_e)
            # actual bitstream loading pin
            inst_cfg_i = instance.pins.get('cfg_i')
            if inst_cfg_i is None:
                continue
            assert len(inst_cfg_i) == cfg_width
            instance.cfg_bitoffset = cfg_bitoffset
            cfg_bitoffset += instance.model.cfg_bitcount
            # connect nets
            if "cfg_clk" not in cfg_nets:
                for k, v in iteritems(cls._get_or_create_cfg_ports(module, cfg_width)):
                    cfg_nets.setdefault(k, v)
            NetUtils.connect(cfg_nets["cfg_clk"], instance.pins['cfg_clk'])
            NetUtils.connect(cfg_nets["cfg_i"], inst_cfg_i)
            NetUtils.connect(cfg_nets["cfg_we"], instance.pins["cfg_we"])
            cfg_nets["cfg_i"] = instance.pins['cfg_o']
            cfg_we_o = instance.pins.get("cfg_we_o")
            if cfg_we_o:
                cfg_nets["cfg_we"] = cfg_we_o
                if "cfg_we_o" not in cfg_nets:
                    cfg_nets["cfg_we_o"] = ModuleUtils.create_port(module, "cfg_we_o", 1, PortDirection.output,
                            net_class = NetClass.cfg)
        if "cfg_i" in cfg_nets:
            if timing_enclosure(module):
                # align to `cfg_width`
                if cfg_bitoffset % cfg_width != 0:
                    remainder = cfg_width - (cfg_bitoffset % cfg_width)
                    filler = ModuleUtils.instantiate(module,
                            cls.get_cfg_data_cell(context, remainder),
                            "_i_cfg_filler")
                    NetUtils.connect(cls._get_or_create_cfg_ports(module, cfg_width, enable_only = True),
                            filler.pins["cfg_e"])
                    NetUtils.connect(cfg_nets["cfg_clk"], filler.pins["cfg_clk"])
                    NetUtils.connect(cfg_nets["cfg_we"], filler.pins["cfg_we"])
                    NetUtils.connect(cfg_nets["cfg_i"], filler.pins["cfg_i"])
                    cfg_nets["cfg_i"] = filler.pins["cfg_o"]
                    cfg_bitoffset += remainder
                # inject cfg_we register
                cfg_we_o = cfg_nets.get("cfg_we_o")
                if cfg_we_o is None:
                    cfg_we_o = ModuleUtils.create_port(module, "cfg_we_o", 1, PortDirection.output,
                            net_class = NetClass.cfg)
                delimiter = ModuleUtils.instantiate(module, 
                        context.database[ModuleView.logical, "cfg_delim"],
                        "_i_cfg_delim")
                NetUtils.connect(cfg_nets["cfg_clk"], delimiter.pins["cfg_clk"])
                NetUtils.connect(cfg_nets["cfg_e"], delimiter.pins["cfg_e"])
                NetUtils.connect(cfg_nets["cfg_we"], delimiter.pins["cfg_we"])
                NetUtils.connect(cfg_nets["cfg_i"], delimiter.pins["cfg_i"])
                NetUtils.connect(delimiter.pins["cfg_o"], cfg_nets["cfg_o"])
                NetUtils.connect(delimiter.pins["cfg_we_o"], cfg_we_o)
            else:
                NetUtils.connect(cfg_nets["cfg_i"], cfg_nets["cfg_o"])
                cfg_we_o = cfg_nets.get("cfg_we_o")
                if cfg_we_o:
                    NetUtils.connect(cfg_nets["cfg_we"], cfg_we_o)
        module.cfg_bitcount = cfg_bitoffset
        _logger.info("Scanchain injected to {}. Total bits: {}".format(module, cfg_bitoffset))
        if module.key == context.top.key:
            if not hasattr(context.summary, "scanchain"):
                context.summary.scanchain = {}
            context.summary.scanchain["bitstream_size"] = cfg_bitoffset

    @classmethod
    def annotate_user_view(cls, context, user_module = None, *, _annotated = None):
        """Annotate configuration data back to the user view.
        
        Args:
            context (`Context`):
            user_module (`Module`): User view of the module to be annotated

        Keyword Args:
            _annotated (:obj:`set` [:obj:`Hashable` ]): A scratchpad used to track processed modules across recursive
                calls

        This method calls itself recursively to process all instances (sub-modules).
        """
        module = uno(user_module, context.top)
        logical = context.database[ModuleView.logical, module.key]
        _annotated = uno(_annotated, set())

        # 1. annotate user instances
        for instance in itervalues(module.instances):
            # look for the corresponding logical instance and annotate cfg_bitoffset
            logical_instance = logical.instances[instance.key]
            if hasattr(logical_instance, "cfg_bitoffset"):
                instance.cfg_bitoffset = logical_instance.cfg_bitoffset
                if not (instance.model.module_class.is_primitive or instance.model.key in _annotated):
                    _annotated.add(instance.model.key)
                    cls.annotate_user_view(context, instance.model, _annotated = _annotated)

        # 2. annotate multi-source connections
        if not module.allow_multisource:
            return
        assert not module.coalesce_connections and not logical.coalesce_connections
        assert not logical.allow_multisource
        for logical_bus in ModuleUtils._iter_nets(logical):
            if logical_bus.net_type.is_port and not logical_bus.net_class.is_user:
                continue
            elif logical_bus.net_type.is_pin and not logical_bus.model.net_class.is_user:
                continue
            elif not logical_bus.is_sink:
                continue
            for logical_sink in logical_bus:
                user_tail = NetUtils._dereference(module, NetUtils._reference(logical_sink))
                stack = [(logical_sink, tuple())]
                while stack:
                    head, cfg_bits = stack.pop()

                    # check source driving head
                    if (prev := NetUtils.get_source(head)).net_type.is_const:
                        continue
                    elif prev.net_type.is_pin and prev.model.net_class.is_switch:
                        # switch output
                        switch = prev.instance
                        for idx, input_ in enumerate(switch.pins['i']):
                            this_cfg_bits = cfg_bits
                            for digit in range(idx.bit_length()):
                                if (idx & (1 << digit)):
                                    this_cfg_bits += (switch.cfg_bitoffset + digit, )
                            stack.append( (input_, this_cfg_bits) )
                    else:
                        user_head = NetUtils._dereference(module, NetUtils._reference(prev))
                        NetUtils.get_connection(user_head, user_tail).cfg_bits = cfg_bits

    class InjectConfigCircuitry(AbstractPass):
        """Automatically inject configuration circuitry.
        
        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module
            timing_enclosure (:obj:`Function` [`Module` ] -> :obj:`bool`): A function used to determine if
                configuration enable signals should be registered for one configuration cycle in a module. This is
                necessary because the configuration enable signal may control millions of registers across the entire
                FPGA. This super high-fanout net, if not registered, will be very slow to drive
        """

        __slots__ = ["iter_instances", "timing_enclosure"]

        def __init__(self, *, iter_instances = None, timing_enclosure = None):
            self.iter_instances = iter_instances
            self.timing_enclosure = timing_enclosure

        def run(self, context, renderer = None):
            kwargs = {}
            if callable(self.iter_instances):
                kwargs["iter_instances"] = self.iter_instances
            if callable(self.timing_enclosure):
                kwargs["timing_enclosure"] = self.timing_enclosure
            Scanchain.complete_scanchain(context, **kwargs)
            Scanchain.annotate_user_view(context)

        @property
        def key(self):
            return "config.injection.scanchain"

        @property
        def dependences(self):
            return ("translation", )
        
        @property
        def passes_after_self(self):
            return ("rtl", )
