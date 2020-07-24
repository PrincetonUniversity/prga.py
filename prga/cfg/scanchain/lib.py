# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...core.common import NetClass, ModuleClass, ModuleView, IOType
from ...core.context import Context
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...passes.base import AbstractPass
from ...passes.translation import AbstractSwitchDatabase, TranslationPass
from ...passes.vpr import FASMDelegate
from ...renderer.renderer import FileRenderer
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
class ScanchainSwitchDatabase(Object, AbstractSwitchDatabase):
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
        switch = Module('sw' + str(width), view = ModuleView.logical, key = key,
                module_class = ModuleClass.switch, cfg_bitcount = cfg_bitcount,
                allow_multisource = True, verilog_template = "switch.tmpl.v")
        # switch inputs/outputs
        i = ModuleUtils.create_port(switch, 'i', width, PortDirection.input_, net_class = NetClass.switch)
        o = ModuleUtils.create_port(switch, 'o', 1, PortDirection.output, net_class = NetClass.switch)
        NetUtils.connect(i, o, fully = True)
        ModuleUtils.instantiate(switch, Scanchain.get_cfg_data_cell(self.context, cfg_bitcount), "i_cfg_data")
        # configuration circuits
        self.entry._get_or_create_cfg_ports(switch, self.cfg_width)
        return self.context._database.setdefault((ModuleView.logical, key), switch)

    def get_obuf(self):
        try:
            return self.context.database[ModuleView.logical, "cfg_obuf"]
        except KeyError:
            return None

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
                if (offset := getattr(i, "cfg_bitoffset", None)) is None:
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
        if instance.model.module_class.is_primitive and instance.model.primitive_class.is_lut:
            return ''
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
        if (cfg_bitoffset := self._instance_bitoffset(instance)) is None:
            return tuple()
        retval = []
        for subtile, blkinst in enumerate(instance.model._instances.subtiles):
            if (inst_bitoffset := getattr(blkinst, 'cfg_bitoffset', None)) is None:
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

    class PrimitiveParameter(namedtuple("PrimitiveParameter", "cfg_bitoffset cfg_bitcount")):
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
                if module.is_cell:
                    NetUtils.connect(cfg_clk, itervalues(ports), fully = True)
                ports["cfg_clk"] = cfg_clk
                return ports

    @classmethod
    def _register_primitives(cls, context, cfg_width, dont_add_primitive, dont_add_logical_primitive):
        if not isinstance(dont_add_primitive, set):
            dont_add_primitive = set(iter(dont_add_primitive))

        if not isinstance(dont_add_logical_primitive, set):
            dont_add_logical_primitive = set(iter(dont_add_logical_primitive)) | dont_add_primitive

        # modify dual-mode I/O
        if True:
            iopad = context.primitives["iopad"]
            iopad.cfg_bitcount = 1
            iopad.modes["inpad"].cfg_mode_selection = tuple()
            iopad.modes["outpad"].cfg_mode_selection = (0, )

        # register chain delimiter
        if "cfg_delim" not in dont_add_logical_primitive:
            delim = Module("cfg_delim",
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.cfg,
                    verilog_template = "cfg_delim.tmpl.v")
            cls._get_or_create_cfg_ports(delim, cfg_width, we_o = True)
            context._database[ModuleView.logical, "cfg_delim"] = delim
        
        # register enable register
        if "cfg_e_reg" not in dont_add_logical_primitive:
            ereg = Module("cfg_e_reg",
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.cfg,
                    verilog_template = "cfg_e_reg.tmpl.v")
            clk = ModuleUtils.create_port(ereg, "cfg_clk", 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.cfg)
            ei = ModuleUtils.create_port(ereg, "cfg_e_i", 1, PortDirection.input_,
                    net_class = NetClass.cfg)
            eo = ModuleUtils.create_port(ereg, "cfg_e", 1, PortDirection.output,
                    net_class = NetClass.cfg)
            NetUtils.connect(clk, [ei, eo], fully = True)
            context._database[ModuleView.logical, "cfg_e_reg"] = ereg

        # register OBUF
        if "cfg_obuf" not in dont_add_logical_primitive:
            obuf = Module("cfg_obuf",
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    cfg_bitcount = 1,
                    verilog_template = "cfg_obuf.tmpl.v")

            # logical ports
            oe = ModuleUtils.create_port(obuf, "oe", 1, PortDirection.output, net_class = NetClass.io)
            opin_i = ModuleUtils.create_port(obuf, "opin_i", 1, PortDirection.input_, net_class = NetClass.user)
            opin_o = ModuleUtils.create_port(obuf, "opin_o", 1, PortDirection.output, net_class = NetClass.io)
            NetUtils.connect( opin_i, opin_o, fully = True )

            # configuration data
            ModuleUtils.instantiate(obuf, cls.get_cfg_data_cell(context, 1), "i_cfg_data")

            # configuration ports
            cls._get_or_create_cfg_ports(obuf, cfg_width)
            context._database[ModuleView.logical, obuf.key] = obuf

        # register luts
        for i in range(2, 9):
            name = "lut" + str(i)
            if name in dont_add_logical_primitive:
                continue
            lut = Module(name,
                    view = ModuleView.logical,
                    allow_multisource = True,
                    module_class = ModuleClass.primitive,
                    cfg_bitcount = 2 ** i,
                    verilog_template = "lut.tmpl.v")
            # user ports
            in_ = ModuleUtils.create_port(lut, 'in', i, PortDirection.input_, net_class = NetClass.user)
            out = ModuleUtils.create_port(lut, 'out', 1, PortDirection.output, net_class = NetClass.user)
            NetUtils.connect(in_, out, fully = True)

            # configuration data
            ModuleUtils.instantiate(lut, cls.get_cfg_data_cell(context, 2 ** i), "i_cfg_data")

            # configuration ports
            cls._get_or_create_cfg_ports(lut, cfg_width)
            context._database[ModuleView.logical, lut.key] = lut

            # modify built-in LUT
            context._database[ModuleView.user, lut.key].cfg_bitcount = 2 ** i

        # register flipflops
        if "flipflop" not in dont_add_logical_primitive:
            flipflop = Module('flipflop',
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.primitive,
                    verilog_template = "flipflop.tmpl.v")
            clk = ModuleUtils.create_port(flipflop, 'clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.user)
            D = ModuleUtils.create_port(flipflop, 'D', 1, PortDirection.input_,
                    net_class = NetClass.user)
            Q = ModuleUtils.create_port(flipflop, 'Q', 1, PortDirection.output,
                    net_class = NetClass.user)
            NetUtils.connect(clk, [D, Q], fully = True)

            # configuration ports
            cls._get_or_create_cfg_ports(flipflop, cfg_width, enable_only = True)
            context._database[ModuleView.logical, flipflop.key] = flipflop

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
                fraclut6 = fraclut6.build_logical_counterpart(not_cell = True, allow_multisource = True,
                        cfg_bitcount = 65, verilog_template = "fraclut6.tmpl.v")

                # combinational paths
                NetUtils.connect(fraclut6.ports["in"], fraclut6.ports["o6"], fully = True)
                NetUtils.connect(fraclut6.ports["in"][:5], fraclut6.ports["o5"], fully = True)

                # configuration data
                ModuleUtils.instantiate(fraclut6.module, cls.get_cfg_data_cell(context, 65), "i_cfg_data")

                # configuration ports
                cls._get_or_create_cfg_ports(fraclut6._module, cfg_width)

            fraclut6.commit()

        # register multi-mode flipflop
        if "mdff" not in dont_add_primitive:
            # user view
            mdff = context.build_primitive("mdff",
                    techmap_template = "mdff.techmap.tmpl.v",
                    premap_commands = (
                        "simplemap t:$dff t:$dffe t:$dffsr",
                        "dffsr2dff",
                        "dff2dffe",
                        "opt -full",
                        ),
                    parameters = {
                        "ENABLE_CE": {"init": "1'b0", "cfg": cls.PrimitiveParameter(0, 1)},
                        "ENABLE_SR": {"init": "1'b0", "cfg": cls.PrimitiveParameter(1, 1)},
                        "SR_SET": {"init": "1'b0", "cfg": cls.PrimitiveParameter(2, 1)},
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
            if "mdff" not in dont_add_logical_primitive:
                mdff = mdff.build_logical_counterpart(not_cell = True, allow_multisource = True,
                        cfg_bitcount = 3, verilog_template = "mdff.tmpl.v")
                ModuleUtils.instantiate(mdff.module, cls.get_cfg_data_cell(context, 3), "i_cfg_data")
                cls._get_or_create_cfg_ports(mdff._module, cfg_width)
            
            mdff.commit()

        # register adder
        if "adder" not in dont_add_primitive:
            # user view
            adder = context.build_primitive("adder",
                    techmap_template = "adder.techmap.tmpl.v",
                    parameters = {
                        "CIN_FABRIC": {"init": "1'b0", "cfg": cls.PrimitiveParameter(0, 1)},
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
            if "adder" not in dont_add_logical_primitive:
                adder = adder.build_logical_counterpart(not_cell = True, allow_multisource = True,
                        cfg_bitcount = 1, verilog_template = "adder.tmpl.v")
                ModuleUtils.instantiate(adder.module, cls.get_cfg_data_cell(context, 1), "i_cfg_data")
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
                fle6 = fle6.build_logical_counterpart(not_cell = True, allow_multisource = True,
                        cfg_bitcount = 69, verilog_template = "fle6.tmpl.v")
                ModuleUtils.instantiate(fle6.module, cls.get_cfg_data_cell(context, 69), "i_cfg_data")

                # combinational paths
                NetUtils.connect([fle6.ports["in"], fle6.ports["cin"]], [fle6.ports["out"], fle6.ports["cout"]],
                        fully = True)
                NetUtils.connect(fle6.ports["clk"], fle6.ports["out"], fully = True)

                # configuration ports
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
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.cfg,
                    verilog_template = "cfg_data.tmpl.v",
                    key = key,
                    cfg_bitcount = data_width)
            cfg_clk = cls._get_or_create_cfg_ports(module, context.summary.scanchain["cfg_width"])["cfg_clk"]
            cfg_d = ModuleUtils.create_port(module, "cfg_d", data_width, PortDirection.output,
                    net_class = NetClass.cfg)
            NetUtils.connect(cfg_clk, cfg_d, fully = True)
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
        context._fasm_delegate = ScanchainFASMDelegate(context)
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
        # special processing needed for IO blocks (output enable)
        if module.module_class.is_io_block:
            if (oe := module.ports.get(IOType.oe)) is None:
                pass
            elif (obuf := module.instances.get("_obuf")) is None:
                inst = ModuleUtils.instantiate(module,
                        cls.get_cfg_data_cell(context, 1),
                        '_obuf')
                NetUtils.connect(inst.pins["cfg_d"], oe)
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
                            "_cfg_ereg")
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
                            "_cfg_filler_inst")
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
                        "_cfg_delim")
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
            # 1.1 special process needed for IO blocks (output enable)
            if module.module_class.is_io_block and instance.key == "io":
                if instance.model.primitive_class.is_multimode:
                    instance.cfg_bitoffset = logical.instances["_obuf"].cfg_bitoffset
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

    class InjectConfigCircuitry(Object, AbstractPass):
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
