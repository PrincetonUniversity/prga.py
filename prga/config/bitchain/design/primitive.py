# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import AbstractLeafModule, BaseModule
from prga.arch.primitive.common import PrimitivePortClass, PrimitiveClass
from prga.arch.primitive.port import PrimitiveInputPort, PrimitiveOutputPort, PrimitiveClockPort
from prga.arch.primitive.primitive import AbstractPrimitive, CustomPrimitive

import os
from collections import OrderedDict

__all__ = ['CONFIG_BITCHAIN_SEARCH_PATH', 'ConfigBitchain', 'FracturableLUT6', 'SynchronousSRFlipflop']

CONFIG_BITCHAIN_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- Configuration Bitchain Module -------------------------------------------
# ----------------------------------------------------------------------------
class ConfigBitchain(BaseModule, AbstractLeafModule):
    """Configuration circuitry: bit chain.

    Args:
        width (:obj:`int`): Number of config bits in this chain
        name (:obj:`str`): Name of this module. Default to 'cfg_bitchain{width}'
    """

    __slots__ = ['_ports']
    def __init__(self, width, name = None):
        name = name or ("cfg_bitchain" + str(width))
        super(ConfigBitchain, self).__init__(name)
        self._ports = OrderedDict()
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', 1, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', 1, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_d', width, 'cfg_clk'))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.config

    @property
    def verilog_template(self):
        return "cfg_bitchain.tmpl.v"

# XXX/TODO: use multi-mode modules to implement the modules below
# ----------------------------------------------------------------------------
# -- Fractuable 2-mode LUT6 --------------------------------------------------
# ----------------------------------------------------------------------------
class FracturableLUT6(BaseModule, AbstractPrimitive):
    """Fracturable LUT6."""

    __slots__ = ['_ports']
    def __init__(self):
        super(FracturableLUT6, self).__init__('fraclut6')
        self._ports = OrderedDict()
        self._add_port(PrimitiveInputPort(self, 'in', 6, port_class = PrimitivePortClass.lut_in))
        self._add_port(PrimitiveOutputPort(self, 'o6', 1, combinational_sources = ('in', ),
                port_class = PrimitivePortClass.lut_out))
        self._add_port(PrimitiveOutputPort(self, 'o5', 1, combinational_sources = ('in', ),
                port_class = PrimitivePortClass.lut_out))
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', 1, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', 1, 'cfg_clk'))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def primitive_class(self):
        return PrimitiveClass.lut

    @property
    def verilog_template(self):
        return "fraclut6.tmpl.v"

# ----------------------------------------------------------------------------
# -- 7-mode Flip-flop --------------------------------------------------------
# ----------------------------------------------------------------------------
class SynchronousSRFlipflop(BaseModule, AbstractPrimitive):
    """7-mode synchronous set/reset flipflop."""

    __slots__ = ['_ports']
    def __init__(self):
        super(SynchronousSRFlipflop, self).__init__('sff')
        self._ports = OrderedDict()
        self._add_port(PrimitiveClockPort(self, 'clk', port_class = PrimitivePortClass.clock))
        self._add_port(PrimitiveInputPort(self, 'rst', 1, clock = 'clk'))
        self._add_port(PrimitiveInputPort(self, 'ce', 1, clock = 'clk'))
        self._add_port(PrimitiveInputPort(self, 'd', 1, clock = 'clk', port_class = PrimitivePortClass.D))
        self._add_port(PrimitiveOutputPort(self, 'q', 1, clock = 'clk', port_class = PrimitivePortClass.Q))
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', 1, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', 1, 'cfg_clk'))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def primitive_class(self):
        return PrimitiveClass.flipflop

    @property
    def verilog_template(self):
        return "sff.v"

# ----------------------------------------------------------------------------
# -- Carry Chain -------------------------------------------------------------
# ----------------------------------------------------------------------------
carrychain = CustomPrimitive('carrychain', 'carrychain.v')
carrychain.create_input('p', 1)
carrychain.create_input('g', 1)
carrychain.create_input('ci', 1)
carrychain.create_output('s', 1, combinational_sources = ('p', 'g', 'ci'))
carrychain.create_output('co', 1, combinational_sources = ('p', 'g', 'ci'))
