# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import AbstractLeafModule, BaseModule
from prga.arch.primitive.common import PrimitivePortClass, PrimitiveClass
from prga.arch.primitive.port import PrimitiveInputPort, PrimitiveOutputPort, PrimitiveClockPort
from prga.arch.primitive.primitive import AbstractPrimitive
from prga.arch.multimode.port import MultimodeClockPort, MultimodeInputPort, MultimodeOutputPort
from prga.arch.switch.switch import SwitchInstance
from prga.flow.delegate import PRGAPrimitiveNotFoundError, PrimitiveRequirement
from prga.config.bitchain.design.multimode import BitchainMode, BitchainMultimode

import os
from collections import OrderedDict

__all__ = ['CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH',
        'ConfigBitchain', 'FracturableLUT6', 'FracturableLUT6FF', 'FracturableLUT6WithSFFnCarry']

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
        context (`ArchitectureContext`): Architecture context in which this primitive will be added to
        in_physical_domain (:obj:`bool`): If this module is in the physical domain
    """

    __slots__ = ['in_physical_domain']
    def __init__(self, context, in_physical_domain = True):
        lut5 = context.primitive_library.get_or_create_primitive('lut5', PrimitiveRequirement.non_physical_preferred)
        lut6 = context.primitive_library.get_or_create_primitive('lut6', PrimitiveRequirement.non_physical_preferred)

        super(FracturableLUT6, self).__init__('fraclut6')
        self.in_physical_domain = in_physical_domain
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
        context (`ArchitectureContext`): Architecture context in which this primitive will be added to
        in_physical_domain (:obj:`bool`): If this module is in the physical domain
    """

    __slots__ = ['in_physical_domain']
    def __init__(self, context, in_physical_domain = True):
        lib = context.primitive_library
        lut5 = lib.get_or_create_primitive('lut5', PrimitiveRequirement.non_physical_preferred)
        lut6 = lib.get_or_create_primitive('lut6', PrimitiveRequirement.non_physical_preferred)
        ff = lib.get_or_create_primitive('flipflop', PrimitiveRequirement.non_physical_preferred)
        mux2 = context.switch_library.get_or_create_switch(2, None, False)

        super(FracturableLUT6FF, self).__init__('fraclut6ff')
        self.in_physical_domain = in_physical_domain
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
        mode_lut6x1.connect(lut6_inst.pins['out'], ff_inst.pins['D'], pack_pattern = 'lut6_dff')
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
            mode_lut5x2.connect(lutinst.pins['out'], ffinst.pins['D'], pack_pattern = 'lut5_dff_' + str(i))
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

