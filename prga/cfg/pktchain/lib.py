# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..scanchain.lib import Scanchain, ScanchainSwitchDatabase
from ...core.common import ModuleClass, ModuleView, NetClass
from ...core.context import Context
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...passes.vpr import FASMDelegate
from ...exception import PRGAAPIError

import os

__all__ = ['Pktchain']

ADDITIONAL_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- Pktchain Configuration Circuitry Main Entry -----------------------------
# ----------------------------------------------------------------------------
class Pktchain(Scanchain):
    """Packetized configuration circuitry entry point."""

    @classmethod
    def new_context(cls, cfg_width = 1, *, dont_add_primitive = tuple()):
        if not 0 < cfg_width <= 8:
            raise PRGAAPIError("Supported configuration width: (0, 8]")
        context = Context("pktchain", cfg_width = cfg_width)
        context._switch_database = ScanchainSwitchDatabase(context, cfg_width)
        context._fasm_delegate = FASMDelegate()
        cls.register_primitives(context, cfg_width, dont_add_primitive)
        return context

    @classmethod
    def register_primitives(cls, context, cfg_width, dont_add_primitive = tuple()):
        super(Pktchain, cls).register_primitives(context, cfg_width, dont_add_primitive)

        # register pktchain_router
        if "pktchain_router" not in dont_add_primitive:
            router = Module("pktchain_router",
                    view = ModuleView.logical,
                    is_cell = True,
                    module_class = ModuleClass.cfg,
                    verilog_template = "pktchain_router.tmpl.v")
            cfg_clk, _0, _1, _2 = cls._get_or_create_cfg_ports(router, cfg_width)
            cfg_we = ModuleUtils.create_port(router, "cfg_we", 1, PortDirection.output,
                    net_class = NetClass.cfg)
            cfg_dout = ModuleUtils.create_port(router, "cfg_dout", cfg_width, PortDirection.output,
                    net_class = NetClass.cfg)
            cfg_din = ModuleUtils.create_port(router, "cfg_din", cfg_width, PortDirection.input_,
                    net_class = NetClass.cfg)
            NetUtils.connect(cfg_clk, [cfg_we, cfg_dout, cfg_din], fully = True)
            context._database[ModuleView.logical, "pktchain_router"] = router

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        r = super(Pktchain, cls).new_renderer(additional_template_search_paths)
        r.template_search_paths.insert(0, ADDITIONAL_TEMPLATE_SEARCH_PATH)
        return r
