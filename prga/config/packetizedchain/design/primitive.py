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
from prga.config.packetizedchain.design.multimode import PacketizedchainMode, PacketizedchainMultimode
from prga.exception import PRGAInternalError

import os
from collections import OrderedDict

__all__ = ['CONFIG_PACKETIZED_CHAIN_TEMPLATE_SEARCH_PATH', 'ConfigWidechain', 'ConfigPacketizedChainCtrl',
        'PacketizedChainFracturableLUT6', 'PacketizedChainFracturableLUT6WithSFFnCarry']

CONFIG_PACKETIZED_CHAIN_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- Configuration Chain Module ----------------------------------------------
# ----------------------------------------------------------------------------
class ConfigWidechain(BaseModule, AbstractLeafModule):
    """Configuration circuitry: wide chain.

    Args:
        width (:obj:`int`): Number of config bits in this chain
        config_width (:obj:`int`): Width of the config input port
        name (:obj:`str`): Name of this module. Default to 'cfgwc_b{width}_x{config_width}'
    """

    __slots__ = ['_ports']
    def __init__(self, width, config_width, name = None):
        name = name or "cfgwc_b{}_x{}".format(width, config_width)
        super(ConfigWidechain, self).__init__(name)
        self._ports = OrderedDict()
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', config_width, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', config_width, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_d', width, 'cfg_clk'))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.config

    @property
    def verilog_template(self):
        return "cfg_widechain.tmpl.v"

