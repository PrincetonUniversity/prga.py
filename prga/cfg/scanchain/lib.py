# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...core.common import NetClass, ModuleClass, ModuleView, Subtile
from ...core.context import Context
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...passes.translation import AbstractSwitchDatabase
from ...renderer.renderer import FileRenderer
from ...util import Object

import os
from collections import OrderedDict

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
            return self.context.database[ModuleView.logical, key]
        except KeyError:
            pass
        try:
            cfg_bitcount = width.bit_length()
        except AttributeError:
            cfg_bitcount = len(bin(width).lstrip('-0b'))
        switch = Module('sw' + str(width), key = key, ports = OrderedDict(), allow_multisource = True,
                module_class = ModuleClass.switch, cfg_bitcount = cfg_bitcount,
                verilog_template = "switch.tmpl.v")
        # switch inputs/outputs
        i = ModuleUtils.create_port(switch, 'i', width, PortDirection.input_, net_class = NetClass.switch)
        o = ModuleUtils.create_port(switch, 'o', 1, PortDirection.output, net_class = NetClass.switch)
        NetUtils.connect(i, o, fully = True)
        # configuration circuits
        cfg_clk = ModuleUtils.create_port(switch, 'cfg_clk', 1, PortDirection.input_,
                is_clock = True, net_class = NetClass.cfg)
        cfg_e = ModuleUtils.create_port(switch, 'cfg_e', 1, PortDirection.input_, net_class = NetClass.cfg)
        cfg_i = ModuleUtils.create_port(switch, 'cfg_i', self.cfg_width, PortDirection.input_,
                net_class = NetClass.cfg)
        cfg_o = ModuleUtils.create_port(switch, 'cfg_o', self.cfg_width, PortDirection.output,
                net_class = NetClass.cfg)
        return self.context.database.setdefault((ModuleView.logical, key), switch)

