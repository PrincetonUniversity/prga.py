# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .protocol import PktchainProtocol
from ..scanchain.lib import Scanchain, ScanchainSwitchDatabase, ScanchainFASMDelegate
from ...core.common import ModuleClass, ModuleView, NetClass
from ...core.context import Context
from ...netlist.net.common import PortDirection, Const
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...passes.vpr import FASMDelegate
from ...renderer.renderer import FileRenderer
from ...util import Object, uno
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
        assert instance.model.module_class.is_leaf_array
        chain, ypos = 0, 0
        for i in instance.hierarchy:
            chain, ypos_inc = i.cfg_chainoffsets[chain]
            ypos += ypos_inc
        return chain, ypos

    def fasm_prefix_for_tile(self, instance):
        leaf_array_instance = instance.shrink_hierarchy(slice(1, None))
        bitoffsets = []
        for subblock in range(instance.model.capacity):
            blk_inst = leaf_array_instance.model.instances[instance.hierarchy[0].key[0], subblock]
            inst_bitoffset = self._instance_bitoffset(blk_inst)
            if inst_bitoffset is None:
                return tuple()
            bitoffsets.append( inst_bitoffset )
        chain, ypos = self._instance_chainoffset(leaf_array_instance)
        return tuple("x{}.y{}.b{}".format(chain, ypos, bitoffset) for bitoffset in bitoffsets)

    def fasm_features_for_routing_switch(self, source, sink, instance = None):
        below, above = None, None
        for split, i in enumerate(instance.hierarchy):
            if i.model.module_class.is_leaf_array:
                below = instance.shrink_hierarchy(slice(None, split))
                above = instance.shrink_hierarchy(slice(split, None))
                break
        assert above is not None
        chain, ypos = self._instance_chainoffset(above)
        return tuple('x{}.y{}.{}'.format(chain, ypos, f) for f in self._features_for_path(source, sink, below))

    # def fasm_features_for_routing_switch(self, source, sink, instance = None):
    #     return self._features_for_path(source, sink, instance)

