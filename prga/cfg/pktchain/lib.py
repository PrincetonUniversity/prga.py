# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..scanchain.lib import Scanchain, ScanchainSwitchDatabase
from ...core.common import ModuleClass, ModuleView, NetClass
from ...core.context import Context
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...passes.translation import TranslationPass
from ...passes.vpr import FASMDelegate
from ...renderer.renderer import FileRenderer
from ...util import Object, uno
from ...exception import PRGAInternalError, PRGAAPIError

import os
from collections import OrderedDict, namedtuple
from itertools import chain, product

__all__ = ['Pktchain']

ADDITIONAL_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

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
    def new_context(cls, phit_width = 8, cfg_width = 1, *,
            dont_add_primitive = tuple(), dont_add_logical_primitive = tuple()):
        if phit_width not in (1, 2, 4, 8, 16):
            raise PRGAAPIError("Unsupported configuration phit width: {}. Supported values are: [1, 2, 4, 8, 16]"
                    .format(phit_width))
        if cfg_width not in (1, 2, 4):
            raise PRGAAPIError("Unsupported configuration chain width: {}. Supported values are: [1, 2, 4]"
                    .format(cfg_width))
        context = Context("pktchain", phit_width = phit_width, cfg_width = cfg_width)
        context._switch_database = ScanchainSwitchDatabase(context, cfg_width, cls)
        context._fasm_delegate = FASMDelegate()
        cls._register_primitives(context, phit_width, cfg_width, dont_add_primitive, dont_add_logical_primitive)
        return context

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
        if "pktchain_fifo" not in dont_add_logical_primitive:
            mod = Module("pktchain_fifo",
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.cfg,
                    phit_width = phit_width,
                    verilog_template = "pktchain_fifo.tmpl.v")
            # we don't need to create ports for this module.
            context._database[ModuleView.logical, "pktchain_fifo"] = mod

        # register pktchain router output fifo
        if "pktchain_frame_sender" not in dont_add_logical_primitive:
            mod = Module("pktchain_frame_sender",
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.cfg,
                    phit_width = phit_width,
                    verilog_template = "pktchain_frame_sender.tmpl.v")
            # we don't need to create ports for this module.
            context._database[ModuleView.logical, "pktchain_frame_sender"] = mod

        # register pktchain router
        if not ({"pktchain_clasp", "pktchain_fifo", "pktchain_frame_sender", "pktchain_router"} &
                dont_add_logical_primitive):
            mod = Module("pktchain_router",
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_router.tmpl.v")
            # create a short alias
            mcp = ModuleUtils.create_port
            cfg_clk = mcp(mod, "cfg_clk", 1, PortDirection.input_, is_clock = True, net_class = NetClass.cfg)
            mcp(mod, "cfg_rst", 1, PortDirection.input_, net_class = NetClass.cfg)
            clocked_ports = (
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
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_fifo"], "ififo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_sender"], "ofifo")
            context._database[ModuleView.logical, "pktchain_router"] = mod

        # register pktchain dispatcher (column/row header)
        if not ({"pktchain_dispatcher", "pktchain_fifo", "pktchain_frame_sender"} &
                dont_add_logical_primitive):
            mod = Module("pktchain_dispatcher",
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_dispatcher.tmpl.v")
            # create a short alias
            mcp = ModuleUtils.create_port
            cfg_clk = mcp(mod, "cfg_clk", 1, PortDirection.input_, is_clock = True, net_class = NetClass.cfg)
            mcp(mod, "cfg_rst", 1, PortDirection.input_, net_class = NetClass.cfg)
            clocked_ports = (
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
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_fifo"], "ififo")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_sender"], "ox")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_sender"], "oy")
            context._database[ModuleView.logical, "pktchain_dispatcher"] = mod

        # register pktchain gatherer (column/row footer)
        if not ({"pktchain_gatherer", "pktchain_fifo", "pktchain_frame_sender"} &
                dont_add_logical_primitive):
            mod = Module("pktchain_gatherer",
                    view = ModuleView.logical,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_gatherer.tmpl.v")
            # create a short alias
            mcp = ModuleUtils.create_port
            cfg_clk = mcp(mod, "cfg_clk", 1, PortDirection.input_, is_clock = True, net_class = NetClass.cfg)
            mcp(mod, "cfg_rst", 1, PortDirection.input_, net_class = NetClass.cfg)
            clocked_ports = (
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
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_fifo"], "ix")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_fifo"], "iy")
            ModuleUtils.instantiate(mod, context.database[ModuleView.logical, "pktchain_frame_sender"], "ofifo")
            context._database[ModuleView.logical, "pktchain_gatherer"] = mod

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        r = super(Pktchain, cls).new_renderer(additional_template_search_paths)
        r.template_search_paths.insert(0, ADDITIONAL_TEMPLATE_SEARCH_PATH)
        return r

    @classmethod
    def complete_pktchain_leaf(cls, context, logical_module, *, iter_instances = lambda m: itervalues(m.instances)):
        # short alias
        module = logical_module
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
            NetUtils.connect(cls._get_or_create_cfg_ports(module, context.cfg_width, enable_only = True),
                    inst_cfg_e)
            # bitstream loading pin
            inst_cfg_i = instance.pins.get("cfg_i")
            if inst_cfg_i is None:
                continue
            assert len(inst_cfg_i) == context.cfg_width
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
        if "cfg_i" in cfg_nets:
            router = ModuleUtils.instantiate(module,
                    context.database[ModuleView.logical, "pktchain_router"],
                    "_cfg_router_inst")
            NetUtils.connect(cfg_nets["cfg_clk"], router.pins["cfg_clk"])
            NetUtils.connect(router.pins["cfg_we_o"], cfg_nets["cfg_we"])
            NetUtils.connect(router.pins["cfg_o"], cfg_nets["cfg_i"])
            NetUtils.connect(cfg_nets["cfg_we_o"], router.pins["cfg_we_i"])
            NetUtils.connect(cfg_nets["cfg_o"], router.pins["cfg_i"])
            NetUtils.connect(ModuleUtils.create_port(module, "cfg_rst", 1, PortDirection.input_,
                net_class = NetClass.cfg), router.pins["cfg_rst"])
            phit_intf = cls._get_or_create_fifo_intf(module, context.phit_width)
            NetUtils.connect(router.pins["phit_i_full"], phit_intf["phit_i_full"]) 
            NetUtils.connect(phit_intf["phit_i_wr"], router.pins["phit_i_wr"]) 
            NetUtils.connect(phit_intf["phit_i"], router.pins["phit_i"]) 
            NetUtils.connect(phit_intf["phit_o_full"], router.pins["phit_o_full"]) 
            NetUtils.connect(router.pins["phit_o_wr"], phit_intf["phit_o_wr"]) 
            NetUtils.connect(router.pins["phit_o"], phit_intf["phit_o"]) 
            module.cfg_chains = (1, )
        else:
            module.cfg_chains = tuple()

    @classmethod
    def complete_pktchain_network(cls, context, logical_module, *, iter_instances = lambda m: itervalues(m.instances)):
        # short alias
        module = logical_module
        # make sure this is a non-leaf array
        if not module.module_class.is_nonleaf_array:
            raise PRGAInternalError("Cannot complete pktchain (non-leaf) in {}, not a non-leaf array".format(module))
        # complete network
        chains, ypos = [], 0
        cfg_nets = {}
        for instance in iter_instances(module):
            # end the current chain and start a new one
            if instance is None:
                if "phit" in cfg_nets:
                    chain = len(chains)
                    NetUtils.connect(cfg_nets.pop("phit_wr"), ModuleUtils.create_port(module, 
                        cls._phit_port_name("phit_o_wr", chain), 1,
                        PortDirection.output, net_class = NetClass.cfg))
                    NetUtils.connect(cfg_nets.pop("phit"), ModuleUtils.create_port(module,
                        cls._phit_port_name("phit_o", chain), context.phit_width,
                        PortDirection.output, net_class = NetClass.cfg))
                    NetUtils.connect(ModuleUtils.create_port(module, cls._phit_port_name("phit_o_full", chain), 1,
                        PortDirection.input_, net_class = NetClass.cfg), cfg_nets.pop("phit_full"))
                chains.append(ypos)
                ypos = 0
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
            if inst_cfg_e is None:
                continue
            elif NetUtils.get_source(inst_cfg_e, return_none_if_unconnected = True) is None:
                NetUtils.connect(cls._get_or_create_cfg_ports(module, context.cfg_width, enable_only = True),
                    inst_cfg_e)
            # network pin
            inst_phit_i = instance.pins.get(cls._phit_port_name("phit_i", subchain))
            if inst_phit_i is None:
                continue
            # update chains and instance chain mapping
            try:
                subchain_length = instance.model.cfg_chains[subchain]
            except (AttributeError, IndexError):
                raise PRGAInternalError("{} does not have chain No. {}".format(subchain))
            chainoffsets = getattr(instance, "cfg_chainoffsets", None)
            if chainoffsets is None:
                chainoffsets = instance.cfg_chainoffsets = {}
            chainoffsets[subchain] = chain, ypos
            ypos += subchain_length
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
                        cls._phit_port_name("phit_i", chain), context.phit_width,
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
                cls._phit_port_name("phit_o", chain), context.phit_width,
                PortDirection.output, net_class = NetClass.cfg))
            NetUtils.connect(ModuleUtils.create_port(module, cls._phit_port_name("phit_o_full", chain), 1,
                PortDirection.input_, net_class = NetClass.cfg), cfg_nets.pop("phit_full"))
            chains.append(ypos)
        module.cfg_chains = tuple(chains)