# ----------------------------------------------------------------------------
# -- Scanchain Configuration Circuitry Main Entry ----------------------------
# ----------------------------------------------------------------------------
class Scanchain(object):
    """Scanchain configuration circuitry entry point."""

    @classmethod
    def _get_or_create_cfg_ports(cls, module, cfg_width, enable_only = False):
        try:
            if enable_only:
                return module.ports['cfg_e']
            else:
                return tuple(map(lambda x: module.ports[x], ("cfg_clk", "cfg_i", "cfg_o")))
        except KeyError:
            if enable_only:
                return ModuleUtils.create_port(module, 'cfg_e', 1, PortDirection.input_,
                        net_class = NetClass.cfg)
            else:
                cfg_clk = ModuleUtils.create_port(module, 'cfg_clk', 1, PortDirection.input_,
                        is_clock = True, net_class = NetClass.cfg)
                cfg_i = ModuleUtils.create_port(module, 'cfg_i', cfg_width, PortDirection.input_,
                        net_class = NetClass.cfg)
                cfg_o = ModuleUtils.create_port(module, 'cfg_o', cfg_width, PortDirection.output,
                        net_class = NetClass.cfg)
                return cfg_clk, cfg_i, cfg_o

    @classmethod
    def new_context(cls, cfg_width = 1):
        context = Context(cfg_width = cfg_width)
        context._switch_database = ScanchainSwitchDatabase(context, cfg_width)

        # register luts
        for i in range(2, 9):
            lut = Module('lut' + str(i),
                    ports = OrderedDict(),
                    allow_multisource = True,
                    module_class = ModuleClass.primitive,
                    cfg_bitcount = 2 ** i,
                    verilog_template = "lut.tmpl.v")
            # user ports
            in_ = ModuleUtils.create_port(lut, 'in', i, PortDirection.input_, net_class = NetClass.primitive)
            out = ModuleUtils.create_port(lut, 'out', 1, PortDirection.output, net_class = NetClass.primitive)
            NetUtils.connect(in_, out, fully = True)

            # configuration ports
            cfg_clk = ModuleUtils.create_port(lut, 'cfg_clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.cfg)
            cfg_e = ModuleUtils.create_port(lut, 'cfg_e', 1, PortDirection.input_, net_class = NetClass.cfg)
            cfg_i = ModuleUtils.create_port(lut, 'cfg_i', cfg_width, PortDirection.input_,
                    net_class = NetClass.cfg)
            cfg_o = ModuleUtils.create_port(lut, 'cfg_o', cfg_width, PortDirection.output,
                    net_class = NetClass.cfg)
            context._database[ModuleView.logical, lut.key] = lut

        # register flipflops
        if True:
            flipflop = Module('flipflop',
                    ports = OrderedDict(),
                    allow_multisource = True,
                    module_class = ModuleClass.primitive,
                    verilog_template = "flipflop.tmpl.v")
            ModuleUtils.create_port(flipflop, 'clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.primitive)
            ModuleUtils.create_port(flipflop, 'D', 1, PortDirection.input_,
                    clock = 'clk', net_class = NetClass.primitive)
            ModuleUtils.create_port(flipflop, 'Q', 1, PortDirection.output,
                    clock = 'clk', net_class = NetClass.primitive)
            context._database[ModuleView.logical, flipflop.key] = flipflop

        # register single-bit configuration filler
        if True:
            cfg_bit = Module('cfg_bit',
                    ports = OrderedDict(),
                    allow_multisource = True,
                    module_class = ModuleClass.cfg,
                    cfg_bitcount = 1,
                    verilog_template = "cfg_bit.tmpl.v")
            cfg_clk = ModuleUtils.create_port(cfg_bit, 'cfg_clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.cfg)
            cfg_e = ModuleUtils.create_port(cfg_bit, 'cfg_e', 1, PortDirection.input_,
                    net_class = NetClass.cfg)
            cfg_i = ModuleUtils.create_port(cfg_bit, 'cfg_i', cfg_width, PortDirection.input_,
                    net_class = NetClass.cfg)
            cfg_o = ModuleUtils.create_port(cfg_bit, 'cfg_o', cfg_width, PortDirection.output,
                    net_class = NetClass.cfg)
            cfg_d = ModuleUtils.create_port(cfg_bit, 'cfg_d', 1, PortDirection.output,
                    net_class = NetClass.cfg)
            context._database[ModuleView.logical, cfg_bit.key] = cfg_bit

        return context

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        r = FileRenderer()
        r.template_search_paths.insert(0, ADDITIONAL_TEMPLATE_SEARCH_PATH)
        r.template_search_paths.extend(additional_template_search_paths)
        return r

    @classmethod
    def complete_scanchain(cls, context, module):
        """Complete the scanchain."""
        # special process needed for IO blocks (output enable)
        if module.module_class.is_io_block:
            oe = module.ports.get('_oe')
            if oe is not None:
                inst = ModuleUtils.instantiate(module, context.database[ModuleView.logical, 'cfg_bit'], '_cfg_oe')
                NetUtils.connect(inst.pins["cfg_d"], oe)
        # connecting scanchain ports
        cfg_bitoffset = 0
        cfg_clk, cfg_e, cfg_i, cfg_o = (None, ) * 4
        for instance in itervalues(module.instances):
            if instance.model.module_class not in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.cfg):
                if not hasattr(instance.model, 'cfg_bitcount'):
                    cls.complete_scanchain(context, instance.model)
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
                cfg_clk, cfg_i, cfg_o = cls._get_or_create_cfg_ports(module, context.cfg_width)
            instance.cfg_bitoffset = cfg_bitoffset
            NetUtils.connect(cfg_clk, instance.pins['cfg_clk'])
            NetUtils.connect(cfg_i, inst_cfg_i)
            cfg_i = instance.pins['cfg_o']
            cfg_bitoffset += instance.model.cfg_bitcount
        if cfg_i is not None:
            NetUtils.connect(cfg_i, cfg_o)
        module.cfg_bitcount = cfg_bitoffset