# ----------------------------------------------------------------------------
# -- Pktchain Configuration Circuitry Main Entry -----------------------------
# ----------------------------------------------------------------------------
class Pktchain(Scanchain):
    """Packetized configuration circuitry entry point."""

    @classmethod
    def _phit_port_name(cls, type_, chain):
        return "cfg_{}_c{}".format(type_, chain)

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
    def _create_axilite_intf(cls, module, prefix, addr_width, data_bytes, is_master = False):
        ports = {}
        # aliases
        p, mcp = prefix, ModuleUtils.create_port
        # master output, master input
        mo, mi = ((PortDirection.output, PortDirection.input_) if is_master else
                (PortDirection.input_, PortDirection.output))
        # write address channel
        ports["AWVALID"]  = mcp(module,  p+"_AWVALID", 1,              mo)
        ports["AWREADY"]  = mcp(module,  p+"_AWREADY", 1,              mi)
        ports["AWADDR"]   = mcp(module,  p+"_AWADDR",  addr_width,     mo)
        ports["AWPROT"]   = mcp(module,  p+"_AWPROT",  3,              mo)
        # write data channel
        ports["WVALID"]   = mcp(module,  p+"_WVALID",  1,              mo)
        ports["WREADY"]   = mcp(module,  p+"_WREADY",  1,              mi)
        ports["WDATA"]    = mcp(module,  p+"_WDATA",   data_bytes * 8, mo)
        ports["WSTRB"]    = mcp(module,  p+"_WSTRB",   data_bytes,     mo)
        # write response channel
        ports["BVALID"]   = mcp(module,  p+"_BVALID",  1,              mi)
        ports["BREADY"]   = mcp(module,  p+"_BREADY",  1,              mo)
        ports["BRESP"]    = mcp(module,  p+"_BRESP",   2,              mi)
        # read address channel
        ports["ARVALID"]  = mcp(module,  p+"_ARVALID", 1,              mo)
        ports["ARREADY"]  = mcp(module,  p+"_ARREADY", 1,              mi)
        ports["ARADDR"]   = mcp(module,  p+"_ARADDR",  addr_width,     mo)
        ports["ARPROT"]   = mcp(module,  p+"_ARPROT",  3,              mo)
        # read response channel
        ports["RVALID"]   = mcp(module,  p+"_RVALID",  1,              mi)
        ports["RREADY"]   = mcp(module,  p+"_RREADY",  1,              mo)
        ports["RDATA"]    = mcp(module,  p+"_RDATA",   data_bytes * 8, mi)
        ports["RRESP"]    = mcp(module,  p+"_RRESP",   2,              mi)
        # return created ports
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
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.cfg,
                    cfg_width = cfg_width,
                    verilog_template = "pktchain_clasp.tmpl.v")
            # we don't need to create ports for this module.
            context._database[ModuleView.logical, "pktchain_clasp"] = mod

        # register pktchain router input fifo
        if "pktchain_frame_assemble" not in dont_add_logical_primitive:
            mod = Module("pktchain_frame_assemble",
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

        # register pktchain AXILite interface-related stuff
        if "pktchain_axilite_intf_fe" not in dont_add_logical_primitive:
            d = "pktchain_axilite_intf_fe"
            mod = context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    verilog_template = "axilite_intf/" + d + ".tmpl.v")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"],
                    "axi_waddr_fifo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"],
                    "axi_wdata_fifo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"],
                    "axi_raddr_fifo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_tokenfifo"],
                    "axi_wresp_fifo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"],
                    "axi_rresp_fifo")

        if "pktchain_axilite_intf_be_uprot" not in dont_add_logical_primitive:
            d = "pktchain_axilite_intf_be_uprot"
            mod = context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    verilog_template = "axilite_intf/" + d + ".tmpl.v")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_byteaddressable_reg"],
                    "timeout_limit_reg")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"],
                    "uerr_fifo")

        if not ({"pktchain_frame_disassemble", "pktchain_frame_assemble", "pktchain_axilite_intf_be_cfg"} &
                dont_add_logical_primitive):
            d = "pktchain_axilite_intf_be_cfg"
            mod = context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    verilog_template = "axilite_intf/" + d + ".tmpl.v")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo"],
                    "axififo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "prga_fifo_resizer"],
                    "axififo_resizer")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_disassemble"],
                    "bsframe_fifo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_assemble"],
                    "bsresp_fifo")

        if not ({"pktchain_axilite_intf_fe", "pktchain_axilite_intf_be_uprot", "pktchain_axilite_intf_be_cfg"} &
                dont_add_logical_primitive):
            d = "pktchain_axilite_intf"
            mod = context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    verilog_template = "axilite_intf/" + d + ".tmpl.v")
            # create a short alias
            mcp = ModuleUtils.create_port
            mit = ModuleUtils.instantiate
            # ports
            clk = mcp(mod, "clk", 1, PortDirection.input_, is_clock = True)
            rst = mcp(mod, "rst", 1, PortDirection.input_)
            mcp(mod, "uclk", 1, PortDirection.output, is_clock = True)
            mcp(mod, "urst_n", 1, PortDirection.output)
            mcp(mod, "cfg_rst",             1,              PortDirection.output),
            mcp(mod, "cfg_e",               1,              PortDirection.output),
            mcp(mod, "cfg_phit_o_full",     1,              PortDirection.input_),
            mcp(mod, "cfg_phit_o_wr",       1,              PortDirection.output),
            mcp(mod, "cfg_phit_o",          phit_width,     PortDirection.output),
            mcp(mod, "cfg_phit_i_full",     1,              PortDirection.output),
            mcp(mod, "cfg_phit_i_wr",       1,              PortDirection.input_),
            mcp(mod, "cfg_phit_i",          phit_width,     PortDirection.input_),
            cls._create_axilite_intf(mod, "m", PktchainProtocol.AXILiteController.ADDR_WIDTH,
                    2 ** (PktchainProtocol.AXILiteController.DATA_WIDTH_LOG2 - 3))
            cls._create_axilite_intf(mod, "u", PktchainProtocol.AXILiteController.ADDR_WIDTH,
                    2 ** (PktchainProtocol.AXILiteController.DATA_WIDTH_LOG2 - 3), is_master = True)
            # instances
            mit(mod, context.database[ModuleView.logical, "pktchain_axilite_intf_fe"], "i_fe")
            mit(mod, context.database[ModuleView.logical, "prga_async_tokenfifo"], "i_cdcq_wresp")
            mit(mod, context.database[ModuleView.logical, "prga_clkdiv"], "i_clkdiv")
            mit(mod, context.database[ModuleView.logical, "prga_async_fifo"], "i_cdcq_wreq")
            mit(mod, context.database[ModuleView.logical, "prga_async_fifo"], "i_cdcq_rreq")
            mit(mod, context.database[ModuleView.logical, "prga_async_fifo"], "i_cdcq_rresp")
            mit(mod, context.database[ModuleView.logical, "pktchain_axilite_intf_be_uprot"], "i_uprot")
            mit(mod, context.database[ModuleView.logical, "pktchain_axilite_intf_be_cfg"], "i_cfg")
            mit(mod, context.database[ModuleView.logical, "prga_fifo"], "i_wresp_tokenq")
            mit(mod, context.database[ModuleView.logical, "prga_fifo"], "i_rresp_tokenq")
            mit(mod, context.database[ModuleView.logical, "prga_fifo"], "i_rresp_dataq")
            mit(mod, context.database[ModuleView.logical, "prga_byteaddressable_reg"], "i_ctrl_cfg")
            mit(mod, context.database[ModuleView.logical, "prga_fifo"], "i_errq")
            mit(mod, context.database[ModuleView.logical, "prga_byteaddressable_reg"], "i_bsid")

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
        context._add_verilog_header("pktchain.vh", "pktchain.tmpl.vh")
        context._add_verilog_header("pktchain_axilite_intf.vh", "axilite_intf/pktchain_axilite_intf.tmpl.vh")
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
        r = super(Pktchain, cls).new_renderer(additional_template_search_paths)
        r.template_search_paths.insert(0, ADDITIONAL_TEMPLATE_SEARCH_PATH)
        return r

    @classmethod
    def complete_pktchain_leaf(cls, context, logical_module, *, iter_instances = lambda m: itervalues(m.instances)):
        """Inject leaf pktchain in ``logical_module``.
        
        Args:
            context (`Context`):
            logical_module (`Module`): The module (logical view) in which leaf pktchain is injected.

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module

        Thie method calls itself recursively to process all the instances (sub-modules). This method calls
        `Scanchain.complete_scanchain` under the hood, because within each terminal in the packet-switch network, the
        bitstream is still loaded through a scanchain.
        """
        # short alias
        module = logical_module
        cfg_width = context.summary.scanchain["cfg_width"]
        # make sure this is an leaf array
        if not module.module_class.is_leaf_array:
            raise PRGAInternalError("Cannot complete pktchain (leaf) in {}, not a leaf array".format(module))
        # complete scanchain of each sub blocks/boxes
        cfg_bitoffset = 0
        cfg_nets = {}
        for instance in iter_instances(module):
            if instance.model.module_class.is_block or instance.model.module_class.is_routing_box:
                if not hasattr(instance.model, "cfg_bitcount"):
                    cls.complete_scanchain(context, instance.model, iter_instances = iter_instances)
            # enable pin?
            inst_cfg_e = instance.pins.get("cfg_e")
            if inst_cfg_e is None:
                continue
            NetUtils.connect(cls._get_or_create_cfg_ports(module, cfg_width, enable_only = True),
                    inst_cfg_e)
            # bitstream loading pin
            inst_cfg_i = instance.pins.get("cfg_i")
            if inst_cfg_i is None:
                continue
            assert len(inst_cfg_i) == cfg_width
            if instance.model.cfg_bitcount % cfg_width > 0:
                raise PRGAInternalError("Scanchain in {} is not aligned to cfg_width ({})"
                        .format(instance.model, cfg_width))
            instance.cfg_bitoffset = cfg_bitoffset
            cfg_bitoffset += instance.model.cfg_bitcount
            # connect clocks
            cfg_clk = cfg_nets.get("cfg_clk")
            if cfg_clk is None:
                cfg_clk = cfg_nets["cfg_clk"] = ModuleUtils.create_port(module, "cfg_clk", 1, PortDirection.input_,
                        is_clock = True, net_class = NetClass.cfg)
            NetUtils.connect(cfg_clk, instance.pins["cfg_clk"])
            # chain inputs
            if "cfg_o" not in cfg_nets:
                cfg_nets["cfg_we"] = instance.pins["cfg_we"]
                cfg_nets["cfg_i"] = instance.pins["cfg_i"]
            else:
                NetUtils.connect(cfg_nets["cfg_o"], instance.pins["cfg_i"])
                NetUtils.connect(cfg_nets["cfg_we_o"], instance.pins["cfg_we"])
            cfg_nets["cfg_o"] = instance.pins["cfg_o"]
            cfg_nets["cfg_we_o"] = instance.pins["cfg_we_o"]
        # inject router
        module.cfg_bitcount = cfg_bitoffset
        # NOTE: inject router anyway because we need to balance chains
        router = ModuleUtils.instantiate(module,
                context.database[ModuleView.logical, "pktchain_router"],
                "_cfg_router_inst")
        if "cfg_i" in cfg_nets:
            NetUtils.connect(cfg_nets["cfg_clk"], router.pins["cfg_clk"])
            NetUtils.connect(router.pins["cfg_we_o"], cfg_nets["cfg_we"])
            NetUtils.connect(router.pins["cfg_o"], cfg_nets["cfg_i"])
            NetUtils.connect(cfg_nets["cfg_we_o"], router.pins["cfg_we_i"])
            NetUtils.connect(cfg_nets["cfg_o"], router.pins["cfg_i"])
        else:
            cfg_clk = ModuleUtils.create_port(module, "cfg_clk", 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.cfg)
            NetUtils.connect(cfg_clk, router.pins["cfg_clk"])
            NetUtils.connect(router.pins["cfg_we_o"], router.pins["cfg_we_i"])
            NetUtils.connect(router.pins["cfg_o"], router.pins["cfg_i"])
        NetUtils.connect(ModuleUtils.create_port(module, "cfg_rst", 1, PortDirection.input_,
            net_class = NetClass.cfg), router.pins["cfg_rst"])
        phit_intf = cls._get_or_create_fifo_intf(module, context.summary.pktchain["fabric"]["phit_width"])
        NetUtils.connect(router.pins["phit_i_full"], phit_intf["phit_i_full"]) 
        NetUtils.connect(phit_intf["phit_i_wr"], router.pins["phit_i_wr"]) 
        NetUtils.connect(phit_intf["phit_i"], router.pins["phit_i"]) 
        NetUtils.connect(phit_intf["phit_o_full"], router.pins["phit_o_full"]) 
        NetUtils.connect(router.pins["phit_o_wr"], phit_intf["phit_o_wr"]) 
        NetUtils.connect(router.pins["phit_o"], phit_intf["phit_o"]) 
        # cfg_chains[chain offset][router offset] -> cfg_bitcount
        module.cfg_chains = ((cfg_bitoffset, ), )
        _logger.info("Pktchain(leaf) injected to {}. Total bits: {}".format(module, cfg_bitoffset))

    @classmethod
    def complete_pktchain_network(cls, context, logical_module, *, iter_instances = lambda m: itervalues(m.instances)):
        """Inject pktchain network and routers in ``logical_module``.
        
        Args:
            context (`Context`):
            logical_module (`Module`): The module (logical view) in which pktchain network and routers are injected.

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module. Whenever ``None`` is yielded, the current secondary packet-switch network
                is terminated and attached to the primary packet-switch network, then a new secondary packet-switch
                network is started.

        Thie method calls itself recursively to process all the instances (sub-modules). This method calls
        `Pktchain.complete_pktchain_leaf` on `LeafArray`s in the hierarchy.
        """
        # short alias
        module = logical_module
        # make sure this is a non-leaf array
        if not module.module_class.is_nonleaf_array:
            raise PRGAInternalError("Cannot complete pktchain (non-leaf) in {}, not a non-leaf array".format(module))
        # complete network
        chains, current_chain = [], []
        cfg_nets = {}
        for instance in iter_instances(module):
            if instance is None:
                # end the current chain and start a new one
                if "phit" in cfg_nets:
                    chain = len(chains)
                    NetUtils.connect(cfg_nets.pop("phit_wr"), ModuleUtils.create_port(module, 
                        cls._phit_port_name("phit_o_wr", chain), 1,
                        PortDirection.output, net_class = NetClass.cfg))
                    NetUtils.connect(cfg_nets.pop("phit"), ModuleUtils.create_port(module,
                        cls._phit_port_name("phit_o", chain), context.summary.pktchain["fabric"]["phit_width"],
                        PortDirection.output, net_class = NetClass.cfg))
                    NetUtils.connect(ModuleUtils.create_port(module, cls._phit_port_name("phit_o_full", chain), 1,
                        PortDirection.input_, net_class = NetClass.cfg), cfg_nets.pop("phit_full"))
                    chains.append(tuple(current_chain))
                current_chain = []
                continue
            chain = len(chains)
            # complete sub-instance
            if not hasattr(instance.model, "cfg_chains"):
                if instance.model.module_class.is_leaf_array:
                    cls.complete_pktchain_leaf(context, instance.model, iter_instances = iter_instances)
                else:
                    cls.complete_pktchain_network(context, instance.model, iter_instances = iter_instances)
            # is the sub-chain specified?
            try:
                instance, subchain = instance
            except (TypeError, ValueError):
                chainoffsets = getattr(instance, "cfg_chainoffsets", {})
                assert set(range(len(chainoffsets))) == set(chainoffsets)
                subchain = len(chainoffsets)
            # enable pin?
            inst_cfg_e = instance.pins.get("cfg_e")
            if inst_cfg_e is not None and NetUtils.get_source(inst_cfg_e, return_none_if_unconnected = True) is None:
                NetUtils.connect(cls._get_or_create_cfg_ports(module, context.summary.scanchain["cfg_width"],
                    enable_only = True), inst_cfg_e)
            # update chains and instance chain mapping
            try:
                subchain_bitmap = instance.model.cfg_chains[subchain]
            except (AttributeError, IndexError):
                raise PRGAInternalError("{} does not have chain No. {}".format(subchain))
            chainoffsets = getattr(instance, "cfg_chainoffsets", None)
            if chainoffsets is None:
                chainoffsets = instance.cfg_chainoffsets = {}
            chainoffsets[subchain] = chain, len(current_chain)
            current_chain.extend(subchain_bitmap)
            # connect clock/reset pins if we haven't done so
            if NetUtils.get_source(instance.pins["cfg_clk"], return_none_if_unconnected = True) is None:
                cfg_clk = cfg_nets.get("cfg_clk")
                if cfg_clk is None:
                    cfg_clk = cfg_nets["cfg_clk"] = ModuleUtils.create_port(module, "cfg_clk", 1,
                            PortDirection.input_, is_clock = True, net_class = NetClass.cfg)
                NetUtils.connect(cfg_clk, instance.pins["cfg_clk"])
                cfg_rst = cfg_nets.get("cfg_rst")
                if cfg_rst is None:
                    cfg_rst = cfg_nets["cfg_rst"] = ModuleUtils.create_port(module, "cfg_rst", 1,
                            PortDirection.input_, net_class = NetClass.cfg)
                NetUtils.connect(cfg_rst, instance.pins["cfg_rst"])
            # connect other pins
            if "phit" not in cfg_nets:
                cfg_nets["phit_full"] = ModuleUtils.create_port(module,
                        cls._phit_port_name("phit_i_full", chain), 1,
                        PortDirection.output, net_class = NetClass.cfg)
                cfg_nets["phit_wr"] = ModuleUtils.create_port(module,
                        cls._phit_port_name("phit_i_wr", chain), 1,
                        PortDirection.input_, net_class = NetClass.cfg)
                cfg_nets["phit"] = ModuleUtils.create_port(module,
                        cls._phit_port_name("phit_i", chain), context.summary.pktchain["fabric"]["phit_width"],
                        PortDirection.input_, net_class = NetClass.cfg)
            NetUtils.connect(instance.pins[cls._phit_port_name("phit_i_full", subchain)], cfg_nets["phit_full"])
            NetUtils.connect(cfg_nets["phit_wr"], instance.pins[cls._phit_port_name("phit_i_wr", subchain)])
            NetUtils.connect(cfg_nets["phit"], instance.pins[cls._phit_port_name("phit_i", subchain)])
            cfg_nets["phit_full"] = instance.pins[cls._phit_port_name("phit_o_full", subchain)]
            cfg_nets["phit_wr"] = instance.pins[cls._phit_port_name("phit_o_wr", subchain)]
            cfg_nets["phit"] = instance.pins[cls._phit_port_name("phit_o", subchain)]
        if "phit" in cfg_nets:
            chain = len(chains)
            NetUtils.connect(cfg_nets.pop("phit_wr"), ModuleUtils.create_port(module, 
                cls._phit_port_name("phit_o_wr", chain), 1,
                PortDirection.output, net_class = NetClass.cfg))
            NetUtils.connect(cfg_nets.pop("phit"), ModuleUtils.create_port(module,
                cls._phit_port_name("phit_o", chain), context.summary.pktchain["fabric"]["phit_width"],
                PortDirection.output, net_class = NetClass.cfg))
            NetUtils.connect(ModuleUtils.create_port(module, cls._phit_port_name("phit_o_full", chain), 1,
                PortDirection.input_, net_class = NetClass.cfg), cfg_nets.pop("phit_full"))
            chains.append(tuple(current_chain))
        module.cfg_chains = tuple(chains)
        _logger.info("Pktchain(network) injected to {}. Chains: {}".format(module, ", ".join(map(str, chains))))

    @classmethod
    def complete_pktchain(cls, context, logical_module = None, *, iter_instances = lambda m: itervalues(m.instances)):
        """Inject pktchain network and routers in ``logical_module``. This method should be called on the top-level
        array.
        
        Args:
            context (`Context`):
            logical_module (`Module`): The module (logical view) in which pktchain network and routers are injected. If
                not specified, the top-level array in ``context`` is selected

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module. Whenever ``None`` is yielded, the current secondary packet-switch network
                is terminated and attached to the primary packet-switch network, then a new secondary packet-switch
                network is started.

        This method calls `Pktchain.complete_pktchain_network` and `Pktchain.complete_pktchain_leaf`.
        """
        # short alias
        module = uno(logical_module, context.database[ModuleView.logical, context.top.key])
        # make sure this is a non-leaf array
        if not module.module_class.is_nonleaf_array:
            raise PRGAInternalError("Cannot complete pktchain (top) in {}, not a non-leaf array".format(module))
        # complete network
        chains, current_chain = [], []
        cfg_nets = {}
        prev_dispatcher = None
        gatherers = []
        for instance in iter_instances(module):
            if instance is None:
                # end the current chain and start a new one
                if "phit" in cfg_nets:
                    chain = len(chains)
                    gather = ModuleUtils.instantiate(module,
                            context.database[ModuleView.logical, "pktchain_gatherer"],
                            "_cfg_gatherer_c{}".format(chain))
                    NetUtils.connect(cfg_nets["cfg_clk"], gather.pins["cfg_clk"])
                    NetUtils.connect(cfg_nets["cfg_rst"], gather.pins["cfg_rst"])
                    NetUtils.connect(cfg_nets.pop("phit_wr"), gather.pins["phit_iy_wr"])
                    NetUtils.connect(gather.pins["phit_iy_full"], cfg_nets.pop("phit_full"))
                    NetUtils.connect(cfg_nets.pop("phit"), gather.pins["phit_iy"])
                    gatherers.append(gather)
                    chains.append(tuple(current_chain))
                current_chain = []
                continue
            chain = len(chains)
            # complete sub-instance
            if not hasattr(instance.model, "cfg_chains"):
                if instance.model.module_class.is_leaf_array:
                    cls.complete_pktchain_leaf(context, instance.model, iter_instances = iter_instances)
                else:
                    cls.complete_pktchain_network(context, instance.model, iter_instances = iter_instances)
            # is the sub-chain specified?
            try:
                instance, subchain = instance
            except (TypeError, ValueError):
                chainoffsets = getattr(instance, "cfg_chainoffsets", {})
                assert set(range(len(chainoffsets))) == set(chainoffsets)
                subchain = len(chainoffsets)
            # enable pin?
            inst_cfg_e = instance.pins.get("cfg_e")
            if inst_cfg_e is not None and NetUtils.get_source(inst_cfg_e, return_none_if_unconnected = True) is None:
                NetUtils.connect(cls._get_or_create_cfg_ports(module, context.summary.scanchain["cfg_width"],
                    enable_only = True), inst_cfg_e)
            # update chains and instance chain mapping
            try:
                subchain_bitmap = instance.model.cfg_chains[subchain]
            except (AttributeError, IndexError):
                raise PRGAInternalError("{} does not have chain No. {}".format(instance, subchain))
            chainoffsets = getattr(instance, "cfg_chainoffsets", None)
            if chainoffsets is None:
                chainoffsets = instance.cfg_chainoffsets = {}
            chainoffsets[subchain] = chain, len(current_chain)
            current_chain.extend(subchain_bitmap)
            # connect clock/reset pins if we haven't done so
            if NetUtils.get_source(instance.pins["cfg_clk"], return_none_if_unconnected = True) is None:
                cfg_clk = cfg_nets.get("cfg_clk")
                if cfg_clk is None:
                    cfg_clk = cfg_nets["cfg_clk"] = ModuleUtils.create_port(module, "cfg_clk", 1,
                            PortDirection.input_, is_clock = True, net_class = NetClass.cfg)
                NetUtils.connect(cfg_clk, instance.pins["cfg_clk"])
                cfg_rst = cfg_nets.get("cfg_rst")
                if cfg_rst is None:
                    cfg_rst = cfg_nets["cfg_rst"] = ModuleUtils.create_port(module, "cfg_rst", 1,
                            PortDirection.input_, net_class = NetClass.cfg)
                NetUtils.connect(cfg_rst, instance.pins["cfg_rst"])
            # connect other pins
            if "phit" not in cfg_nets:
                dispatcher = ModuleUtils.instantiate(module,
                        context.database[ModuleView.logical, "pktchain_dispatcher"],
                        "_cfg_dispatcher_c{}".format(chain))
                NetUtils.connect(cfg_nets["cfg_clk"], dispatcher.pins["cfg_clk"])
                NetUtils.connect(cfg_nets["cfg_rst"], dispatcher.pins["cfg_rst"])
                if prev_dispatcher is None:
                    NetUtils.connect(ModuleUtils.create_port(module, "phit_i_wr", 1, PortDirection.input_,
                        net_class = NetClass.cfg), dispatcher.pins["phit_i_wr"])
                    NetUtils.connect(ModuleUtils.create_port(module, "phit_i",
                        context.summary.pktchain["fabric"]["phit_width"],
                        PortDirection.input_, net_class = NetClass.cfg), dispatcher.pins["phit_i"])
                    NetUtils.connect(dispatcher.pins["phit_i_full"], ModuleUtils.create_port(module, "phit_i_full",
                        1, PortDirection.output, net_class = NetClass.cfg))
                else:
                    NetUtils.connect(prev_dispatcher.pins["phit_ox_wr"], dispatcher.pins["phit_i_wr"])
                    NetUtils.connect(prev_dispatcher.pins["phit_ox"], dispatcher.pins["phit_i"])
                    NetUtils.connect(dispatcher.pins["phit_i_full"], prev_dispatcher.pins["phit_ox_full"])
                prev_dispatcher = dispatcher
                cfg_nets["phit_full"] = dispatcher.pins["phit_oy_full"]
                cfg_nets["phit_wr"] = dispatcher.pins["phit_oy_wr"]
                cfg_nets["phit"] = dispatcher.pins["phit_oy"]
            NetUtils.connect(instance.pins[cls._phit_port_name("phit_i_full", subchain)], cfg_nets["phit_full"])
            NetUtils.connect(cfg_nets["phit_wr"], instance.pins[cls._phit_port_name("phit_i_wr", subchain)])
            NetUtils.connect(cfg_nets["phit"], instance.pins[cls._phit_port_name("phit_i", subchain)])
            cfg_nets["phit_full"] = instance.pins[cls._phit_port_name("phit_o_full", subchain)]
            cfg_nets["phit_wr"] = instance.pins[cls._phit_port_name("phit_o_wr", subchain)]
            cfg_nets["phit"] = instance.pins[cls._phit_port_name("phit_o", subchain)]
        # close up on the last dispatcher
        if prev_dispatcher is not None:
            NetUtils.connect(Const(1), prev_dispatcher.pins["phit_ox_full"])
        # final gatherer
        if "phit" in cfg_nets:
            chain = len(chains)
            gather = ModuleUtils.instantiate(module,
                    context.database[ModuleView.logical, "pktchain_gatherer"],
                    "_cfg_gatherer_c{}".format(chain))
            NetUtils.connect(cfg_nets["cfg_clk"], gather.pins["cfg_clk"])
            NetUtils.connect(cfg_nets["cfg_rst"], gather.pins["cfg_rst"])
            NetUtils.connect(cfg_nets.pop("phit_wr"), gather.pins["phit_iy_wr"])
            NetUtils.connect(gather.pins["phit_iy_full"], cfg_nets.pop("phit_full"))
            NetUtils.connect(cfg_nets.pop("phit"), gather.pins["phit_iy"])
            gatherers.append(gather)
            chains.append(tuple(current_chain))
        module.cfg_chains = tuple(chains)
        _logger.info("Pktchain(network) injected to {}. Chains: {}".format(module, ", ".join(map(str, chains))))
        if not gatherers:
            return
        # connect gathers
        prev_gatherer = gatherers.pop()
        NetUtils.connect(Const(0), prev_gatherer.pins["phit_ix_wr"])
        for gather in reversed(gatherers):
            NetUtils.connect(prev_gatherer.pins["phit_o_wr"], gather.pins["phit_ix_wr"])
            NetUtils.connect(prev_gatherer.pins["phit_o"], gather.pins["phit_ix"])
            NetUtils.connect(gather.pins["phit_ix_full"], prev_gatherer.pins["phit_o_full"])
            prev_gatherer = gather
        # connect final pins
        NetUtils.connect(ModuleUtils.create_port(module, "phit_o_full", 1, PortDirection.input_,
            net_class = NetClass.cfg), prev_gatherer.pins["phit_o_full"])
        NetUtils.connect(prev_gatherer.pins["phit_o_wr"], ModuleUtils.create_port(module, "phit_o_wr", 1,
            PortDirection.output, net_class = NetClass.cfg))
        NetUtils.connect(prev_gatherer.pins["phit_o"], ModuleUtils.create_port(module, "phit_o",
            context.summary.pktchain["fabric"]["phit_width"], PortDirection.output, net_class = NetClass.cfg))
        # update context summary if this is the top-level module
        if module.key == context.top.key:
            if not hasattr(context.summary, "pktchain"):
                context.summary.pktchain = {}
            fabric = context.summary.pktchain.setdefault("fabric", {})
            fabric["chains"] = tuple(chains)
            fabric["x_tiles"] = len(chains)
            y_tiles = len(chains[0])
            for i, chain in enumerate(chains[1:]):
                if len(chain) != y_tiles:
                    raise PRGAInternalError("Unbalanced chain. Col. {} has {} tiles but col. {} has {}"
                            .format(0, y_tiles, i, len(chain)))
            fabric["y_tiles"] = y_tiles

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
        _annotated = uno(_annotated, set())
        if module.module_class.is_nonleaf_array:
            logical = context.database[ModuleView.logical, module.key]
            # annotate user instances
            for instance in itervalues(module.instances):
                # look for the corresponding logical instance and annotate cfg_chainoffsets
                logical_instance = logical.instances[instance.key]
                if hasattr(logical_instance, "cfg_chainoffsets"):
                    instance.cfg_chainoffsets = logical_instance.cfg_chainoffsets
                    if instance.model.key not in _annotated:
                        cls.annotate_user_view(context, instance.model, _annotated = _annotated)
        else:
            super(Pktchain, cls).annotate_user_view(context, module, _annotated = _annotated)
