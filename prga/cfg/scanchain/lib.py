# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...core.common import NetClass, ModuleClass, ModuleView, Subtile, IOType
from ...core.context import Context
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...passes.translation import AbstractSwitchDatabase, TranslationPass
from ...passes.vpr import FASMDelegate
from ...renderer.renderer import FileRenderer
from ...util import Object, uno
from ...exception import PRGAInternalError

import os
from collections import OrderedDict, namedtuple
from itertools import chain

__all__ = ['Scanchain']

ADDITIONAL_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- Switch Database ---------------------------------------------------------
# ----------------------------------------------------------------------------
class ScanchainSwitchDatabase(Object, AbstractSwitchDatabase):
    """Switch database for scanchain configuration circuitry."""

    __slots__ = ["context", "cfg_width"]
    def __init__(self, context, cfg_width):
        self.context = context
        self.cfg_width = cfg_width

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
        switch = Module('sw' + str(width), view = ModuleView.logical, is_cell = True, key = key,
                module_class = ModuleClass.switch, cfg_bitcount = cfg_bitcount,
                verilog_template = "switch.tmpl.v")
        # switch inputs/outputs
        i = ModuleUtils.create_port(switch, 'i', width, PortDirection.input_, net_class = NetClass.switch)
        o = ModuleUtils.create_port(switch, 'o', 1, PortDirection.output, net_class = NetClass.switch)
        NetUtils.connect(i, o, fully = True)
        # configuration circuits
        Scanchain._get_or_create_cfg_ports(switch, self.cfg_width)
        return self.context._database.setdefault((ModuleView.logical, key), switch)

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class ScanchainFASMDelegate(FASMDelegate):
    """FASM delegate for scanchain configuration circuitry.
    
    Args:
        context (`Context`):
    """

    __slots__ = ['context']
    def __init__(self, context):
        self.context = context

    def _instance_bitoffset(self, instance):
        if instance is None:
            return 0
        cfg_bitoffset = 0
        if instance:
            for i in reversed(instance.hierarchy):
                offset = getattr(i, "cfg_bitoffset", None)
                if offset is None:
                    return None
                cfg_bitoffset += offset
        return cfg_bitoffset

    def _features_for_path(self, source, sink, instance = None):
        # 1. get the cfg bit offset for ``instance``
        cfg_bitoffset = self._instance_bitoffset(instance)
        if cfg_bitoffset is None:
            return tuple()
        # 2. get the cfg bits for the connection
        conn = NetUtils.get_connection(source, sink)
        if conn is None:
            return tuple()
        else:
            return tuple('b{}'.format(cfg_bitoffset + i) for i in conn.get("cfg_bits", tuple()))

    def fasm_mux_for_intrablock_switch(self, source, sink, instance = None):
        return self._features_for_path(source, sink, instance)

    def fasm_prefix_for_intrablock_module(self, instance):
        offset = getattr(instance.hierarchy[0], "cfg_bitoffset", None)
        if offset is None:
            return ''
        else:
            return 'b{}'.format(offset)

    def fasm_features_for_mode(self, instance, mode):
        cfg_bitoffset = self._instance_bitoffset(instance)
        if cfg_bitoffset is None:
            return tuple()
        return tuple("b{}".format(cfg_bitoffset + i) for i in instance.model.modes[mode].cfg_mode_selection)

    def fasm_prefix_for_tile(self, instance):
        cfg_bitoffset = self._instance_bitoffset(instance.shrink_hierarchy(slice(1, None)))
        if cfg_bitoffset is None:
            return tuple()
        retval = []
        leaf_array = instance.hierarchy[0].parent
        for subblock in range(instance.model.capacity):
            blk_inst = leaf_array.instances[instance.hierarchy[0].key[0], subblock]
            inst_bitoffset = getattr(blk_inst, 'cfg_bitoffset', None)
            if inst_bitoffset is None:
                return tuple()
            retval.append( 'b{}'.format(cfg_bitoffset + inst_bitoffset) )
        return retval

    def fasm_lut(self, instance):
        cfg_bitoffset = self._instance_bitoffset(instance)
        if cfg_bitoffset is None:
            return ''
        return 'b{}[{}:0]'.format(str(cfg_bitoffset), instance.model.cfg_bitcount - 1)

    def fasm_params_for_primitive(self, instance):
        cfg_bitoffset = self._instance_bitoffset(instance)
        if cfg_bitoffset is None:
            return {}
        params = getattr(instance.model, "parameters", None)
        if params is None:
            return {}
        fasm_params = {}
        for key, value in iteritems(params):
            settings = value.get("cfg")
            if settings is None:
                continue
            fasm_params[key] = "b{}[{}:0]".format(settings.cfg_bitoffset, settings.cfg_bitcount - 1)
        return fasm_params

    def fasm_features_for_routing_switch(self, source, sink, instance = None):
        return self._features_for_path(source, sink, instance)

