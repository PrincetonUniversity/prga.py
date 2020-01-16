# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import AbstractLeafModule, BaseModule
from prga.exception import PRGAInternalError

import os
from collections import OrderedDict

__all__ = ['CONFIG_PACKETIZED_CHAIN_TEMPLATE_SEARCH_PATH', 'ConfigWidechain', 'ConfigPacketizedChainCtrl']

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
