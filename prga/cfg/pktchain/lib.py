# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .protocol import PktchainProtocol
from ..scanchain.lib import Scanchain, ScanchainSwitchDatabase, ScanchainFASMDelegate
from ...core.common import ModuleClass, ModuleView, NetClass, Orientation
from ...core.context import Context
from ...netlist import PortDirection, Const, Module, NetUtils, ModuleUtils
from ...passes.base import AbstractPass
from ...passes.vpr import FASMDelegate
from ...renderer import FileRenderer
from ...integration import Integration
from ...tools.ioplan.ioplan import IOPlanner
from ...util import uno
from ...exception import PRGAInternalError, PRGAAPIError

import os
from collections import namedtuple
from itertools import chain, product

import logging
_logger = logging.getLogger(__name__)

__all__ = ['Pktchain']

ADDITIONAL_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class PktchainFASMDelegate(ScanchainFASMDelegate):
    """FASM delegate for pktchain configuration circuitry.
    
    Args:
        context (`Context`):
    """

    def _instance_chainoffset(self, instance):
        chain, ypos = 0, 0
        for i in instance.hierarchy:
            chain, ypos_inc = i.cfg_chainoffsets[chain]
            ypos += ypos_inc
        return chain, ypos

    def fasm_prefix_for_tile(self, instance):
        if (tile_bitoffset := getattr(instance.hierarchy[0], "cfg_bitoffset", None)) is None:
            return tuple()
        retval = []
        for subtile, blkinst in iteritems(instance.model.instances):
            if not isinstance(subtile, int):
                continue
            elif subtile >= len(retval):
                retval.extend(None for _ in range(subtile - len(retval) + 1))
            if (inst_bitoffset := getattr(blkinst, "cfg_bitoffset", None)) is not None:
                retval[subtile] = 'x{}.y{}.b{}'.format(*self._instance_chainoffset(instance),
                        tile_bitoffset + inst_bitoffset)
        return tuple(retval)

    def fasm_features_for_interblock_switch(self, source, sink, hierarchy = None):
        inst_for_chain, inst_for_offset = None, None
        if hierarchy.model.module_class.is_connection_box:
            inst_for_chain = hierarchy._shrink_hierarchy(low = 1)
            inst_for_offset = hierarchy._shrink_hierarchy(high = 2)
        else:
            inst_for_chain = hierarchy
            inst_for_offset = hierarchy.hierarchy[0]
        return tuple( 'x{}.y{}.{}'.format(*self._instance_chainoffset(inst_for_chain), f)
                for f in self._features_for_path(source, sink, inst_for_offset) )

