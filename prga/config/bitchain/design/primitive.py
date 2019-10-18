#zO -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import AbstractLeafModule, BaseModule
from prga.arch.primitive.common import PrimitivePortClass, PrimitiveClass
from prga.arch.primitive.port import PrimitiveInputPort, PrimitiveOutputPort, PrimitiveClockPort
from prga.arch.primitive.primitive import AbstractPrimitive, CustomPrimitive
from prga.arch.multimode.port import MultimodeClockPort, MultimodeInputPort, MultimodeOutputPort
from prga.config.bitchain.design.multimode import BitchainMode, BitchainMultimode

import os
from collections import OrderedDict

__all__ = ['CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH',
        'ConfigBitchain', 'FracturableLUT6', 'SynchronousSRFlipflop']

CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

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

# ----------------------------------------------------------------------------
# -- Fractuable 2-mode LUT6 --------------------------------------------------
# ----------------------------------------------------------------------------
class FracturableLUT6(BitchainMultimode):
    """Fracturable LUT6.
    
    Args:
        lut5 (`LUT`): 5-input LUT module to be instantiated logically in the LUT5X2 mode
        lut6 (`LUT`): 6-input LUT module to be instantiated logically in the LUT6X1 mode
    """

    def __init__(self, lut5, lut6):
        super(FracturableLUT6, self).__init__('fraclut6')
        self._add_port(MultimodeInputPort(self, 'in', 6))
        self._add_port(MultimodeOutputPort(self, 'o6', 1, combinational_sources = ('in', )))
        self._add_port(MultimodeOutputPort(self, 'o5', 1, combinational_sources = ('in', )))
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', 1, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', 1, 'cfg_clk'))
        mode_lut6x1 = self._add_mode(BitchainMode('lut6x1', self, {"lut6x1_lutinst": 0}))
        lut6_inst = mode_lut6x1.instantiate(lut6, 'lut6x1_lutinst')
        mode_lut6x1.connect(mode_lut6x1.ports['in'], lut6_inst.pins['in'])
        mode_lut6x1.connect(lut6_inst.pins['out'], mode_lut6x1.ports['o6'])
        mode_lut5x2 = self._add_mode(BitchainMode('lut5x2', self,
            {"lut5x2_lutinst_0": 0, "lut5x2_lutinst_1": 32}, (64, )))
        lutinst0 = mode_lut5x2.instantiate(lut5, 'lut5x2_lutinst_0')
        lutinst1 = mode_lut5x2.instantiate(lut5, 'lut5x2_lutinst_1')
        mode_lut5x2.connect(mode_lut5x2.ports['in'][0:4], lutinst0.pins['in'])
        mode_lut5x2.connect(mode_lut5x2.ports['in'][0:4], lutinst1.pins['in'])
        mode_lut5x2.connect(lutinst0.pins['out'], mode_lut5x2.ports['o6'])
        mode_lut5x2.connect(lutinst1.pins['out'], mode_lut5x2.ports['o5'])

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return "fraclut6.tmpl.v"

    @property
    def config_bit_count(self):
        return 65

# XXX/TODO: use multi-mode modules to implement the modules below
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