# ----------------------------------------------------------------------------
# -- Fractuable LUT6 with Multi-functional Flip-Flops and Carry Chain --------
# ----------------------------------------------------------------------------
class FracturableLUT6WithSFFnCarry(BitchainMultimode):
    """Fracturable LUT6 with multi-functional flip-flops and carry chain.

    Args:
        context (`ArchitectureContext`): Architecture context in which this primitive will be added to
        in_physical_domain (:obj:`bool`): If this module is in the physical domain
    """

    __slots__ = ['in_physical_domain']
    def __init__(self, context, in_physical_domain):
        lib = context.primitive_library
        lut5 = lib.get_or_create_primitive('lut5', PrimitiveRequirement.non_physical_preferred)
        lut6 = lib.get_or_create_primitive('lut6', PrimitiveRequirement.non_physical_preferred)
        mux2 = context.switch_library.get_or_create_switch(2, None, False)
        mux4 = context.switch_library.get_or_create_switch(4, None, False)
        multimodedff = self.__get_multimodedff(lib)
        carrychain = self.__get_carrychain(lib)

        super(FracturableLUT6WithSFFnCarry, self).__init__('fraclut6sffc')
        self.in_physical_domain = in_physical_domain
        self._add_port(MultimodeClockPort(self, 'clk'))
        self._add_port(MultimodeInputPort(self, 'ce', 1))
        self._add_port(MultimodeInputPort(self, 'sr', 1))
        self._add_port(MultimodeInputPort(self, 'ia', 6))
        self._add_port(MultimodeInputPort(self, 'ib', 1))
        self._add_port(MultimodeInputPort(self, 'cin', 1))
        self._add_port(MultimodeOutputPort(self, 'cout', 1))
        self._add_port(MultimodeOutputPort(self, 'oa', 1))
        self._add_port(MultimodeOutputPort(self, 'ob', 1))
        self._add_port(MultimodeOutputPort(self, 'q', 1))
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', 1, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', 1, 'cfg_clk'))

        # mode 1: (LUT6 + DFF) + carrychain + Multi-functional D-Flipflop
        self.__create_mode_lut6dff(lut6, multimodedff, carrychain, mux4)

        # mode 2: 2x(LUT5 + DFF) + carrychain
        self.__create_mode_lut5dffx2(lut5, multimodedff, carrychain, mux2, mux4)

    def __get_multimodedff(self, lib):
        try:
            multimodedff = lib.get_or_create_primitive('multimodedff', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            multimodedff = lib.create_custom_primitive('multimodedff')
            multimodedff.parameters['ENABLE_CE'] = {'init': "1'b0", 'config_bit_offset': 0, 'config_bit_count': 1}
            multimodedff.parameters['ENABLE_SR'] = {'init': "1'b0", 'config_bit_offset': 1, 'config_bit_count': 1}
            multimodedff.parameters['SR_SET'] = {'init': "1'b0", 'config_bit_offset': 2, 'config_bit_count': 1}
            multimodedff.create_clock('clk')
            multimodedff.create_input('d', 1, clock = 'clk')
            multimodedff.create_input('ce', 1, clock = 'clk')
            multimodedff.create_input('sr', 1, clock = 'clk')
            multimodedff.create_output('q', 1, clock = 'clk')
        return multimodedff

    def __get_carrychain(self, lib):
        try:
            carrychain = lib.get_or_create_primitive('carrychain', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            carrychain = lib.create_custom_primitive('carrychain')
            carrychain.parameters['CIN_FABRIC'] = {'init': "1'b0", 'config_bit_offset': 0, 'config_bit_count': 1}
            carrychain.create_input('p', 1)
            carrychain.create_input('g', 1)
            carrychain.create_input('cin', 1)
            carrychain.create_input('cin_fabric', 1)
            carrychain.create_output('s', 1, combinational_sources = ('p', 'g', 'cin', 'cin_fabric'))
            carrychain.create_output('cout', 1, combinational_sources = ('p', 'g', 'cin', 'cin_fabric'))
            carrychain.create_output('cout_fabric', 1, combinational_sources = ('p', 'g', 'cin', 'cin_fabric'))
        return carrychain

    def __create_mode_lut6dff(self, lut6, multimodedff, carrychain, mux4):
        mode = self._add_mode(BitchainMode('lut6dff', self, {
            "lut6_inst": 3,     # LUT5A_DATA, LUT5B_DATA:                       66:3
            "ffa_inst": 73,     # FFA_ENABLE_CE, FFA_ENABLE_SR, FFA_SR_SET:     75:73
            "ffb_inst": 78,     # FFB_ENABLE_CE, FFB_ENABLE_SR, FFB_SR_SET:     80:78
            },
            (67, 72, 77, 83)    # LUT6_ENABLE, FFA_SOURCE = FFA_O6, FFB_SOURCE = FFB_IB, OB_SEL = OB_QB
            ))
        lut6_inst = mode.instantiate(lut6, 'lut6_inst')
        ffa_inst = mode.instantiate(multimodedff, 'ffa_inst')
        ffb_inst = mode.instantiate(multimodedff, 'ffb_inst')
        # LUT6 connections
        mode.connect(mode.ports['ia'], lut6_inst.pins['in'])
        mode.connect(lut6_inst.pins['out'], ffa_inst.pins['d'], pack_pattern = 'lut6_dff')
        mode.connect(lut6_inst.pins['out'], mode.ports['oa'])
        # Flipflop connections
        for ff in (ffa_inst, ffb_inst):
            mode.connect(mode.ports['clk'], ff.pins['clk'])
            mode.connect(mode.ports['ce'], ff.pins['ce'])
            mode.connect(mode.ports['sr'], ff.pins['sr'])
        mode.connect(mode.ports['ib'], ffb_inst.pins['d'])
        mode.connect(ffa_inst.pins['q'], mode.ports['q'])
        mode.connect(ffb_inst.pins['q'], mode.ports['ob'])

    def __create_mode_lut5dffx2(self, lut5, multimodedff, carrychain, mux2, mux4):
        mode = self._add_mode(BitchainMode('lut5dffx2', self, {
            "lut5_inst_0":  3,  # LUT5A_DATA:                                   34:3
            "lut5_inst_1":  35, # LUT5B_DATA:                                   66:35
            "mux_carry_g":  68, # CARRY_SOURCE_G:                               68
            "mux_carry_cin":69, # CARRY_SOURCE_CIN:                             69
            "carry_inst":   70, # CARRY_SOURCE_CIN:                             70
            "mux_ffa_d":    72, # FFA_SOURCE:                                   72
            "ffa_inst":     73, # FFA_ENABLE_CE, FFA_ENABLE_SR, FFA_SR_SET:     75:73
            "mux_ffb_d":    76, # FFB_SOURCE:                                   77:76
            "ffb_inst":     78, # FFB_ENABLE_CE, FFB_ENABLE_SR, FFB_SR_SET:     80:78
            "mux_oa":       81, # OA_SEL:                                       81
            "mux_ob":       82, # OB_SEL:                                       83:82
            },
            ))
        lut5_inst = [mode.instantiate(lut5, 'lut5_inst_' + str(i)) for i in range(2)]
        ff_inst = [mode.instantiate(multimodedff, name) for name in ("ffa_inst", "ffb_inst")]
        carry_inst = mode.instantiate(carrychain, 'carry_inst')
        # LUT5+DFF
        for i in range(2):
            mode.connect(mode.ports['ia'][0:5], lut5_inst[i].pins['in'])
            mode.connect(carry_inst.pins['cout_fabric'], ff_inst[i].pins['d'])
            mode.connect(lut5_inst[i].pins['out'], ff_inst[i].pins['d'], pack_pattern = 'lut5_dff_' + str(i))
            mode.connect(mode.ports['clk'], ff_inst[i].pins['clk'])
            mode.connect(mode.ports['ce'], ff_inst[i].pins['ce'])
            mode.connect(mode.ports['sr'], ff_inst[i].pins['sr'])
        # carry chain
        mode.connect(lut5_inst[0].pins['out'], carry_inst.pins['p'])
        mode.connect(lut5_inst[1].pins['out'], carry_inst.pins['g'])
        mode.connect(mode.ports['ib'], carry_inst.pins['g'])
        mode.connect(mode.ports['cin'], carry_inst.pins['cin'], pack_pattern = 'carrychain')
        mode.connect(mode.ports['ib'], carry_inst.pins['cin_fabric'])
        mode.connect(lut5_inst[1].pins['out'], carry_inst.pins['cin_fabric'])
        mode.connect(carry_inst.pins['cout'], mode.ports['cout'], pack_pattern = 'carrychain')
        mode.connect(carry_inst.pins['s'], ff_inst[1].pins['d'], pack_pattern = 'carrychain')
        # oa
        mode.connect(lut5_inst[0].pins['out'], mode.ports['oa'])
        mode.connect(carry_inst.pins['s'], mode.ports['oa'])
        # q
        mode.connect(ff_inst[0].pins['q'], mode.ports['q'])
        # ob
        mode.connect(carry_inst.pins['cout_fabric'], mode.ports['ob'])
        mode.connect(carry_inst.pins['s'], mode.ports['ob'])
        mode.connect(ff_inst[1].pins['q'], mode.ports['ob'])
        mode.connect(lut5_inst[1].pins['out'], mode.ports['ob'])
        # now the user-invisible part
        # mux for the input 'g' of the carry chain
        mux_carry = mode._add_instance(SwitchInstance(mode, mux2, 'mux_carry_g'))
        mux_carry.switch_inputs[0].logical_source = mode.ports['ib'][0]
        mux_carry.switch_inputs[1].logical_source = lut5_inst[1].pins['out'][0]
        carry_inst.pins['g'][0].logical_source = mux_carry.switch_output
        # mux for the input 'cin' of the carry chain
        mux_cin = mode._add_instance(SwitchInstance(mode, mux2, 'mux_carry_cin'))
        mux_cin.switch_inputs[0].logical_source = mode.ports['ib'][0]
        mux_cin.switch_inputs[1].logical_source = lut5_inst[1].pins['out'][0]
        carry_inst.pins['cin_fabric'][0].logical_source = mux_cin.switch_output
        # mux for input 'd' of Flip-flop A
        mux_ffa_d = mode._add_instance(SwitchInstance(mode, mux2, 'mux_ffa_d'))
        mux_ffa_d.switch_inputs[0].logical_source = carry_inst.pins['cout_fabric'][0]
        mux_ffa_d.switch_inputs[1].logical_source = lut5_inst[0].pins['out'][0]
        ff_inst[0].pins['d'].logical_source = mux_ffa_d.switch_output
        # mux for input 'd' of Flip-flop B
        mux_ffb_d = mode._add_instance(SwitchInstance(mode, mux4, 'mux_ffb_d'))
        mux_ffb_d.switch_inputs[0].logical_source = carry_inst.pins['cout_fabric'][0]
        mux_ffb_d.switch_inputs[1].logical_source = carry_inst.pins['s'][0]
        mux_ffb_d.switch_inputs[2].logical_source = mode.ports['ib'][0]
        mux_ffb_d.switch_inputs[3].logical_source = lut5_inst[1].pins['out'][0]
        ff_inst[1].pins['d'].logical_source = mux_ffb_d.switch_output
        # mux for output port 'oa'
        mux_oa = mode._add_instance(SwitchInstance(mode, mux2, 'mux_oa'))
        mux_oa.switch_inputs[0].logical_source = lut5_inst[0].pins['out'][0]
        mux_oa.switch_inputs[1].logical_source = carry_inst.pins['s'][0]
        mode.ports['oa'][0].logical_source = mux_oa.switch_output
        # mux for output port 'ob'
        mux_ob = mode._add_instance(SwitchInstance(mode, mux4, 'mux_ob'))
        mux_ob.switch_inputs[0].logical_source = carry_inst.pins['cout_fabric'][0]
        mux_ob.switch_inputs[1].logical_source = carry_inst.pins['s'][0]
        mux_ob.switch_inputs[2].logical_source = ff_inst[1].pins['q'][0]
        mux_ob.switch_inputs[3].logical_source = lut5_inst[1].pins['out'][0]
        mode.ports['ob'][0].logical_source = mux_ob.switch_output

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return 'fraclut6sffc.tmpl.v'

    @property
    def config_bit_count(self):
        return 84