# ----------------------------------------------------------------------------
# -- Pktchain Configuration Circuitry Main Entry -----------------------------
# ----------------------------------------------------------------------------
class Pktchain(Scanchain):
    """Packetized configuration circuitry entry point."""

    @classmethod
    def _phit_port_name(cls, type_, chain):
        return "cfg_{}_c{}".format(type_, chain)

    @classmethod
    def _connect_common_cfg_ports(cls, module, instance):
        # clock
        if NetUtils.get_source(instance.pins["cfg_clk"], return_none_if_unconnected = True) is None:
            if (cfg_clk := module.ports.get("cfg_clk")) is None:
                cfg_clk = ModuleUtils.create_port(module, "cfg_clk", 1, PortDirection.input_,
                        is_clock = True, net_class = NetClass.cfg)
            NetUtils.connect(cfg_clk, instance.pins["cfg_clk"])
        # enable
        if (inst_cfg_e := instance.pins.get("cfg_e")) is not None:
            if NetUtils.get_source(inst_cfg_e, return_none_if_unconnected = True) is None:
                if (cfg_e := module.ports.get("cfg_e")) is None:
                    cfg_e = ModuleUtils.create_port(module, "cfg_e", 1, PortDirection.input_,
                            net_class = NetClass.cfg)
                NetUtils.connect(cfg_e, inst_cfg_e)
        # reset
        if (inst_cfg_rst := instance.pins.get("cfg_rst")) is not None:
            if NetUtils.get_source(inst_cfg_rst, return_none_if_unconnected = True) is None:
                if (cfg_rst := module.ports.get("cfg_rst")) is None:
                    cfg_rst = ModuleUtils.create_port(module, "cfg_rst", 1, PortDirection.input_,
                            net_class = NetClass.cfg)
                NetUtils.connect(cfg_rst, inst_cfg_rst)

    @classmethod
    def _get_or_create_fifo_intf(cls, module, phit_width, chain = 0):
        try:
            return {type_: module.ports[cls._phit_port_name(type_, chain)]
                    for type_ in ("phit_i_full", "phit_i_wr", "phit_i", "phit_o_full", "phit_o_wr", "phit_o")}
        except KeyError:
            ports = {}
            ports["phit_i_full"] = ModuleUtils.create_port(module, cls._phit_port_name("phit_i_full", chain), 1,
                    PortDirection.output, net_class = NetClass.cfg)
            ports["phit_i_wr"] = ModuleUtils.create_port(module, cls._phit_port_name("phit_i_wr", chain), 1,
                    PortDirection.input_, net_class = NetClass.cfg)
            ports["phit_i"] = ModuleUtils.create_port(module, cls._phit_port_name("phit_i", chain), phit_width,
                    PortDirection.input_, net_class = NetClass.cfg)
            ports["phit_o_full"] = ModuleUtils.create_port(module, cls._phit_port_name("phit_o_full", chain), 1,
                    PortDirection.input_, net_class = NetClass.cfg)
            ports["phit_o_wr"] = ModuleUtils.create_port(module, cls._phit_port_name("phit_o_wr", chain), 1,
                    PortDirection.output, net_class = NetClass.cfg)
            ports["phit_o"] = ModuleUtils.create_port(module, cls._phit_port_name("phit_o", chain), phit_width,
                    PortDirection.output, net_class = NetClass.cfg)
            return ports

    @classmethod
    def _build_pktchain_backbone(cls, context, xpos = None, ypos = None, *, top = "backbone"):
        # top-level
        phit_width = context.summary.pktchain["fabric"]["phit_width"]
        module = Module(top)
        ports = {
                "clk": ModuleUtils.create_port(module, "clk", 1, PortDirection.input_, is_clock = True),
                "rst": ModuleUtils.create_port(module, "rst", 1, PortDirection.input_),
                "phit_i_full": ModuleUtils.create_port(module, "phit_i_full", 1, PortDirection.output),
                "phit_i_wr": ModuleUtils.create_port(module, "phit_i_wr", 1, PortDirection.input_),
                "phit_i": ModuleUtils.create_port(module, "phit_i", phit_width, PortDirection.input_),
                "phit_o_full": ModuleUtils.create_port(module, "phit_o_full", 1, PortDirection.input_),
                "phit_o_wr": ModuleUtils.create_port(module, "phit_o_wr", 1, PortDirection.output),
                "phit_o": ModuleUtils.create_port(module, "phit_o", phit_width, PortDirection.output),
                }
        for x in range(uno(xpos, context.summary.pktchain["fabric"]["x_tiles"])):
            i = ModuleUtils.instantiate(module,
                    context.database[ModuleView.logical, "pktchain_dispatcher"],
                    "i_cfg_dispatcher_x{}".format(x))
            NetUtils.connect(ports["clk"], i.pins["cfg_clk"])
            NetUtils.connect(ports["rst"], i.pins["cfg_rst"])
            NetUtils.connect(i.pins["phit_i_full"], ports["phit_i_full"])
            NetUtils.connect(ports["phit_i_wr"], i.pins["phit_i_wr"])
            NetUtils.connect(ports["phit_i"], i.pins["phit_i"])
            ports.update({
                "phit_i_full": i.pins["phit_ox_full"],
                "phit_i_wr": i.pins["phit_ox_wr"],
                "phit_i": i.pins["phit_ox"],
                })
            chain = {
                    "full": i.pins["phit_oy_full"],
                    "wr": i.pins["phit_oy_wr"],
                    "phit": i.pins["phit_oy"],
                    }
            for y in range(uno(ypos, context.summary.pktchain["fabric"]["y_tiles"])):
                i = ModuleUtils.instantiate(module,
                        context.database[ModuleView.logical, "pktchain_router"],
                        "i_cfg_router_x{}y{}".format(x, y))
                NetUtils.connect(ports["clk"], i.pins["cfg_clk"])
                NetUtils.connect(ports["rst"], i.pins["cfg_rst"])
                NetUtils.connect(i.pins["phit_i_full"], chain["full"])
                NetUtils.connect(chain["wr"], i.pins["phit_i_wr"])
                NetUtils.connect(chain["phit"], i.pins["phit_i"])
                NetUtils.connect(i.pins["cfg_we_o"], i.pins["cfg_we_i"])
                NetUtils.connect(i.pins["cfg_o"], i.pins["cfg_i"])
                chain.update({ "full": i.pins["phit_o_full"],
                    "wr": i.pins["phit_o_wr"],
                    "phit": i.pins["phit_o"], })
            i = ModuleUtils.instantiate(module,
                    context.database[ModuleView.logical, "pktchain_gatherer"],
                    "i_cfg_gatherer_x{}".format(x))
            NetUtils.connect(ports["clk"], i.pins["cfg_clk"])
            NetUtils.connect(ports["rst"], i.pins["cfg_rst"])
            NetUtils.connect(ports["phit_o_full"], i.pins["phit_o_full"])
            NetUtils.connect(i.pins["phit_o_wr"], ports["phit_o_wr"])
            NetUtils.connect(i.pins["phit_o"], ports["phit_o"])
            NetUtils.connect(i.pins["phit_iy_full"], chain["full"])
            NetUtils.connect(chain["wr"], i.pins["phit_iy_wr"])
            NetUtils.connect(chain["phit"], i.pins["phit_iy"])
            ports.update({
                "phit_o_full": i.pins["phit_ix_full"],
                "phit_o_wr": i.pins["phit_ix_wr"],
                "phit_o": i.pins["phit_ix"],
                })
        return module

    @classmethod
    def _register_primitives(cls, context, phit_width, cfg_width, dont_add_primitive, dont_add_logical_primitive):
        if not isinstance(dont_add_primitive, set):
            dont_add_primitive = set(iter(dont_add_primitive))

        if not isinstance(dont_add_logical_primitive, set):
            dont_add_logical_primitive = set(iter(dont_add_logical_primitive)) | dont_add_primitive

        super(Pktchain, cls)._register_primitives(context, cfg_width, dont_add_primitive, dont_add_logical_primitive)

        # register pktchain clasp
        if "pktchain_clasp" not in dont_add_logical_primitive:
            mod = Module("pktchain_clasp",
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    cfg_width = cfg_width,
                    verilog_template = "pktchain_clasp.tmpl.v")
            # we don't need to create ports for this module.
            context._database[ModuleView.logical, "pktchain_clasp"] = mod

        # register pktchain router input fifo
        if "pktchain_frame_assemble" not in dont_add_logical_primitive:
            mod = Module("pktchain_frame_assemble",
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_frame_assemble.tmpl.v")
            # we don't need to create ports for this module.
            # sub-instances (hierarchy-only)
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"], "fifo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo_resizer"], "resizer")
            context._database[ModuleView.logical, "pktchain_frame_assemble"] = mod

        # register pktchain router output fifo
        if "pktchain_frame_disassemble" not in dont_add_logical_primitive:
            mod = Module("pktchain_frame_disassemble",
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_frame_disassemble.tmpl.v")
            # we don't need to create ports for this module.
            # sub-instances (hierarchy-only)
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo_resizer"], "resizer")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"], "fifo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo_adapter"], "adapter")
            context._database[ModuleView.logical, "pktchain_frame_disassemble"] = mod

        # register pktchain router
        if not ({"pktchain_clasp", "pktchain_frame_assemble", "pktchain_frame_disassemble", "pktchain_router"} &
                dont_add_logical_primitive):
            mod = Module("pktchain_router",
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_router.tmpl.v")
            # create a short alias
            mcp = ModuleUtils.create_port
            cfg_clk = mcp(mod, "cfg_clk", 1, PortDirection.input_, is_clock = True, net_class = NetClass.cfg)
            clocked_ports = (
                    mcp(mod, "cfg_rst", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_i_full", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_i_wr", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_i", phit_width, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_o_full", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_o_wr", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_o", phit_width, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "cfg_we_i", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "cfg_i", cfg_width, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "cfg_we_o", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "cfg_o", cfg_width, PortDirection.output, net_class = NetClass.cfg),
                    )
            # NetUtils.connect(cfg_clk, clocked_ports, fully = True)
            # sub-instances
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_clasp"], "clasp")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_assemble"], "ififo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_disassemble"], "ofifo")
            context._database[ModuleView.logical, "pktchain_router"] = mod

        # register pktchain dispatcher (column/row header)
        if not ({"pktchain_dispatcher", "pktchain_frame_assemble", "pktchain_frame_disassemble"} &
                dont_add_logical_primitive):
            mod = Module("pktchain_dispatcher",
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_dispatcher.tmpl.v")
            # create a short alias
            mcp = ModuleUtils.create_port
            cfg_clk = mcp(mod, "cfg_clk", 1, PortDirection.input_, is_clock = True, net_class = NetClass.cfg)
            clocked_ports = (
                    mcp(mod, "cfg_rst", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_i_full", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_i_wr", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_i", phit_width, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_ox_full", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_ox_wr", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_ox", phit_width, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_oy_full", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_oy_wr", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_oy", phit_width, PortDirection.output, net_class = NetClass.cfg),
                    )
            # NetUtils.connect(cfg_clk, clocked_ports, fully = True)
            # sub-instances
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_assemble"], "ififo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_disassemble"], "ox")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_disassemble"], "oy")
            context._database[ModuleView.logical, "pktchain_dispatcher"] = mod

        # register pktchain gatherer (column/row footer)
        if not ({"pktchain_gatherer", "pktchain_frame_assemble", "pktchain_frame_disassemble"} &
                dont_add_logical_primitive):
            mod = Module("pktchain_gatherer",
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_gatherer.tmpl.v")
            # create a short alias
            mcp = ModuleUtils.create_port
            cfg_clk = mcp(mod, "cfg_clk", 1, PortDirection.input_, is_clock = True, net_class = NetClass.cfg)
            clocked_ports = (
                    mcp(mod, "cfg_rst", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_ix_full", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_ix_wr", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_ix", phit_width, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_iy_full", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_iy_wr", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_iy", phit_width, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_o_full", 1, PortDirection.input_, net_class = NetClass.cfg),
                    mcp(mod, "phit_o_wr", 1, PortDirection.output, net_class = NetClass.cfg),
                    mcp(mod, "phit_o", phit_width, PortDirection.output, net_class = NetClass.cfg),
                    )
            # NetUtils.connect(cfg_clk, clocked_ports, fully = True)
            # sub-instances
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_assemble"], "ix")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_assemble"], "iy")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_disassemble"], "ofifo")
            context._database[ModuleView.logical, "pktchain_gatherer"] = mod

        # register pktchain bitstream loader
        if "pktchain_cfg" not in dont_add_logical_primitive:
            mod = context._database[ModuleView.logical, "pktchain_cfg"] = Module("pktchain_cfg", 
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "pktchain_cfg.tmpl.v")

            ModuleUtils.create_port(mod, "clk", 1, PortDirection.input_, is_clock = True)
            Integration._create_intf_cfg(mod, True)
            ModuleUtils.create_port(mod, "cfg_rst", 1, PortDirection.output)
            ModuleUtils.create_port(mod, "cfg_e", 1, PortDirection.output)
            ModuleUtils.create_port(mod, "phit_o_full", 1, PortDirection.input_)
            ModuleUtils.create_port(mod, "phit_o_wr", 1, PortDirection.output)
            ModuleUtils.create_port(mod, "phit_o", phit_width, PortDirection.output)
            ModuleUtils.create_port(mod, "phit_i_full", 1, PortDirection.output)
            ModuleUtils.create_port(mod, "phit_i_wr", 1, PortDirection.input_)
            ModuleUtils.create_port(mod, "phit_i", phit_width, PortDirection.input_)

            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"], "i_rawq")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo_resizer"], "i_resizer")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_ram_1r1w"], "i_tile_status")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_assemble"], "i_brespq")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_disassemble"], "i_frameq")

    @classmethod
    def _complete_pktchain_leaf(cls, context, module, instance, iter_instances,
            cfg_nets, bitoffset, chain, chainoffset):
        cfg_width = context.summary.scanchain["cfg_width"]
        if not hasattr(instance.model, "cfg_bitcount"):
            cls.complete_scanchain(context, instance.model, iter_instances = iter_instances)
        # does this instance have `cfg_e` port?
        if (inst_cfg_e := instance.pins.get("cfg_e")) is None:
            return bitoffset
        NetUtils.connect(cls._get_or_create_cfg_ports(module, cfg_width, enable_only = True), inst_cfg_e)
        # dose this instance have `cfg_i` port?
        if (inst_cfg_i := instance.pins.get("cfg_i")) is None:
            return bitoffset
        elif len(inst_cfg_i) != cfg_width:
            raise PRGAInternalError("Scanchain in {} is not {}-bit wide"
                    .format(instance, cfg_width))
        elif instance.model.cfg_bitcount % cfg_width > 0:
            raise PRGAInternalError("Scanchain in {} is not aligned to cfg_width ({})"
                    .format(instance, cfg_width))
        # connect configuration clock
        if (cfg_clk := module.ports.get("cfg_clk")) is None:
            cfg_clk = ModuleUtils.create_port(module, "cfg_clk", 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.cfg)
        NetUtils.connect(cfg_clk, instance.pins["cfg_clk"])
        # connect chain inputs/outputs
        if "cfg_o" not in cfg_nets:
            cfg_nets["cfg_we"] = instance.pins["cfg_we"]
            cfg_nets["cfg_i"] = instance.pins["cfg_i"]
        else:
            NetUtils.connect(cfg_nets["cfg_o"], instance.pins["cfg_i"])
            NetUtils.connect(cfg_nets["cfg_we_o"], instance.pins["cfg_we"])
        cfg_nets["cfg_o"] = instance.pins["cfg_o"]
        cfg_nets["cfg_we_o"] = instance.pins["cfg_we_o"]
        # update bitoffset settings
        instance.cfg_bitoffset = bitoffset
        instance.cfg_chainoffsets = { 0: (chain, chainoffset) }
        return bitoffset + instance.model.cfg_bitcount

    @classmethod
    def _complete_pktchain_wrap_leaves(cls, context, module,
            chain, secondary_cfg_nets, secondary_chain, scanchain_cfg_nets, scanchain_bitoffset):
        if not scanchain_cfg_nets:
            return 0
        router = ModuleUtils.instantiate(module,
                context.database[ModuleView.logical, "pktchain_router"],
                "_cfg_router_c{}r{}".format(chain, len(secondary_chain)))
        # connect scanchain to router
        if scanchain_cfg_nets:
            NetUtils.connect(router.pins["cfg_we_o"], scanchain_cfg_nets["cfg_we"])
            NetUtils.connect(router.pins["cfg_o"], scanchain_cfg_nets["cfg_i"])
            NetUtils.connect(scanchain_cfg_nets["cfg_we_o"], router.pins["cfg_we_i"])
            NetUtils.connect(scanchain_cfg_nets["cfg_o"], router.pins["cfg_i"])
        else:
            NetUtils.connect(router.pins["cfg_we_o"], router.pins["cfg_we"])
            NetUtils.connect(router.pins["cfg_o"], router.pins["cfg_i"])
        # connect clock and rst
        cls._connect_common_cfg_ports(module, router)
        # connect secondary chain
        if "phit_o" in secondary_cfg_nets:
            NetUtils.connect(secondary_cfg_nets["phit_o"], router.pins["phit_i"])
            NetUtils.connect(secondary_cfg_nets["phit_o_wr"], router.pins["phit_i_wr"])
            NetUtils.connect(router.pins["phit_i_full"], secondary_cfg_nets["phit_o_full"])
        else:
            secondary_cfg_nets.update(
                    phit_i = router.pins["phit_i"],
                    phit_i_wr = router.pins["phit_i_wr"],
                    phit_i_full = router.pins["phit_i_full"])
        secondary_cfg_nets.update(
                phit_o = router.pins["phit_o"],
                phit_o_wr = router.pins["phit_o_wr"],
                phit_o_full = router.pins["phit_o_full"])
        # update chain settings
        _logger.debug("Wrapping up leaf chains ({} bits) as the {}-th router in secondary chain No. {} ({})"
                .format(scanchain_bitoffset, len(secondary_chain) + 1, chain, module))
        secondary_chain.append( scanchain_bitoffset )
        scanchain_cfg_nets.clear()
        return 0

    @classmethod
    def _connect_pktchain_subchain(cls, module, instance, subchain, cfg_nets):
        # enable, clock and reset
        cls._connect_common_cfg_ports(module, instance)
        # connect secondary chain
        if "phit_o" in cfg_nets:
            NetUtils.connect(cfg_nets["phit_o"], instance.pins[cls._phit_port_name("phit_i", subchain)])
            NetUtils.connect(cfg_nets["phit_o_wr"], instance.pins[cls._phit_port_name("phit_i_wr", subchain)])
            NetUtils.connect(instance.pins[cls._phit_port_name("phit_i_full", subchain)], cfg_nets["phit_o_full"])
        else:
            cfg_nets.update(
                    phit_i = instance.pins[cls._phit_port_name("phit_i", subchain)],
                    phit_i_wr = instance.pins[cls._phit_port_name("phit_i_wr", subchain)],
                    phit_i_full = instance.pins[cls._phit_port_name("phit_i_full", subchain)])
        cfg_nets.update(
                phit_o = instance.pins[cls._phit_port_name("phit_o", subchain)],
                phit_o_wr = instance.pins[cls._phit_port_name("phit_o_wr", subchain)],
                phit_o_full = instance.pins[cls._phit_port_name("phit_o_full", subchain)])

    @classmethod
    def _expose_pktchain_secondary_chain(cls, module, cfg_nets, chain):
        NetUtils.connect(ModuleUtils.create_port(module, cls._phit_port_name("phit_i", chain),
            len(cfg_nets["phit_i"]), PortDirection.input_, net_class = NetClass.cfg), cfg_nets["phit_i"])
        NetUtils.connect(ModuleUtils.create_port(module, cls._phit_port_name("phit_i_wr", chain),
            1, PortDirection.input_, net_class = NetClass.cfg), cfg_nets["phit_i_wr"])
        NetUtils.connect(ModuleUtils.create_port(module, cls._phit_port_name("phit_o_full", chain),
            1, PortDirection.input_, net_class = NetClass.cfg), cfg_nets["phit_o_full"])
        NetUtils.connect(cfg_nets["phit_o"], ModuleUtils.create_port(module, cls._phit_port_name("phit_o", chain),
            len(cfg_nets["phit_o"]), PortDirection.output, net_class = NetClass.cfg))
        NetUtils.connect(cfg_nets["phit_o_wr"], ModuleUtils.create_port(module,
            cls._phit_port_name("phit_o_wr", chain), 1, PortDirection.output, net_class = NetClass.cfg))
        NetUtils.connect(cfg_nets["phit_i_full"], ModuleUtils.create_port(module,
            cls._phit_port_name("phit_i_full", chain), 1, PortDirection.output, net_class = NetClass.cfg))
        cfg_nets.clear()

    @classmethod
    def _attach_pktchain_secondary_chain(cls, context, module, dispatcher, gatherer, cfg_nets, chain):
        # create a new dispatcher
        new_dispatcher = ModuleUtils.instantiate(module,
                context.database[ModuleView.logical, "pktchain_dispatcher"],
                "_cfg_dispatcher_c{}".format(chain))
        # connect common ports
        cls._connect_common_cfg_ports(module, new_dispatcher)
        # connect primary chain ports
        if dispatcher is None:
            NetUtils.connect(ModuleUtils.create_port(module, "phit_i_wr", 1, PortDirection.input_,
                net_class = NetClass.cfg), new_dispatcher.pins["phit_i_wr"])
            NetUtils.connect(ModuleUtils.create_port(module, "phit_i", len(new_dispatcher.pins["phit_i"]),
                PortDirection.input_, net_class = NetClass.cfg), new_dispatcher.pins["phit_i"])
            NetUtils.connect(new_dispatcher.pins["phit_i_full"], ModuleUtils.create_port(module, "phit_i_full", 1,
                PortDirection.output, net_class = NetClass.cfg))
        else:
            NetUtils.connect(dispatcher.pins["phit_ox"], new_dispatcher.pins["phit_i"])
            NetUtils.connect(dispatcher.pins["phit_ox_wr"], new_dispatcher.pins["phit_i_wr"])
            NetUtils.connect(new_dispatcher.pins["phit_i_full"], dispatcher.pins["phit_ox_full"])
        # connect secondary chain ports
        NetUtils.connect(new_dispatcher.pins["phit_oy"], cfg_nets["phit_i"])
        NetUtils.connect(new_dispatcher.pins["phit_oy_wr"], cfg_nets["phit_i_wr"])
        NetUtils.connect(cfg_nets["phit_i_full"], new_dispatcher.pins["phit_oy_full"])
        # create a new gatherer
        new_gatherer = ModuleUtils.instantiate(module,
                context.database[ModuleView.logical, "pktchain_gatherer"],
                "_cfg_gatherer_c{}".format(chain))
        # connect common ports
        cls._connect_common_cfg_ports(module, new_gatherer)
        # connect primary chain ports
        if gatherer is None:
            NetUtils.connect(new_gatherer.pins["phit_o"], ModuleUtils.create_port(module, "phit_o",
                len(new_gatherer.pins["phit_o"]), PortDirection.output, net_class = NetClass.cfg))
            NetUtils.connect(new_gatherer.pins["phit_o_wr"], ModuleUtils.create_port(module, "phit_o_wr",
                1, PortDirection.output, net_class = NetClass.cfg))
            NetUtils.connect(ModuleUtils.create_port(module, "phit_o_full", 1, PortDirection.input_,
                net_class = NetClass.cfg), new_gatherer.pins["phit_o_full"])
        else:
            NetUtils.connect(new_gatherer.pins["phit_o"], gatherer.pins["phit_ix"])
            NetUtils.connect(new_gatherer.pins["phit_o_wr"], gatherer.pins["phit_ix_wr"])
            NetUtils.connect(gatherer.pins["phit_ix_full"], new_gatherer.pins["phit_o_full"])
        # connect secondary chain ports
        NetUtils.connect(cfg_nets["phit_o"], new_gatherer.pins["phit_iy"])
        NetUtils.connect(cfg_nets["phit_o_wr"], new_gatherer.pins["phit_iy_wr"])
        NetUtils.connect(new_gatherer.pins["phit_iy_full"], cfg_nets["phit_o_full"])
        cfg_nets.clear()
        return new_dispatcher, new_gatherer

    @classmethod
    def new_context(cls, phit_width = 8, cfg_width = 1, *,
            router_fifo_depth_log2 = 4,
            dont_add_primitive = tuple(), dont_add_logical_primitive = tuple()):
        """Create a new context.

        Args:
            phit_width (:obj:`int`): Data width of the packet-switch network
            cfg_width (:obj:`int`): Width of the scanchain

        Keyword Args:
            router_fifo_depth_log2 (:obj:`int`): Depth of the FIFO of packet-switch network routers
            dont_add_primitive (:obj:`Sequence` [:obj:`str` ]): A list of primitives (user view) and all primitives
                depending on them that are excluded when creating the context
            dont_add_logical_primitive (:obj:`Sequence` [:obj:`str` ]): A list of primitives (logical view) and all
                primitives depending on them that are excluded when creating the context

        Returns:
            `Context`:
        """
        if phit_width not in (1, 2, 4, 8, 16, 32):
            raise PRGAAPIError("Unsupported configuration phit width: {}. Supported values are: [1, 2, 4, 8, 16, 32]"
                    .format(phit_width))
        if cfg_width not in (1, 2, 4):
            raise PRGAAPIError("Unsupported configuration chain width: {}. Supported values are: [1, 2, 4]"
                    .format(cfg_width))
        context = Context("pktchain")
        context.summary.scanchain = {"cfg_width": cfg_width}
        context.summary.pktchain = {
                "fabric": {
                    "phit_width": phit_width,
                    "router_fifo_depth_log2": router_fifo_depth_log2,
                    }
                }
        context._switch_database = ScanchainSwitchDatabase(context, cfg_width, cls)
        context._fasm_delegate = PktchainFASMDelegate(context)
        context._add_verilog_header("pktchain.vh", "include/pktchain.tmpl.vh")
        context._add_verilog_header("pktchain_system.vh", "include/pktchain_system.tmpl.vh")
        # define the programming protocol
        context.summary.pktchain["protocol"] = PktchainProtocol
        cls._register_primitives(context, phit_width, cfg_width, dont_add_primitive, dont_add_logical_primitive)
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
        r = super(Pktchain, cls).new_renderer(tuple(iter(additional_template_search_paths)) +
                (ADDITIONAL_TEMPLATE_SEARCH_PATH, ))
        return r

    @classmethod
    def complete_pktchain(cls, context, logical_module = None, *,
            iter_instances = lambda m: itervalues(m.instances), _not_top = False):
        """Inject pktchain network and routers in ``module``. This method should be called on a non-top level array.

        Args:
            context (`Context`):
            logical_module (`Module`): The module (logical view) in which pktchain network and routers are injected. If
                not specified, the top-level array in ``context`` is selected

        Keyword Args:
            iter_instances (:obj:`Callable` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module. In addition, when the module is an array, ``None`` can be yielded to
                control pktchain router injection. When one ``None`` is yielded, a pktchain router is injected for
                tiles/switch boxes that are not already controlled by another pktchain router. When two ``None`` are
                yielded consecutively, the current secondary pktchain is terminated and attached to the primary
                pktchain.
            _not_top (:obj:`bool`): If set, the array is treated as a non-top level array. This is primarily used when
                this method calls itself recursively
        """
        module = uno(logical_module, context.database[ModuleView.logical, context.top.key])
        if not module.module_class.is_array:
            raise PRGAInternalError("{} is not an array".format(module))
        # primary network
        dispatcher, gatherer = None, None
        # secondary pktchain
        secondary_cfg_nets, chains, current_chain = {}, [], []
        # scanchain
        scanchain_cfg_nets, scanchain_bitoffset = {}, 0
        none_once = False
        for instance in tuple(iter_instances(module)):
            # control
            if instance is None:
                _logger.debug("Chain break (None) yielded")
                if none_once:
                    if _not_top:
                        _logger.debug("Exposing secondary chain No. {} ({} routers, {})"
                                .format(len(chains), len(current_chain), module))
                        cls._expose_pktchain_secondary_chain(module, secondary_cfg_nets, len(chains))
                    else:
                        _logger.debug("Attaching secondary chain No. {} ({} routers) to the primary backbone"
                                .format(len(chains), len(current_chain)))
                        dispatcher, gatherer = cls._attach_pktchain_secondary_chain(context, module,
                                dispatcher, gatherer, secondary_cfg_nets, len(chains))
                    chains.append( tuple(iter(current_chain)) )
                    current_chain = []
                else:
                    scanchain_bitoffset = cls._complete_pktchain_wrap_leaves(context, module, len(chains),
                            secondary_cfg_nets, current_chain, scanchain_cfg_nets, scanchain_bitoffset)
                none_once = not none_once
                continue
            none_once = False
            try:
                instance, subchain = instance
            except (TypeError, ValueError):
                chainoffsets = getattr(instance, "cfg_chainoffsets", {})
                assert set(range(len(chainoffsets))) == set(chainoffsets)
                subchain = len(chainoffsets)
            # complete sub-instance
            if instance.model.module_class.is_array:
                # ramp up any remaining scanchains
                scanchain_bitoffset = cls._complete_pktchain_wrap_leaves(context, module, len(chains),
                        secondary_cfg_nets, current_chain, scanchain_cfg_nets, scanchain_bitoffset)
                # get subchain map
                if (subchain_map := getattr(instance.model, "cfg_chains", None)) is None:
                    cls.complete_pktchain(context, instance.model, iter_instances = iter_instances, _not_top = True)
                    subchain_map = instance.model.cfg_chains
                if not 0 <= subchain < len(subchain_map):
                    raise PRGAInternalError("{} does not have chain No. {}".format(instance, subchain))
                # update chain settings
                if (chainoffsets := getattr(instance, "cfg_chainoffsets", None)) is None:
                    chainoffsets = instance.cfg_chainoffsets = {}
                chainoffsets[subchain] = len(chains), len(current_chain)
                _logger.debug(("Adding {} routers ({} bits, respectively) from {} to secondary chain "
                    "No. {} ({} routers after, {})")
                    .format(len(subchain_map[subchain]), ', '.join(map(str, subchain_map[subchain])), instance,
                        len(chains), len(current_chain) + len(subchain_map[subchain]), module))
                current_chain.extend( subchain_map[subchain] )
                # connect ports
                cls._connect_pktchain_subchain(module, instance, subchain, secondary_cfg_nets)
            else:
                scanchain_bitoffset = cls._complete_pktchain_leaf(
                        context, module, instance, iter_instances,
                        scanchain_cfg_nets, scanchain_bitoffset, len(chains), len(current_chain))
        # remaining
        # ramp up any remaining scanchains
        cls._complete_pktchain_wrap_leaves(context, module, len(chains),
                secondary_cfg_nets, current_chain, scanchain_cfg_nets, scanchain_bitoffset)
        # if we have a secondary chain, expose it and update our main chain map
        if secondary_cfg_nets:
            if _not_top:
                _logger.debug("Exposing secondary chain No. {} ({} routers, {})"
                        .format(len(chains), len(current_chain), module))
                cls._expose_pktchain_secondary_chain(module, secondary_cfg_nets, len(chains))
            else:
                _logger.debug("Attaching secondary chain No. {} ({} routers) to the primary backbone"
                        .format(len(chains), len(current_chain)))
                dispatcher, gatherer = cls._attach_pktchain_secondary_chain(context, module,
                        dispatcher, gatherer, secondary_cfg_nets, len(chains))
            chains.append( tuple(iter(current_chain)) )
        module.cfg_chains = tuple(iter(chains))
        # tie the control pins of the last dispatcher/gatherer to constant values
        if not _not_top:
            assert dispatcher is not None
            NetUtils.connect(Const(1), dispatcher.pins["phit_ox_full"])
            NetUtils.connect(Const(0), gatherer.pins["phit_ix_wr"])
            # update summary
            if (summary := getattr(context.summary, "pktchain", None)) is None:
                summary = context.summary.pktchain = {}
            fabric = summary.setdefault("fabric", {})
            fabric.update(chains = module.cfg_chains, x_tiles = len(chains))
            y_tiles = len(chains[0])
            for i, chain in enumerate(chains[1:]):
                if len(chain) != y_tiles:
                    raise PRGAInternalError("Unbalanced chain. Col. {} has {} tiles but col. {} has {}"
                            .format(0, y_tiles, i, len(chain)))
            fabric["y_tiles"] = y_tiles
            _logger.info("Pktchain injected: {} nodes on primary backbone, {} nodes per secondary chain"
                    .format(len(chains), y_tiles))

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
        _logger.info("Annotating pktchain configuration data to the user view of {}"
                .format(module))

        _annotated = uno(_annotated, set())
        if module.module_class.is_array:
            logical = context.database[ModuleView.logical, module.key]
            # annotate user instances
            for instance in itervalues(module.instances):
                # look for the corresponding logical instance and annotate cfg_chainoffsets
                logical_instance = logical.instances[instance.key]
                if (cfg_chainoffsets := getattr(logical_instance, "cfg_chainoffsets", None)) is not None:
                    instance.cfg_chainoffsets = cfg_chainoffsets
                if (cfg_bitoffset := getattr(logical_instance, "cfg_bitoffset", None)) is not None:
                    instance.cfg_bitoffset = cfg_bitoffset
                if instance.model.key not in _annotated:
                    _annotated.add(instance.model.key)
                    cls.annotate_user_view(context, instance.model, _annotated = _annotated)
        else:
            super(Pktchain, cls).annotate_user_view(context, module, _annotated = _annotated)

    class InjectConfigCircuitry(AbstractPass):
        """Automatically inject configuration circuitry.
        
        Keyword Args:
            iter_instances (:obj:`Callable` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module. In addition, when the module is an array, ``None`` can be yielded to
                control pktchain router injection. When one ``None`` is yielded, a pktchain router is injected for
                tiles/switch boxes that are not already controlled by another pktchain router. When two ``None`` are
                yielded consecutively, the current secondary pktchain is terminated and attached to the primary
                pktchain.
        """

        __slots__ = ["iter_instances"]

        def __init__(self, *, iter_instances = None):
            self.iter_instances = iter_instances

        def run(self, context, renderer = None):
            kwargs = {}
            if callable(self.iter_instances):
                kwargs["iter_instances"] = self.iter_instances
            Pktchain.complete_pktchain(context, **kwargs)
            Pktchain.annotate_user_view(context)

        @property
        def key(self):
            return "config.injection.pktchain"

        @property
        def dependences(self):
            return ("translation", )
        
        @property
        def passes_after_self(self):
            return ("rtl", )

    class BuildSystem(AbstractPass):
        """Create a system wrapping the fabric with the system integration interface."""

        __slots__  = ["io_constraints_f", "name", "core", "cfg_in_core"]

        def __init__(self, io_constraints_f = "io.pads", *,
                name = "prga_system", core = None, cfg_in_core = False):

            if cfg_in_core and core is None:
                raise PRGAAPIError("`core` must be set when `cfg_in_core` is set")

            self.io_constraints_f = io_constraints_f
            self.name = name
            self.core = core
            self.cfg_in_core = cfg_in_core

        def run(self, context, renderer = None):
            # build system
            Integration.build_system(context,
                    name = self.name, core = self.core)

            # get system module
            system = context.system_top

            # which backend should we connect?
            sysintf_slave, sysintf_prefix = None, ""
            cfg_inst, cfg_slave = None, None

            # check core
            if self.core and self.cfg_in_core:
                core = system.instances["i_core"]
                fabric = core.model.instances["i_fabric"]

                sysintf_slave, sysintf_prefix, cfg_slave = core, "cfg_", fabric

                # create cfg ports
                core_ports = Integration._create_intf_cfg(core.model, True, sysintf_prefix)
                core_ports["cfg_clk"] = ModuleUtils.create_port(core.model, "cfg_clk", 1, PortDirection.input_,
                        is_clock = True)

                # instantiate
                cfg_inst = ModuleUtils.instantiate(core.model,
                        context.database[ModuleView.logical, "pktchain_cfg"], "i_cfg")

                # connect cfg with core ports
                for port_name, port in iteritems(core_ports):
                    if port.direction.is_input:
                        NetUtils.connect(port, cfg_inst.pins[port_name[4:]])
                    else:
                        NetUtils.connect(cfg_inst.pins[port_name[4:]], port)

                # connect cfg with fabric pins
                NetUtils.connect(core_ports["cfg_clk"], fabric.pins["cfg_clk"])

            else:
                if self.core:
                    cfg_slave = core = system.instances["i_core"]
                    fabric = core.model.instances["i_fabric"]

                    # expose fabric cfg ports to outside of core
                    NetUtils.connect(
                            ModuleUtils.create_port(core.model, "cfg_clk", 1, PortDirection.input_, is_clock = True),
                            fabric.pins["cfg_clk"])
                    NetUtils.connect(system.ports["clk"], core.pins["cfg_clk"])

                    for pin_name in ["cfg_rst", "cfg_e", "phit_o_full", "phit_i_wr", "phit_i"]:
                        pin = fabric.pins[pin_name]
                        NetUtils.connect(
                                ModuleUtils.create_port(core.model, pin_name, len(pin), PortDirection.input_),
                                pin)
                    for pin_name in ["phit_i_full", "phit_o_wr", "phit_o"]:
                        pin = fabric.pins[pin_name]
                        NetUtils.connect(pin,
                                ModuleUtils.create_port(core.model, pin_name, len(pin), PortDirection.output))
                else:
                    cfg_slave = system.instances["i_fabric"]
                    NetUtils.connect(system.ports["clk"], cfg_slave.pins["cfg_clk"])

                # instantiate
                sysintf_slave = cfg_inst = ModuleUtils.instantiate(system,
                    context.database[ModuleView.logical, "pktchain_cfg"], "i_cfg")

            # connect cfg with its slave
            NetUtils.connect(cfg_inst.pins["cfg_rst"], cfg_slave.pins["cfg_rst"])
            NetUtils.connect(cfg_inst.pins["cfg_e"], cfg_slave.pins["cfg_e"])
            NetUtils.connect(cfg_inst.pins["phit_i_full"], cfg_slave.pins["phit_o_full"])
            NetUtils.connect(cfg_slave.pins["phit_o_wr"], cfg_inst.pins["phit_i_wr"])
            NetUtils.connect(cfg_slave.pins["phit_o"], cfg_inst.pins["phit_i"])
            NetUtils.connect(cfg_slave.pins["phit_i_full"], cfg_inst.pins["phit_o_full"])
            NetUtils.connect(cfg_inst.pins["phit_o_wr"], cfg_slave.pins["phit_i_wr"])
            NetUtils.connect(cfg_inst.pins["phit_o"], cfg_slave.pins["phit_i"])

            # connect sysintf with its slave
            intf = system.instances["i_sysintf"]
            NetUtils.connect(system.ports["clk"], sysintf_slave.pins[sysintf_prefix + "clk"])
            for pin_name in ["rst_n", "req_val", "req_addr", "req_strb", "req_data", "resp_rdy"]:
                NetUtils.connect(intf.pins["cfg_" + pin_name], sysintf_slave.pins[sysintf_prefix + pin_name])
            for pin_name in ["status", "req_rdy", "resp_val", "resp_err", "resp_data"]:
                NetUtils.connect(sysintf_slave.pins[sysintf_prefix + pin_name], intf.pins["cfg_" + pin_name])

            # generate IO constraints
            constraints = dict(
                    **Integration.ioplan_syscon(context),
                    **Integration.ioplan_reg(context),
                    **Integration.ioplan_ccm(context), )
            IOPlanner.print_io_constraints(constraints, self.io_constraints_f)

        @property
        def key(self):
            return "system.pktchain"

        @property
        def dependences(self):
            return ("vpr", )

        @property
        def passes_after_self(self):
            return ("rtl", )