# ----------------------------------------------------------------------------
# -- Configuration Control Module --------------------------------------------
# ----------------------------------------------------------------------------
class ConfigPacketizedChainCtrl(BaseModule, AbstractLeafModule):
    """Configuration circuitry: control for packetized chain.

    Args:
        config_width (:obj:`int`): Width of the config input port
        name (:obj:`str`): Name of this module. Default to 'cfgctrl_x{config_width}'
        magic_sop (:obj:`int`): 8-bit magic number marking the start of a config packet
    """

    __slots__ = ['_ports', '_magic_sop']
    def __init__(self, config_width, name = None, magic_sop = 0xA5):
        name = name or "cfgctrl_x{}".format(config_width)
        if magic_sop <= 0 or magic_sop > 0xFF:
            raise PRGAInternalError("Magic number for start of packet must be an 8-bit number larger than 0")
        super(ConfigPacketizedChainCtrl, self).__init__(name)
        self._ports = OrderedDict()
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1))
        self._add_port(ConfigInputPort(self, 'cfg_pkt_val_i', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_pkt_data_i', config_width, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_pkt_val_o', 1, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_pkt_data_o', config_width, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_din', config_width, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_dout', config_width, 'cfg_clk'))
        self._magic_sop = magic_sop

    # == low-level API =======================================================
    @property
    def magic_sop(self):
        """:obj:`int`: A magic number for the start of the packet"""
        return self._magic_sop

    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.config

    @property
    def verilog_template(self):
        return "cfg_ctrl.tmpl.v"

# ----------------------------------------------------------------------------
# -- Fractuable 2-mode LUT6 --------------------------------------------------
# ----------------------------------------------------------------------------
class PacketizedChainFracturableLUT6(PacketizedchainMultimode):
    """Fracturable LUT6. This is to be used for `PacketizedChainFracturableLUT6` only because of some
    specially-defined pack patterns and modes.
    
    Args:
        context (`ArchitectureContext`): Architecture context in which this primitive will be added to
    """

    def __init__(self, context):
        lut5 = context.primitive_library.get_or_create_primitive('lut5', PrimitiveRequirement.non_physical_preferred)
        lut6 = context.primitive_library.get_or_create_primitive('lut6', PrimitiveRequirement.non_physical_preferred)

        super(PacketizedChainFracturableLUT6, self).__init__('fraclut6')
        self._add_port(MultimodeInputPort(self, 'in', 6))
        self._add_port(MultimodeOutputPort(self, 'o6', 1, combinational_sources = ('in', )))
        self._add_port(MultimodeOutputPort(self, 'o5', 2, combinational_sources = ('in', )))

        mode_lut6x1 = self._add_mode(PacketizedchainMode('lut6x1', self, {"lut6x1_lutinst": 0}, (64, )))
        lut6_inst = mode_lut6x1.instantiate(lut6, 'lut6x1_lutinst')
        mode_lut6x1.connect(mode_lut6x1.ports['in'], lut6_inst.pins['in'])
        mode_lut6x1.connect(lut6_inst.pins['out'], mode_lut6x1.ports['o6'], pack_pattern='lut6_dff')

        mode_lut5x2 = self._add_mode(PacketizedchainMode('lut5x2', self,
            {"lut5x2_lutinst_0": 0, "lut5x2_lutinst_1": 32}))
        lutinst0 = mode_lut5x2.instantiate(lut5, 'lut5x2_lutinst_0')
        lutinst1 = mode_lut5x2.instantiate(lut5, 'lut5x2_lutinst_1')
        mode_lut5x2.connect(mode_lut5x2.ports['in'][0:5], lutinst0.pins['in'])
        mode_lut5x2.connect(mode_lut5x2.ports['in'][0:5], lutinst1.pins['in'])
        mode_lut5x2.connect(lutinst0.pins['out'], mode_lut5x2.ports['o5'][0],
                pack_pattern=('lut5_dff0', 'carrychain'))
        mode_lut5x2.connect(lutinst1.pins['out'], mode_lut5x2.ports['o5'][1],
                pack_pattern=('lut5_dff1', 'carrychain'))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def in_physical_domain(self):
        return False

    @property
    def config_bitcount(self):
        return 65

# ----------------------------------------------------------------------------
# -- Fractuable LUT6 with Multi-functional Flip-Flops and Carry Chain --------
# ----------------------------------------------------------------------------
class PacketizedChainFracturableLUT6WithSFFnCarry(PacketizedchainMultimode):
    """Fracturable LUT6 with multi-functional flip-flops and carry chain.

    Args:
        context (`ArchitectureContext`): Architecture context in which this primitive will be added to
        config_width (:obj:`int`): Width of the config ports
        in_physical_domain (:obj:`bool`): If this module is in the physical domain
    """

    __slots__ = ['in_physical_domain']
    def __init__(self, context, config_width, in_physical_domain = True):
        lib = context.primitive_library
        mux2 = context.switch_library.get_or_create_switch(2, None, False)
        mux4 = context.switch_library.get_or_create_switch(4, None, False)
        fraclut6 = lib.get_or_create_primitive('fraclut6', PrimitiveRequirement.non_physical_preferred)
        multimodedff = self.__get_multimodedff(lib)
        carrychain = self.__get_carrychain(lib)

        super(PacketizedChainFracturableLUT6WithSFFnCarry, self).__init__('fraclut6sffc')
        self.in_physical_domain = in_physical_domain
        self._add_port(MultimodeClockPort(self, 'clk'))
        self._add_port(MultimodeInputPort(self, 'ce', 1))
        self._add_port(MultimodeInputPort(self, 'sr', 1))
        self._add_port(MultimodeInputPort(self, 'ia', 6))
        self._add_port(MultimodeInputPort(self, 'ib', 2))
        self._add_port(MultimodeInputPort(self, 'cin', 1))
        self._add_port(MultimodeOutputPort(self, 'cout', 1))
        self._add_port(MultimodeOutputPort(self, 'oa', 1))
        self._add_port(MultimodeOutputPort(self, 'ob', 1))
        self._add_port(MultimodeOutputPort(self, 'q', 1))
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', config_width, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', config_width, 'cfg_clk'))

        mode = self._add_mode(PacketizedchainMode('default', self, {
            'lut_inst':      3,  # LUT5A_DATA, LUT5B_DATA, LUT6_ENABLE:         67:3
            'mux_carry_p':   68, # CARRY_SOURCE_P:                              68
            'mux_carry_g':   69, # CARRY_SOURCE_G:                              69
            'mux_carry_cin': 70, # CARRY_SOURCE_CIN:                            70
            'carry_inst':    71, # CARRY_SOURCE_CIN:                            71
            "mux_ffa_d":     72, # FFA_SOURCE:                                  73:72
            "ffa_inst":      74, # FFA_ENABLE_CE, FFA_ENABLE_SR, FFA_SR_SET:    76:74
            "mux_ffb_d":     77, # FFB_SOURCE:                                  78:77
            "ffb_inst":      79, # FFB_ENABLE_CE, FFB_ENABLE_SR, FFB_SR_SET:    80:79
            "mux_oa":        82, # OA_SEL:                                      82
            "mux_ob":        83, # OB_SEL:                                      84:83
            }))
        lut_inst = mode.instantiate(fraclut6, 'lut_inst')
        carry_inst = mode.instantiate(carrychain, 'carry_inst')
        ffa_inst = mode.instantiate(multimodedff, 'ffa_inst')
        ffb_inst = mode.instantiate(multimodedff, 'ffb_inst')
        # lut
        mode.connect(mode.ports['ia'], lut_inst.pins['in'])
        # ff-A
        mode.connect(lut_inst.pins['o6'], ffa_inst.pins['d'], pack_pattern = 'lut6_dff')
        mode.connect(lut_inst.pins['o5'][0], ffa_inst.pins['d'], pack_pattern = 'lut5_dff0')
        mode.connect(mode.ports['ib'][0], ffa_inst.pins['d'])
        mode.connect(mode.ports['clk'], ffa_inst.pins['clk'])
        mode.connect(mode.ports['ce'], ffa_inst.pins['ce'])
        mode.connect(mode.ports['sr'], ffa_inst.pins['sr'])
        # ff-B
        mode.connect(lut_inst.pins['o5'][1], ffb_inst.pins['d'], pack_pattern = 'lut5_dff1')
        mode.connect(mode.ports['ib'][1], ffb_inst.pins['d'])
        mode.connect(mode.ports['clk'], ffb_inst.pins['clk'])
        mode.connect(mode.ports['ce'], ffb_inst.pins['ce'])
        mode.connect(mode.ports['sr'], ffb_inst.pins['sr'])
        # carry chain
        mode.connect(lut_inst.pins['o6'], carry_inst.pins['p'])
        mode.connect(lut_inst.pins['o5'][0], carry_inst.pins['p'], pack_pattern = 'carrychain')
        mode.connect(lut_inst.pins['o5'][1], carry_inst.pins['g'], pack_pattern = 'carrychain')
        mode.connect(mode.ports['ib'][0], carry_inst.pins['p'])
        mode.connect(mode.ports['ib'][1], carry_inst.pins['g'])
        mode.connect(mode.ports['cin'], carry_inst.pins['cin'], pack_pattern = 'carrychain')
        mode.connect(mode.ports['ib'][0], carry_inst.pins['cin_fabric'])
        mode.connect(lut_inst.pins['o5'][1], carry_inst.pins['cin_fabric'])
        mode.connect(carry_inst.pins['cout'], mode.ports['cout'], pack_pattern = 'carrychain')
        mode.connect(carry_inst.pins['s'], ffa_inst.pins['d'], pack_pattern = 'carrychain')
        mode.connect(carry_inst.pins['s'], ffb_inst.pins['d'], pack_pattern = 'carrychain')
        mode.connect(carry_inst.pins['cout_fabric'], ffb_inst.pins['d'])
        # oa
        mode.connect(lut_inst.pins['o6'], mode.ports['oa'])
        mode.connect(lut_inst.pins['o5'][0], mode.ports['oa'])
        mode.connect(carry_inst.pins['s'], mode.ports['oa'])
        # q
        mode.connect(ffa_inst.pins['q'], mode.ports['q'])
        # ob
        mode.connect(carry_inst.pins['cout_fabric'], mode.ports['ob'])
        mode.connect(carry_inst.pins['s'], mode.ports['ob'])
        mode.connect(ffb_inst.pins['q'], mode.ports['ob'])
        mode.connect(lut_inst.pins['o5'][1], mode.ports['ob'])

        # now the user-invisible part
        # mux for the input 'd' of Flip-Flop A
        #   pre-select: this is a logical-only switch that does not need configuration
        mux_ffa_d_pre = mode._add_instance(SwitchInstance(mode, mux2, 'mux_ffa_d_pre'))
        mux_ffa_d_pre.switch_inputs[0].logical_source = lut_inst.pins['o6'][0]
        mux_ffa_d_pre.switch_inputs[1].logical_source = lut_inst.pins['o5'][0]
        #   main mux
        mux_ffa_d = mode._add_instance(SwitchInstance(mode, mux4, 'mux_ffa_d'))
        mux_ffa_d.switch_inputs[0].logical_source = mux_ffa_d_pre.switch_output
        mux_ffa_d.switch_inputs[1].logical_source = carry_inst.pins['s'][0]
        mux_ffa_d.switch_inputs[2].logical_source = mode.ports['ib'][0]
        mux_ffa_d.switch_inputs[3].logical_source = lut_inst.pins['o5'][1]
        ffa_inst.pins['d'].logical_source = mux_ffa_d.switch_output
        # mux for the input 'd' of Flip-Flop B
        mux_ffb_d = mode._add_instance(SwitchInstance(mode, mux4, 'mux_ffb_d'))
        mux_ffb_d.switch_inputs[0].logical_source = carry_inst.pins['cout_fabric'][0]
        mux_ffb_d.switch_inputs[1].logical_source = carry_inst.pins['s'][0]
        mux_ffb_d.switch_inputs[2].logical_source = mode.ports['ib'][1]
        mux_ffb_d.switch_inputs[3].logical_source = lut_inst.pins['o5'][1]
        ffb_inst.pins['d'].logical_source = mux_ffb_d.switch_output
        # mux for the input 'p' of the carry chain
        #   pre-select: this is a logical-only switch that does not need configuration
        mux_carry_p_pre = mode._add_instance(SwitchInstance(mode, mux2, 'mux_carry_p_pre'))
        mux_carry_p_pre.switch_inputs[0].logical_source = lut_inst.pins['o6'][0]
        mux_carry_p_pre.switch_inputs[1].logical_source = lut_inst.pins['o5'][0]
        #   main mux
        mux_carry_p = mode._add_instance(SwitchInstance(mode, mux2, 'mux_carry_p'))
        mux_carry_p.switch_inputs[0].logical_source = mode.ports['ib'][0]
        mux_carry_p.switch_inputs[1].logical_source = mux_carry_p_pre.switch_output
        carry_inst.pins['p'][0].logical_source = mux_carry_p.switch_output
        # mux for the input 'g' of the carry chain
        mux_carry_g = mode._add_instance(SwitchInstance(mode, mux2, 'mux_carry_g'))
        mux_carry_g.switch_inputs[0].logical_source = mode.ports['ib'][1]
        mux_carry_g.switch_inputs[1].logical_source = lut_inst.pins['o5'][1]
        carry_inst.pins['g'][0].logical_source = mux_carry_g.switch_output
        # mux for the input 'cin' of the carry chain
        mux_carry_cin = mode._add_instance(SwitchInstance(mode, mux2, 'mux_carry_cin'))
        mux_carry_cin.switch_inputs[0].logical_source = mode.ports['ib'][0]
        mux_carry_cin.switch_inputs[1].logical_source = lut_inst.pins['o5'][1]
        carry_inst.pins['cin_fabric'][0].logical_source = mux_carry_cin.switch_output
        # mux for output port 'oa'
        #   pre-select: this is a logical-only switch that does not need configuration
        mux_oa_pre = mode._add_instance(SwitchInstance(mode, mux2, 'mux_oa_pre'))
        mux_oa_pre.switch_inputs[0].logical_source = lut_inst.pins['o6'][0]
        mux_oa_pre.switch_inputs[1].logical_source = lut_inst.pins['o5'][0]
        #   main mux
        mux_oa = mode._add_instance(SwitchInstance(mode, mux2, 'mux_oa'))
        mux_oa.switch_inputs[0].logical_source = mux_oa_pre.switch_output
        mux_oa.switch_inputs[1].logical_source = carry_inst.pins['s'][0]
        mode.ports['oa'][0].logical_source = mux_oa.switch_output
        # mux for output port 'ob'
        mux_ob = mode._add_instance(SwitchInstance(mode, mux4, 'mux_ob'))
        mux_ob.switch_inputs[0].logical_source = carry_inst.pins['cout_fabric'][0]
        mux_ob.switch_inputs[1].logical_source = carry_inst.pins['s'][0]
        mux_ob.switch_inputs[2].logical_source = ffb_inst.pins['q'][0]
        mux_ob.switch_inputs[3].logical_source = lut_inst.pins['o5'][1]
        mode.ports['ob'][0].logical_source = mux_ob.switch_output

    def __get_multimodedff(self, lib):
        try:
            multimodedff = lib.get_or_create_primitive('multimodedff', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            multimodedff = lib.create_custom_primitive('multimodedff')
            multimodedff.parameters['ENABLE_CE'] = {'init': "1'b0", 'config_bitmap': 0, 'config_bitcount': 1}
            multimodedff.parameters['ENABLE_SR'] = {'init': "1'b0", 'config_bitmap': 1, 'config_bitcount': 1}
            multimodedff.parameters['SR_SET'] = {'init': "1'b0", 'config_bitmap': 2, 'config_bitcount': 1}
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
            carrychain.parameters['CIN_FABRIC'] = {'init': "1'b0", 'config_bitmap': 0, 'config_bitcount': 1}
            carrychain.create_input('p', 1)
            carrychain.create_input('g', 1)
            carrychain.create_input('cin', 1)
            carrychain.create_input('cin_fabric', 1)
            carrychain.create_output('s', 1, combinational_sources = ('p', 'g', 'cin', 'cin_fabric'))
            carrychain.create_output('cout', 1, combinational_sources = ('p', 'g', 'cin', 'cin_fabric'))
            carrychain.create_output('cout_fabric', 1, combinational_sources = ('p', 'g', 'cin', 'cin_fabric'))
        return carrychain

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return 'fraclut6sffc.tmpl.v'

    @property
    def config_bitcount(self):
        return 85
