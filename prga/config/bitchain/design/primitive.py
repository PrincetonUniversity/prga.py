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
from prga.arch.multimode.port import MultimodeClockPort, MultimodeInputPort, MultimodeOutputPort
from prga.arch.switch.switch import SwitchInstance
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
        mode_lut5x2.connect(mode_lut5x2.ports['in'][0:5], lutinst0.pins['in'])
        mode_lut5x2.connect(mode_lut5x2.ports['in'][0:5], lutinst1.pins['in'])
        mode_lut5x2.connect(lutinst0.pins['out'], mode_lut5x2.ports['o6'])
        mode_lut5x2.connect(lutinst1.pins['out'], mode_lut5x2.ports['o5'])

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return 'fraclut6.tmpl.v'

    @property
    def config_bit_count(self):
        return 65

# ----------------------------------------------------------------------------
# -- Fractuable 2-mode LUT6 with Optional Flip-Flops -------------------------
# ----------------------------------------------------------------------------
class FracturableLUT6FF(BitchainMultimode):
    """Fracturable LUT6 with optional flipflops.
    
    Args:
        lut5 (`LUT`): 5-input LUT module to be instantiated logically in the LUT5X2 mode
        lut6 (`LUT`): 6-input LUT module to be instantiated logically in the LUT6X1 mode
        ff (`Flipflop`): Flipflop module to be instantiated logically in both modes
        mux2 (`ConfigurableMUX`): mux module to be instantiated logically in both modes
    """

    def __init__(self, lut5, lut6, ff, mux2):
        super(FracturableLUT6FF, self).__init__('fraclut6ff')
        self._add_port(MultimodeClockPort(self, 'clk'))
        self._add_port(MultimodeInputPort(self, 'in', 6))
        self._add_port(MultimodeOutputPort(self, 'o6', 1, combinational_sources = ('in', )))
        self._add_port(MultimodeOutputPort(self, 'o5', 1, combinational_sources = ('in', )))
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', 1, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', 1, 'cfg_clk'))

        mode_lut6x1 = self._add_mode(BitchainMode('lut6x1', self,
            {"lut6x1_lutinst": 0, "lut6x1_muxinst": 64}))
        # user-visible instances & connections
        lut6_inst = mode_lut6x1.instantiate(lut6, 'lut6x1_lutinst')
        ff_inst = mode_lut6x1.instantiate(ff, 'lut6x1_ffinst')
        mode_lut6x1.connect(mode_lut6x1.ports['in'], lut6_inst.pins['in'])
        mode_lut6x1.connect(mode_lut6x1.ports['clk'], ff_inst.pins['clk'])
        mode_lut6x1.connect(lut6_inst.pins['out'], mode_lut6x1.ports['o6'])
        mode_lut6x1.connect(lut6_inst.pins['out'], ff_inst.pins['D'], pack_pattern = True)
        mode_lut6x1.connect(ff_inst.pins['Q'], mode_lut6x1.ports['o6'])
        # user-invisible instances & connections
        mux2_inst = mode_lut6x1._add_instance(SwitchInstance(mode_lut6x1, mux2, 'lut6x1_muxinst'))
        mode_lut6x1.logical_ports['o6'].logical_source = mux2_inst.logical_pins['o']
        mux2_inst.logical_pins['i'][0].logical_source = lut6_inst.logical_pins['out'][0]
        mux2_inst.logical_pins['i'][1].logical_source = ff_inst.logical_pins['Q'][0]

        mode_lut5x2 = self._add_mode(BitchainMode('lut5x2', self,
            {"lut5x2_lutinst_0": 0, "lut5x2_lutinst_1": 32, "lut5x2_muxinst_0": 64, "lut5x2_muxinst_1": 65}, (66, )))
        for i, out in zip(range(2), ('o6', 'o5')):
            # user-visible instances & connections
            lutinst = mode_lut5x2.instantiate(lut5, 'lut5x2_lutinst_' + str(i))
            ffinst = mode_lut5x2.instantiate(ff, 'lut5x2_ffinst_' + str(i))
            mode_lut5x2.connect(mode_lut5x2.ports['in'][0:5], lutinst.pins['in'])
            mode_lut5x2.connect(mode_lut5x2.ports['clk'], ffinst.pins['clk'])
            mode_lut5x2.connect(lutinst.pins['out'], mode_lut5x2.ports[out])
            mode_lut5x2.connect(lutinst.pins['out'], ffinst.pins['D'], pack_pattern = True)
            mode_lut5x2.connect(ffinst.pins['Q'], mode_lut5x2.ports[out])
            # user-invisible instances & connections
            muxinst = mode_lut5x2._add_instance(SwitchInstance(mode_lut5x2, mux2, 'lut5x2_muxinst_' + str(i)))
            mode_lut5x2.logical_ports[out].logical_source = muxinst.logical_pins['o']
            muxinst.logical_pins['i'][0].logical_source = lutinst.logical_pins['out'][0]
            muxinst.logical_pins['i'][1].logical_source = ffinst.logical_pins['Q'][0]

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return 'fraclut6ff.tmpl.v'

    @property
    def config_bit_count(self):
        return 67

# # XXX/TODO: use multi-mode modules to implement the modules below
# # ----------------------------------------------------------------------------
# # -- 7-mode Flip-flop --------------------------------------------------------
# # ----------------------------------------------------------------------------
# class SynchronousSRFlipflop(BaseModule, AbstractPrimitive):
#     """7-mode synchronous set/reset flipflop."""
# 
#     __slots__ = ['_ports']
#     def __init__(self):
#         super(SynchronousSRFlipflop, self).__init__('sff')
#         self._ports = OrderedDict()
#         self._add_port(PrimitiveClockPort(self, 'clk', port_class = PrimitivePortClass.clock))
#         self._add_port(PrimitiveInputPort(self, 'rst', 1, clock = 'clk'))
#         self._add_port(PrimitiveInputPort(self, 'ce', 1, clock = 'clk'))
#         self._add_port(PrimitiveInputPort(self, 'd', 1, clock = 'clk', port_class = PrimitivePortClass.D))
#         self._add_port(PrimitiveOutputPort(self, 'q', 1, clock = 'clk', port_class = PrimitivePortClass.Q))
#         self._add_port(ConfigClockPort(self, 'cfg_clk'))
#         self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
#         self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
#         self._add_port(ConfigInputPort(self, 'cfg_i', 1, 'cfg_clk'))
#         self._add_port(ConfigOutputPort(self, 'cfg_o', 1, 'cfg_clk'))
# 
#     # == low-level API =======================================================
#     # -- implementing properties/methods required by superclass --------------
#     @property
#     def primitive_class(self):
#         return PrimitiveClass.flipflop
# 
#     @property
#     def verilog_template(self):
#         return "sff.v"
# 
# # ----------------------------------------------------------------------------
# # -- Carry Chain -------------------------------------------------------------
# # ----------------------------------------------------------------------------
# carrychain = CustomPrimitive('carrychain', 'carrychain.v')
# carrychain.create_input('p', 1)
# carrychain.create_input('g', 1)
# carrychain.create_input('ci', 1)
# carrychain.create_output('s', 1, combinational_sources = ('p', 'g', 'ci'))
# carrychain.create_output('co', 1, combinational_sources = ('p', 'g', 'ci'))