# ----------------------------------------------------------------------------
# -- Scanchain Configuration Circuitry Main Entry ----------------------------
# ----------------------------------------------------------------------------
class Scanchain(object):
    """Scanchain configuration circuitry entry point."""

    class _PrimitiveParameter(namedtuple("_PrimitiveParameter", "cfg_bitoffset cfg_bitcount")):
        pass

    @classmethod
    def _get_or_create_cfg_ports(cls, module, cfg_width, enable_only = False):
        try:
            if enable_only:
                return module.ports['cfg_e']
            else:
                return tuple(map(lambda x: module.ports[x], ("cfg_clk", "cfg_e", "cfg_i", "cfg_o")))
        except KeyError:
            if enable_only:
                return ModuleUtils.create_port(module, 'cfg_e', 1, PortDirection.input_,
                        net_class = NetClass.cfg)
            else:
                cfg_clk = ModuleUtils.create_port(module, 'cfg_clk', 1, PortDirection.input_,
                        is_clock = True, net_class = NetClass.cfg)
                cfg_e = module.ports.get("cfg_e")
                if cfg_e is None:
                    cfg_e = ModuleUtils.create_port(module, 'cfg_e', 1, PortDirection.input_,
                            net_class = NetClass.cfg)
                cfg_i = ModuleUtils.create_port(module, 'cfg_i', cfg_width, PortDirection.input_,
                        net_class = NetClass.cfg)
                cfg_o = ModuleUtils.create_port(module, 'cfg_o', cfg_width, PortDirection.output,
                        net_class = NetClass.cfg)
                if module.is_cell:
                    NetUtils.connect(cfg_clk, [cfg_e, cfg_i, cfg_o], fully = True, allow_multisource = True)
                return cfg_clk, cfg_e, cfg_i, cfg_o

    @classmethod
    def new_context(cls, cfg_width = 1, *, dont_add_primitive = tuple()):
        context = Context("scanchain", cfg_width = cfg_width)
        context._switch_database = ScanchainSwitchDatabase(context, cfg_width)
        context._fasm_delegate = ScanchainFASMDelegate(context)

        # modify dual-mode I/O
        if True:
            iopad = context.primitives["iopad"]
            iopad.cfg_bitcount = 1
            iopad.modes["inpad"].cfg_mode_selection = tuple()
            iopad.modes["outpad"].cfg_mode_selection = (0, )

        # register luts
        for i in range(2, 9):
            name = "lut" + str(i)
            if name in dont_add_primitive:
                continue
            lut = Module(name,
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.primitive,
                    cfg_bitcount = 2 ** i,
                    verilog_template = "lut.tmpl.v")
            # user ports
            in_ = ModuleUtils.create_port(lut, 'in', i, PortDirection.input_, net_class = NetClass.primitive)
            out = ModuleUtils.create_port(lut, 'out', 1, PortDirection.output, net_class = NetClass.primitive)
            NetUtils.connect(in_, out, fully = True)

            # configuration ports
            cls._get_or_create_cfg_ports(lut, cfg_width)
            context._database[ModuleView.logical, lut.key] = lut

            # modify built-in LUT
            context._database[ModuleView.user, lut.key].cfg_bitcount = 2 ** i

        # register flipflops
        if "flipflop" not in dont_add_primitive:
            flipflop = Module('flipflop',
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.primitive,
                    verilog_template = "flipflop.tmpl.v")
            clk = ModuleUtils.create_port(flipflop, 'clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.primitive)
            D = ModuleUtils.create_port(flipflop, 'D', 1, PortDirection.input_,
                    net_class = NetClass.primitive)
            Q = ModuleUtils.create_port(flipflop, 'Q', 1, PortDirection.output,
                    net_class = NetClass.primitive)
            NetUtils.connect(clk, [D, Q], fully = True)

            # configuration ports
            cls._get_or_create_cfg_ports(flipflop, cfg_width, enable_only = True)
            context._database[ModuleView.logical, flipflop.key] = flipflop

        # register single-bit configuration filler
        if "cfg_bit" not in dont_add_primitive:
            cfg_bit = Module('cfg_bit',
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.cfg,
                    cfg_bitcount = 1,
                    verilog_template = "cfg_bit.tmpl.v")
            cfg_clk, _0, _1, _2 = cls._get_or_create_cfg_ports(cfg_bit, cfg_width)
            cfg_d = ModuleUtils.create_port(cfg_bit, 'cfg_d', 1, PortDirection.output,
                    net_class = NetClass.cfg)
            NetUtils.connect(cfg_clk, cfg_d)
            context._database[ModuleView.logical, cfg_bit.key] = cfg_bit

        # register fracturable LUT6
        if ("lut5" not in dont_add_primitive and
                "lut6" not in dont_add_primitive and
                "fraclut6" not in dont_add_primitive):
            # user view
            fraclut6 = context.create_multimode('fraclut6', cfg_bitcount = 65)
            fraclut6.create_input("in", 6)
            fraclut6.create_output("o6", 1)
            fraclut6.create_output("o5", 1)

            if True:
                mode = fraclut6.create_mode("lut6x1", cfg_mode_selection = (64, ))
                inst = mode.instantiate(context.primitives["lut6"], "LUT6A", cfg_bitoffset = 0)
                mode.connect(mode.ports["in"], inst.pins["in"])
                mode.connect(inst.pins["out"], mode.ports["o6"], pack_patterns = ("lut6_dff", ))
                mode.commit()

            if True:
                mode = fraclut6.create_mode("lut5x2", cfg_mode_selection = tuple())
                insts = mode.instantiate(context.primitives["lut5"], "LUT5", vpr_num_pb = 2)
                insts[0].cfg_bitoffset = 0
                insts[1].cfg_bitoffset = 32
                mode.connect(mode.ports["in"][:5], insts[0].pins["in"])
                mode.connect(mode.ports["in"][:5], insts[1].pins["in"])
                mode.connect(insts[0].pins["out"], mode.ports["o6"], pack_patterns = ("lut5A_dff", ))
                mode.connect(insts[1].pins["out"], mode.ports["o5"], pack_patterns = ("lut5B_dff", ))
                mode.commit()

            fraclut6 = fraclut6.create_logical_counterpart(
                    cfg_bitcount = 65, verilog_template = "fraclut6.tmpl.v")

            # combinational paths
            fraclut6.add_timing_arc(fraclut6.ports["in"], fraclut6.ports["o6"])
            fraclut6.add_timing_arc(fraclut6.ports["in"][:5], fraclut6.ports["o5"])

            # configuration ports
            cls._get_or_create_cfg_ports(fraclut6._module, cfg_width)

            fraclut6.commit()

        # register multi-mode flipflop
        if "mdff" not in dont_add_primitive:
            # user view
            mdff = context.create_primitive("mdff",
                    techmap_template = "mdff.techmap.tmpl.v",
                    premap_commands = (
                        "simplemap t:$dff t:$dffe t:$dffsr",
                        "dffsr2dff",
                        "dff2dffe",
                        "opt -full",
                        ),
                    parameters = {
                        "ENABLE_CE": {"init": "1'b0", "cfg": cls._PrimitiveParameter(0, 1)},
                        "ENABLE_SR": {"init": "1'b0", "cfg": cls._PrimitiveParameter(1, 1)},
                        "SR_SET": {"init": "1'b0", "cfg": cls._PrimitiveParameter(2, 1)},
                        },
                    cfg_bitcount = 3)
            clk = mdff.create_clock("clk")
            p = []
            p.append(mdff.create_input("D", 1, clock = "clk"))
            p.append(mdff.create_output("Q", 1, clock = "clk"))
            p.append(mdff.create_input("ce", 1, clock = "clk"))
            p.append(mdff.create_input("sr", 1, clock = "clk"))
            NetUtils.connect(clk, p, fully = True)

            # logical view
            mdff = mdff.create_logical_counterpart(
                    cfg_bitcount = 3,
                    verilog_template = "mdff.tmpl.v")
            cls._get_or_create_cfg_ports(mdff._module, cfg_width)
            mdff.commit()

        # register adder
        if "adder" not in dont_add_primitive:
            # user view
            adder = context.create_primitive("adder",
                    techmap_template = "adder.techmap.tmpl.v",
                    parameters = {
                        "CIN_FABRIC": {"init": "1'b0", "cfg": cls._PrimitiveParameter(0, 1)},
                        },
                    cfg_bitcount = 1)
            i, o = [], []
            o.append(adder.create_output("cout", 1))
            o.append(adder.create_output("s", 1))
            o.append(adder.create_output("cout_fabric", 1))
            i.append(adder.create_input("a", 1, vpr_combinational_sinks = ("cout", "s", "cout_fabric")))
            i.append(adder.create_input("b", 1, vpr_combinational_sinks = ("cout", "s", "cout_fabric")))
            i.append(adder.create_input("cin", 1, vpr_combinational_sinks = ("cout", "s", "cout_fabric")))
            i.append(adder.create_input("cin_fabric", 1, vpr_combinational_sinks = ("cout", "s", "cout_fabric")))
            NetUtils.connect(i, o, fully = True)

            # logical view
            adder = adder.create_logical_counterpart(
                    cfg_bitcount = 1,
                    verilog_template = "adder.tmpl.v")
            cls._get_or_create_cfg_ports(adder._module, cfg_width)
            adder.commit()

#         # register simplified stratix-IV FLE
#         if ("lut5" not in dont_add_primitive and
#                 "lut6" not in dont_add_primitive and
#                 "adder" not in dont_add_primitive and
#                 "flipflop" not in dont_add_primitive and
#                 "fle6" not in dont_add_primitive):
#             # user view
#             fle6 = context.create_multimode('fle6')
#             fle6.create_clock("clk")
#             fle6.create_input("in", 6)
#             fle6.create_input("cin", 1)
#             fle6.create_output("out", 2)
#             fle6.create_output("cout", 1)
# 
#             if True:
#                 mode = fle6.create_mode("lut6x1")
#                 lut = mode.instantiate(context.primitives["lut6"], "lut")
#                 ff = mode.instantiate(context.primitives["flipflop"], "ff")
#                 mode.connect(mode.ports["clk"], ff.pins["clk"])
#                 mode.connect(mode.ports["in"], lut.pins["in"])
#                 mode.connect(lut.pins["out"], ff.pins["D"], pack_patterns = ["lut6_dff"])
#                 mode.connect(lut.pins["out"], mode.ports["out"][0])
#                 mode.connect(ff.pins["Q"], mode.ports["out"][0])
#                 mode.commit()
# 
#             if True:
#                 mode = fle6.create_mode("lut5x2")
#                 for i, suffix in enumerate(["A", "B"]):
#                     lut = mode.instantiate(context.primitives["lut5"], "lut" + suffix)
#                     ff = mode.instantiate(context.primitives["flipflop"], "ff" + suffix)
#                     mode.connect(mode.ports["clk"], ff.pins["clk"])
#                     mode.connect(mode.ports["in"][0:5], lut.pins["in"])
#                     mode.connect(lut.pins["out"], ff.pins["D"], pack_patterns = ["lut5" + suffix + "_dff"])
#                     mode.connect(lut.pins["out"], mode.ports["out"][i])
#                     mode.connect(ff.pins["Q"], mode.ports["out"][i])
#                 mode.commit()
# 
#             if True:
#                 mode = fle6.create_mode("arithmetic")
#                 adder = mode.instantiate(context.primitives["adder"], "fa")
#                 for p in ("a", "b"):
#                     lut = mode.instantiate(context.primitives["lut5"], "lut" + p.upper())
#                     mode.connect(mode.ports["in"][0:5], lut.pins["in"])
#                     mode.connect(lut.pins["out"], adder.pins[p], pack_patterns = ["carrychain"])
#                 mode.connect(mode.ports["cin"], adder.pins["cin"], pack_patterns = ["carrychain"])
#                 mode.connect(mode.ports["in"][5], adder.pins["cin_fabric"])
#                 for i, (p, suffix) in enumerate([("s", "A"), ("cout_fabric", "B")]):
#                     ff = mode.instantiate(context.primitives["flipflop"], "ff" + suffix)
#                     mode.connect(mode.ports["clk"], ff.pins["clk"])
#                     mode.connect(adder.pins[p], ff.pins["D"], pack_patterns = ["carrychain"])
#                     mode.connect(adder.pins[p], mode.ports["out"][i])
#                     mode.connect(ff.pins["Q"], mode.ports["out"][i])
#                 mode.connect(adder.pins["cout"], mode.ports["cout"], pack_patterns = ["carrychain"])
#                 mode.commit()
# 
#             fle6 = fle6.create_logical_counterpart(
#                     cfg_bitcount = 69, verilog_template = "fle6.tmpl.v")
# 
#             # configuration ports
#             fle6.create_cfg_port('cfg_clk', 1, PortDirection.input_, is_clock = True)
#             fle6.create_cfg_port('cfg_e', 1, PortDirection.input_, clock = 'cfg_clk')
#             fle6.create_cfg_port('cfg_i', cfg_width, PortDirection.input_, clock = 'cfg_clk')
#             fle6.create_cfg_port('cfg_o', cfg_width, PortDirection.output, clock = 'cfg_clk')
# 
#             if True:
#                 mode = fle6.edit_mode("lut6x1", cfg_mode_selection = tuple())
#                 lut = mode.instantiate(context._database[ModuleView.logical, 'lut6'], "lut")
#                 ff = mode.instantiate(context._database[ModuleView.logical, 'flipflop'], "ff")
#                 sw = mode.instantiate(context.switch_database.get_switch(2, mode), "_sw_out_0")
#                 mode.connect(mode.ports["clk"], ff.pins["clk"])
#                 mode.connect(mode.ports["in"], lut.pins["in"])
#                 mode.connect(lut.pins["out"], ff.pins["D"])
#                 mode.connect(lut.pins["out"], sw.pins["i"][0])
#                 mode.connect(ff.pins["Q"], sw.pins["i"][1])
#                 mode.connect(sw.pins["o"], mode.ports["out"][0])
#                 lut.cfg_bitoffset = 0
#                 sw.cfg_bitoffset = 64
#                 mode.commit()
# 
#             if True:
#                 mode = fle6.edit_mode("lut5x2", cfg_mode_selection = (66, ))
#                 for i, suffix in enumerate(["A", "B"]):
#                     lut = mode.instantiate(context._database[ModuleView.logical, "lut5"], "lut" + suffix)
#                     ff = mode.instantiate(context._database[ModuleView.logical, "flipflop"], "ff" + suffix)
#                     sw = mode.instantiate(context.switch_database.get_switch(2, mode), "_sw_out_" + str(i))
#                     mode.connect(mode.ports["clk"], ff.pins["clk"])
#                     mode.connect(mode.ports["in"][0:5], lut.pins["in"])
#                     mode.connect(lut.pins["out"], ff.pins["D"])
#                     mode.connect(lut.pins["out"], sw.pins["i"][0])
#                     mode.connect(ff.pins["Q"], sw.pins["i"][1])
#                     mode.connect(sw.pins["o"], mode.ports["out"][i])
#                     lut.cfg_bitoffset = 32 * i
#                     sw.cfg_bitoffset = 64 + i
#                 mode.commit()
# 
#             if True:
#                 mode = fle6.edit_mode("arithmetic", cfg_mode_selection = (66, 67))
#                 adder = mode.instantiate(context._database[ModuleView.logical, "adder"], "fa")
#                 for i, p in enumerate(["a", "b"]):
#                     lut = mode.instantiate(context._database[ModuleView.logical, "lut5"], "lut" + p.upper())
#                     mode.connect(mode.ports["in"][0:5], lut.pins["in"])
#                     mode.connect(lut.pins["out"], adder.pins[p])
#                     lut.cfg_bitoffset = 32 * i
#                 mode.connect(mode.ports["cin"], adder.pins["cin"])
#                 mode.connect(mode.ports["in"][5], adder.pins["cin_fabric"])
#                 for i, (p, suffix) in enumerate([("s", "A"), ("cout_fabric", "B")]):
#                     ff = mode.instantiate(context._database[ModuleView.logical, "flipflop"], "ff" + suffix)
#                     sw = mode.instantiate(context.switch_database.get_switch(2, mode), "_sw_out_" + str(i))
#                     mode.connect(mode.ports["clk"], ff.pins["clk"])
#                     mode.connect(adder.pins[p], ff.pins["D"])
#                     mode.connect(adder.pins[p], sw.pins["i"][0])
#                     mode.connect(ff.pins["Q"], sw.pins["i"][1])
#                     mode.connect(sw.pins["o"], mode.ports["out"][i])
#                     sw.cfg_bitoffset = 64 + i
#                 mode.connect(adder.pins["cout"], mode.ports["cout"])
#                 adder.cfg_bitoffset = 68
#                 mode.commit()
# 
#             fle6.commit()

        return context

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        r = FileRenderer()
        r.template_search_paths.insert(0, ADDITIONAL_TEMPLATE_SEARCH_PATH)
        r.template_search_paths.extend(additional_template_search_paths)
        return r

    @classmethod
    def complete_scanchain(cls, context, logical_module, *, iter_instances = lambda m: itervalues(m.instances)):
        """Complete the scanchain."""
        module = logical_module
        # special process needed for IO blocks (output enable)
        if module.module_class.is_io_block:
            oe = module.ports.get(IOType.oe)
            if oe is not None:
                inst = ModuleUtils.instantiate(module, context.database[ModuleView.logical, 'cfg_bit'], '_cfg_oe')
                NetUtils.connect(inst.pins["cfg_d"], oe)
        # connecting scanchain ports
        cfg_bitoffset = 0
        cfg_clk, cfg_e, cfg_i, cfg_o = (None, ) * 4
        for instance in iter_instances(module):
            if instance.model.module_class not in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.cfg):
                if not hasattr(instance.model, 'cfg_bitcount'):
                    cls.complete_scanchain(context, instance.model, iter_instances = iter_instances)
            # enable pin
            inst_cfg_e = instance.pins.get('cfg_e')
            if inst_cfg_e is None:
                continue
            cfg_e = cls._get_or_create_cfg_ports(module, context.cfg_width, True)
            NetUtils.connect(cfg_e, inst_cfg_e)
            # actual bitstream loading pin
            inst_cfg_i = instance.pins.get('cfg_i')
            if inst_cfg_i is None:
                continue
            assert len(inst_cfg_i) == context.cfg_width
            if cfg_clk is None:
                cfg_clk, cfg_e, cfg_i, cfg_o = cls._get_or_create_cfg_ports(module, context.cfg_width)
            instance.cfg_bitoffset = cfg_bitoffset
            NetUtils.connect(cfg_clk, instance.pins['cfg_clk'])
            NetUtils.connect(cfg_i, inst_cfg_i)
            cfg_i = instance.pins['cfg_o']
            cfg_bitoffset += instance.model.cfg_bitcount
        if cfg_i is not None:
            NetUtils.connect(cfg_i, cfg_o)
        module.cfg_bitcount = cfg_bitoffset
        if module.key == context.top.key:
            if not hasattr(context.summary, "scanchain"):
                context.summary.scanchain = {}
            context.summary.scanchain["bitstream_size"] = cfg_bitoffset

    @classmethod
    def annotate_user_view(cls, context, user_module = None, *, _annotated = None):
        """Annotate configuration data to the user view."""
        module = uno(user_module, context.top)
        logical = context.database[ModuleView.logical, module.key]
        _annotated = uno(_annotated, set())
        # 1. annotate user instances
        for instance in itervalues(module.instances):
            # 1.1 special process needed for IO blocks (output enable)
            if module.module_class.is_io_block and instance.key == "io":
                if instance.model.primitive_class.is_multimode:
                    instance.cfg_bitoffset = logical.instances["_cfg_oe"].cfg_bitoffset
                continue
            # 1.2 for all other instances, look for the corresponding logical instance and annotate cfg_bitoffset
            logical_instance = logical.instances[instance.key]
            if hasattr(logical_instance, "cfg_bitoffset"):
                instance.cfg_bitoffset = logical_instance.cfg_bitoffset
                if not (instance.model.module_class.is_primitive or instance.model.key in _annotated):
                    _annotated.add(instance.model.key)
                    cls.annotate_user_view(context, instance.model, _annotated = _annotated)
        # 2. annotate multi-source connections
        if not module._allow_multisource:
            return
        assert not module._coalesce_connections and not logical._coalesce_connections
        assert not logical._allow_multisource
        nets = None
        if module.module_class.is_io_block:
            nets = chain(
                    iter(port for port in itervalues(logical.ports)
                        if not (port.net_class.is_cfg or port.key is IOType.oe)),
                    iter(pin for inst_key in module.instances if inst_key != "io"
                        for pin in itervalues(logical.instances[inst_key].pins)))
        else:
            nets = chain(
                    iter(port for port in itervalues(logical.ports) if not port.net_class.is_cfg),
                    iter(pin for inst_key in module.instances
                        for pin in itervalues(logical.instances[inst_key].pins)))
        for logical_bus in nets:
            if not logical_bus.is_sink:
                continue
            for logical_sink in logical_bus:
                user_tail = TranslationPass._l2u(logical, NetUtils._reference(logical_sink))
                if user_tail not in module._conn_graph:
                    continue
                    # raise PRGAInternalError("No user-counterpart found for logical net {}".format(logical_sink))
                stack = [(logical_sink, tuple())]
                while stack:
                    head, cfg_bits = stack.pop()
                    predecessors = tuple(logical._conn_graph.predecessors(NetUtils._reference(head)))
                    if len(predecessors) == 0:
                        continue
                    elif len(predecessors) > 1:
                        raise PRGAInternalError("Multiple sources found for logical net{}".format(head))
                    user_head = TranslationPass._l2u(logical, predecessors[0])
                    if user_head in module._conn_graph:
                        edge = module._conn_graph.edges.get( (user_head, user_tail) )
                        if edge is None:
                            raise PRGAInternalError(("No connection found from user net {} to {}. "
                                "Logical path exists from {} to {}")
                                .format( NetUtils._dereference(module, user_head),
                                    NetUtils._dereference(module, user_tail),
                                    NetUtils._dereference(logical, predecessors[0]),
                                    logical_sink ))
                        edge["cfg_bits"] = cfg_bits
                        continue
                    prev = NetUtils._dereference(logical, predecessors[0])
                    if prev.net_type.is_const:
                        continue
                    elif prev.net_type.is_port or not prev.bus.model.net_class.is_switch:
                        raise PRGAInternalError("No user-counterpart found for logical net {}".format(prev))
                    switch = prev.bus.instance
                    for idx, input_ in enumerate(switch.pins["i"]):
                        this_cfg_bits = cfg_bits
                        for digit in range(idx.bit_length()):
                            if (idx & (1 << digit)):
                                this_cfg_bits += (switch.cfg_bitoffset + digit, )
                        stack.append( (input_, this_cfg_bits) )
