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
        'ConfigBitchain', 'FracturableLUT6', 'FracturableLUT6FF', 'MultifuncFlipflop', 'MultimodeAdder',
        'FracturableLUT6WithSFFAdder']

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

# ----------------------------------------------------------------------------
# -- Multi-functional Flip-flop ----------------------------------------------
# ----------------------------------------------------------------------------
class MultifuncFlipflop(BitchainMultimode):
    """Multi-functional flipflop.
    
    Args:
        context (`ArchitectureContext`): Architecture context in which this primitive will be added to
    """

    def __init__(self, context):
        super(MultifuncFlipflop, self).__init__('multifuncflipflop')
        self._add_port(MultimodeClockPort(self, 'clk'))
        self._add_port(MultimodeInputPort(self, 'd', 1, clock = 'clk'))
        self._add_port(MultimodeInputPort(self, 'sr', 1, clock = 'clk'))
        self._add_port(MultimodeInputPort(self, 'en', 1, clock = 'clk'))
        self._add_port(MultimodeOutputPort(self, 'q', 1, clock = 'clk'))

        # create modes
        lib = context.primitive_library
        self.__create_mode_ffce(lib)
        self.__create_mode_ffse(lib)
        self.__create_mode_ffc(lib)
        self.__create_mode_ffs(lib)
        self.__create_mode_ffe(lib)

    def __create_mode_ffce(self, lib):
        # flip-flop with synchronous clear and enable
        try:
            ffce = lib.get_or_create_primitive('ffce', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            ffce = lib.create_custom_primitive('ffce')
            ffce.create_clock('clk')
            ffce.create_input('d', 1, clock = 'clk')
            ffce.create_input('clear', 1, clock = 'clk')
            ffce.create_input('en', 1, clock = 'clk')
            ffce.create_output('q', 1, clock = 'clk')

        # add mode
        mode_ffce = self._add_mode(BitchainMode('ffce', self, mode_enabling_bits = (0, 1)))
        ffce_inst = mode_ffce.instantiate(ffce, 'ffce_inst')
        mode_ffce.connect(mode_ffce.ports['clk'], ffce_inst.pins['clk'])
        mode_ffce.connect(mode_ffce.ports['d'], ffce_inst.pins['d'])
        mode_ffce.connect(mode_ffce.ports['en'], ffce_inst.pins['en'])
        mode_ffce.connect(mode_ffce.ports['sr'], ffce_inst.pins['clear'])
        mode_ffce.connect(ffce_inst.pins['q'], mode_ffce.ports['q'])

    def __create_mode_ffse(self, lib):
        # flip-flop with synchronous set and enable
        try:
            ffse = lib.get_or_create_primitive('ffse', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            ffse = lib.create_custom_primitive('ffse')
            ffse.create_clock('clk')
            ffse.create_input('d', 1, clock = 'clk')
            ffse.create_input('set', 1, clock = 'clk')
            ffse.create_input('en', 1, clock = 'clk')
            ffse.create_output('q', 1, clock = 'clk')

        # add mode
        mode_ffse = self._add_mode(BitchainMode('ffse', self, mode_enabling_bits = (0, 1, 2)))
        ffse_inst = mode_ffse.instantiate(ffse, 'ffse_inst')
        mode_ffse.connect(mode_ffse.ports['clk'], ffse_inst.pins['clk'])
        mode_ffse.connect(mode_ffse.ports['d'], ffse_inst.pins['d'])
        mode_ffse.connect(mode_ffse.ports['en'], ffse_inst.pins['en'])
        mode_ffse.connect(mode_ffse.ports['sr'], ffse_inst.pins['set'])
        mode_ffse.connect(ffse_inst.pins['q'], mode_ffse.ports['q'])

    def __create_mode_ffc(self, lib):
        # flip-flop with synchronous clear
        try:
            ffc = lib.get_or_create_primitive('ffc', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            ffc = lib.create_custom_primitive('ffc')
            ffc.create_clock('clk')
            ffc.create_input('d', 1, clock = 'clk')
            ffc.create_input('clear', 1, clock = 'clk')
            ffc.create_output('q', 1, clock = 'clk')

        # add mode
        mode_ffc = self._add_mode(BitchainMode('ffc', self, mode_enabling_bits = (1, )))
        ffc_inst = mode_ffc.instantiate(ffc, 'ffc_inst')
        mode_ffc.connect(mode_ffc.ports['clk'], ffc_inst.pins['clk'])
        mode_ffc.connect(mode_ffc.ports['d'], ffc_inst.pins['d'])
        mode_ffc.connect(mode_ffc.ports['sr'], ffc_inst.pins['clear'])
        mode_ffc.connect(ffc_inst.pins['q'], mode_ffc.ports['q'])

    def __create_mode_ffs(self, lib):
        # flip-flop with synchronous set
        try:
            ffs = lib.get_or_create_primitive('ffs', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            ffs = lib.create_custom_primitive('ffs')
            ffs.create_clock('clk')
            ffs.create_input('d', 1, clock = 'clk')
            ffs.create_input('set', 1, clock = 'clk')
            ffs.create_output('q', 1, clock = 'clk')

        # add mode
        mode_ffs = self._add_mode(BitchainMode('ffs', self, mode_enabling_bits = (1, 2)))
        ffs_inst = mode_ffs.instantiate(ffs, 'ffs_inst')
        mode_ffs.connect(mode_ffs.ports['clk'], ffs_inst.pins['clk'])
        mode_ffs.connect(mode_ffs.ports['d'], ffs_inst.pins['d'])
        mode_ffs.connect(mode_ffs.ports['sr'], ffs_inst.pins['set'])
        mode_ffs.connect(ffs_inst.pins['q'], mode_ffs.ports['q'])

    def __create_mode_ffe(self, lib):
        # flip-flop with clock enable
        try:
            ffe = lib.get_or_create_primitive('ffe', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            ffe = lib.create_custom_primitive('ffe')
            ffe.create_clock('clk')
            ffe.create_input('d', 1, clock = 'clk')
            ffe.create_input('en', 1, clock = 'clk')
            ffe.create_output('q', 1, clock = 'clk')

        # add mode
        mode_ffe = self._add_mode(BitchainMode('ffe', self, mode_enabling_bits = (0, )))
        ffe_inst = mode_ffe.instantiate(ffe, 'ffe_inst')
        mode_ffe.connect(mode_ffe.ports['clk'], ffe_inst.pins['clk'])
        mode_ffe.connect(mode_ffe.ports['d'], ffe_inst.pins['d'])
        mode_ffe.connect(mode_ffe.ports['en'], ffe_inst.pins['en'])
        mode_ffe.connect(ffe_inst.pins['q'], mode_ffe.ports['q'])

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def in_physical_domain(self):
        return False

    @property
    def config_bit_count(self):
        return 3

# ----------------------------------------------------------------------------
# -- Multi-mode Adder --------------------------------------------------------
# ----------------------------------------------------------------------------
class MultimodeAdder(BitchainMultimode):
    """An adder primitive with a configurable carry input.

    Args:
        context (`ArchitectureContext`): Architecture context in which this primitive will be added to
    """
    
    def __init__(self, context):
        super(MultimodeAdder, self).__init__('multimodeadder')
        self._add_port(MultimodeInputPort(self, 'a', 1))
        self._add_port(MultimodeInputPort(self, 'b', 1))
        self._add_port(MultimodeInputPort(self, 'cin', 1))
        self._add_port(MultimodeOutputPort(self, 's', 1))
        self._add_port(MultimodeOutputPort(self, 'cout', 1))

        # create modes
        lib = context.primitive_library
        self.__create_mode_adder(lib)
        self.__create_mode_adder_cin0(lib)
        self.__create_mode_adder_cin1(lib)

    def __create_mode_adder(self, lib):
        # full adder
        try:
            adder = lib.get_or_create_primitive('adder', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            adder = lib.create_custom_primitive('adder')
            adder.create_input('a', 1)
            adder.create_input('b', 1)
            adder.create_input('cin', 1)
            adder.create_output('s', 1, combinational_sources = ('a', 'b', 'cin'))
            adder.create_output('cout', 1, combinational_sources = ('a', 'b', 'cin'))

        # add mode
        mode = self._add_mode(BitchainMode('adder', self, mode_enabling_bits = (1, )))
        inst = mode.instantiate(adder, 'adder')
        mode.connect(mode.ports['a'], inst.pins['a'])
        mode.connect(mode.ports['b'], inst.pins['b'])
        mode.connect(mode.ports['cin'], inst.pins['cin'])
        mode.connect(inst.pins['s'], mode.ports['s'])
        mode.connect(inst.pins['cout'], mode.ports['cout'])

    def __create_mode_adder_cin0(self, lib):
        # adder with constant-zero carry-in
        try:
            adder = lib.get_or_create_primitive('adder_cin0', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            adder = lib.create_custom_primitive('adder_cin0')
            adder.create_input('a', 1)
            adder.create_input('b', 1)
            adder.create_output('s', 1, combinational_sources = ('a', 'b'))
            adder.create_output('cout', 1, combinational_sources = ('a', 'b'))

        # add mode
        mode = self._add_mode(BitchainMode('adder_cin0', self, mode_enabling_bits = tuple()))
        inst = mode.instantiate(adder, 'adder')
        mode.connect(mode.ports['a'], inst.pins['a'])
        mode.connect(mode.ports['b'], inst.pins['b'])
        mode.connect(inst.pins['s'], mode.ports['s'])
        mode.connect(inst.pins['cout'], mode.ports['cout'])

    def __create_mode_adder_cin1(self, lib):
        # adder with constant-one carry-in
        try:
            adder = lib.get_or_create_primitive('adder_cin1', PrimitiveRequirement.non_physical_preferred)
        except PRGAPrimitiveNotFoundError:
            adder = lib.create_custom_primitive('adder_cin1')
            adder.create_input('a', 1)
            adder.create_input('b', 1)
            adder.create_output('s', 1, combinational_sources = ('a', 'b'))
            adder.create_output('cout', 1, combinational_sources = ('a', 'b'))

        # add mode
        mode = self._add_mode(BitchainMode('adder_cin1', self, mode_enabling_bits = (0, )))
        inst = mode.instantiate(adder, 'adder')
        mode.connect(mode.ports['a'], inst.pins['a'])
        mode.connect(mode.ports['b'], inst.pins['b'])
        mode.connect(inst.pins['s'], mode.ports['s'])
        mode.connect(inst.pins['cout'], mode.ports['cout'])

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def in_physical_domain(self):
        return False

    @property
    def config_bit_count(self):
        return 2

# ----------------------------------------------------------------------------
# -- Fractuable LUT6 with Multi-functional Flip-Flops and Adder --------------
# ----------------------------------------------------------------------------
class FracturableLUT6WithSFFAdder(BitchainMultimode):
    """Fracturable LUT6 with multi-functional flip-flops and adder.

    Args:
        context (`ArchitectureContext`): Architecture context in which this primitive will be added to
        in_physical_domain (:obj:`bool`): If this module is in the physical domain
    """

    __slots__ = ['in_physical_domain']
    def __init__(self, context, in_physical_domain):
        lib = context.primitive_library
        lut5 = lib.get_or_create_primitive('lut5', PrimitiveRequirement.non_physical_preferred)
        lut6 = lib.get_or_create_primitive('lut6', PrimitiveRequirement.non_physical_preferred)
        ff = lib.get_or_create_primitive('flipflop', PrimitiveRequirement.non_physical_preferred)
        adder = lib.get_or_create_primitive('multimodeadder')
        multifuncflipflop = lib.get_or_create_primitive('multifuncflipflop')
        mux2 = context.switch_library.get_or_create_switch(2, None, False)
        mux4 = context.switch_library.get_or_create_switch(4, None, False)

        super(FracturableLUT6WithSFFAdder, self).__init__('fraclut6sffc')
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

        # mode 1: (LUT6 + DFF) + Multi-mode Adder + Multi-functional D-Flipflop
        self.__create_mode_lut6dff(lut6, ff, adder, multifuncflipflop, mux4)

        # mode 2: 2x(LUT5 + DFF) + Multi-mode Adder
        self.__create_mode_lut5dffx2(lut5, ff, adder, mux2, mux4)

    def __create_mode_lut6dff(self, lut6, ff, adder, multifuncflipflop, mux4):
        mode = self._add_mode(BitchainMode('lut6dff', self, {
            "lut6_inst": 3,     # LUT5A_DATA, LUT5B_DATA:                   66:3
            "adder_inst": 69,   # ADDER_SOURCE_CIN:                         70:69
            "mux_mfdff_d": 76,  # FFB_SOURCE:                               77:76
            "mfdff_inst": 78,   # FFB_ENABLE_CE, FFB_ENABLE_SR, FFB_SR_SET: 80:78
            "mux_ob": 81,       # OB_SEL:                                   82:81
            },
            (67, 72)            # LUT6_ENABLE, FFA_SOURCE = FFA_O6
            ))
        lut6_inst = mode.instantiate(lut6, 'lut6_inst')
        adder_inst = mode.instantiate(adder, 'adder_inst')
        ff_inst = mode.instantiate(ff, 'ff_inst')
        multiff_inst = mode.instantiate(multifuncflipflop, 'mfdff_inst')
        # LUT6 connections
        mode.connect(mode.ports['ia'], lut6_inst.pins['in'])
        mode.connect(lut6_inst.pins['out'], ff_inst.pins['D'], pack_pattern = True)
        mode.connect(lut6_inst.pins['out'], adder_inst.pins['a'])
        mode.connect(lut6_inst.pins['out'], mode.ports['oa'])
        # D-Flipflop connections
        mode.connect(mode.ports['clk'], ff_inst.pins['clk'])
        mode.connect(ff_inst.pins['Q'], mode.ports['q'])
        # adder connections
        mode.connect(mode.ports['ib'], adder_inst.pins['b'])
        mode.connect(mode.ports['cin'], adder_inst.pins['cin'])
        mode.connect(adder_inst.pins['cout'], mode.ports['cout'])
        mode.connect(adder_inst.pins['cout'], mode.ports['ob'])
        mode.connect(adder_inst.pins['cout'], multiff_inst.pins['d'])
        mode.connect(adder_inst.pins['s'], mode.ports['ob'])
        mode.connect(adder_inst.pins['s'], multiff_inst.pins['d'])
        # multi-functional flipflop connections
        mode.connect(mode.ports['clk'], multiff_inst.pins['clk'])
        mode.connect(mode.ports['ce'], multiff_inst.pins['en'])
        mode.connect(mode.ports['sr'], multiff_inst.pins['sr'])
        mode.connect(mode.ports['ib'], multiff_inst.pins['d'])
        mode.connect(multiff_inst.pins['q'], mode.ports['ob'])
        # now the user-invisible part
        # mux for the input of the multi-functional D-flipflop
        mux_mfdff = mode._add_instance(SwitchInstance(mode, mux4, 'mux_mfdff_d'))
        mux_mfdff.switch_inputs[0].logical_source = adder_inst.pins['cout'][0]
        mux_mfdff.switch_inputs[1].logical_source = adder_inst.pins['s'][0]
        mux_mfdff.switch_inputs[2].logical_source = mode.ports['ib'][0]
        multiff_inst.pins['d'][0].logical_source = mux_mfdff.switch_output
        # mux for the output 'ob'
        mux_ob = mode._add_instance(SwitchInstance(mode, mux4, 'mux_ob'))
        mux_ob.switch_inputs[0].logical_source = adder_inst.pins['cout'][0]
        mux_ob.switch_inputs[1].logical_source = adder_inst.pins['s'][0]
        mux_ob.switch_inputs[2].logical_source = multiff_inst.pins['q'][0]
        mode.ports['ob'][0].logical_source = mux_ob.switch_output

    def __create_mode_lut5dffx2(self, lut5, ff, adder, mux2, mux4):
        mode = self._add_mode(BitchainMode('lut5dffx2', self, {
            "lut5_inst_0":  3,  # LUT5A_DATA:                               34:3
            "lut5_inst_1":  35, # LUT5B_DATA:                               66:35
            "mux_adder_b":  68, # ADDER_SOURCE_B:                           68
            "adder_inst":   69, # ADDER_SOURCE_CIN:                         70:69
            "mux_ob":       81, # OB_SEL:                                   82:81
            },
            (72, 77, 78)        # FFA_SOURCE = FFA_O6, FFB_SOURCE = FFB_O5
            ))
        lut5_inst = [mode.instantiate(lut5, 'lut5_inst_' + str(i)) for i in range(2)]
        ff_inst = [mode.instantiate(ff, 'ff_inst_' + str(i)) for i in range(2)]
        adder_inst = mode.instantiate(adder, 'adder_inst')
        # LUT5+DFF
        for i in range(2):
            mode.connect(mode.ports['ia'][0:5], lut5_inst[i].pins['in'])
            mode.connect(lut5_inst[i].pins['out'], ff_inst[i].pins['D'], pack_pattern = True)
            mode.connect(mode.ports['clk'], ff_inst[i].pins['clk'])
        # adder
        mode.connect(lut5_inst[0].pins['out'], adder_inst.pins['a'])
        mode.connect(lut5_inst[1].pins['out'], adder_inst.pins['b'])
        mode.connect(mode.ports['ib'], adder_inst.pins['b'])
        mode.connect(mode.ports['cin'], adder_inst.pins['cin'])
        mode.connect(adder_inst.pins['cout'], mode.ports['cout'])
        # oa
        mode.connect(lut5_inst[0].pins['out'], mode.ports['oa'])
        # q
        mode.connect(ff_inst[0].pins['Q'], mode.ports['q'])
        # ob
        mode.connect(adder_inst.pins['cout'], mode.ports['ob'])
        mode.connect(adder_inst.pins['s'], mode.ports['ob'])
        mode.connect(ff_inst[1].pins['Q'], mode.ports['ob'])
        mode.connect(lut5_inst[1].pins['out'], mode.ports['ob'])
        # now the user-invisible part
        # mux for the input 'b' of the adder
        mux_adder = mode._add_instance(SwitchInstance(mode, mux2, 'mux_adder_b'))
        mux_adder.switch_inputs[0].logical_source = mode.ports['ib'][0]
        mux_adder.switch_inputs[1].logical_source = lut5_inst[1].pins['out'][0]
        adder_inst.pins['b'][0].logical_source = mux_adder.switch_output
        # mux for output port 'ob'
        mux_ob = mode._add_instance(SwitchInstance(mode, mux4, 'mux_ob'))
        mux_ob.switch_inputs[0].logical_source = adder_inst.pins['cout'][0]
        mux_ob.switch_inputs[1].logical_source = adder_inst.pins['s'][0]
        mux_ob.switch_inputs[2].logical_source = ff_inst[1].pins['Q'][0]
        mux_ob.switch_inputs[3].logical_source = lut5_inst[1].pins['out'][0]
        mode.ports['ob'][0].logical_source = mux_ob.switch_output

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return 'fraclut6sffc.tmpl.v'

    @property
    def config_bit_count(self):
        return 83
