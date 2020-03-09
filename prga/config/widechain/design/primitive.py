# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import AbstractLeafModule, BaseModule
from prga.exception import PRGAInternalError
from prga.util import Enum

import os
from collections import OrderedDict

__all__ = ['CONFIG_WIDECHAIN_TEMPLATE_SEARCH_PATH', 'ConfigWidechain', 'ConfigWidechainCtrl']

CONFIG_WIDECHAIN_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- Configuration Module Class ----------------------------------------------
# ----------------------------------------------------------------------------
class ConfigWidechainModuleClass(Enum):
    """Widechain configuration circuitry-specific module class."""

    chain = 0       #: configuration data chain
    ctrl = 1        #: ctrl register and data shift-enable generator

# ----------------------------------------------------------------------------
# -- Configuration Widechain Module ------------------------------------------
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
    @property
    def widechain_class(self):
        """`ConfigWidechainModuleClass`: Module class specific to widechain configuration circuitry."""
        return ConfigWidechainModuleClass.chain

    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.config

    @property
    def verilog_template(self):
        return "cfg_widechain.tmpl.v"

# ----------------------------------------------------------------------------
# -- Configuration Widechain Ctrl Module -------------------------------------
# ----------------------------------------------------------------------------
class ConfigWidechainCtrl(BaseModule, AbstractLeafModule):
    """Configuration circuitry: Ctrl module.
    
    Args:
        config_width (:obj:`int`): Width of the config input port. One extra bit is added on the given value for
            ctrl/data selection
        depth (:obj:`int`): Depth of the internal FIFO. Default is 2
        name (:obj:`str`): Name of this module. Default to 'cfgctrl_x{config_width}_d{depth}'
    """

    __slots__ = ['_ports', '_depth', '_log2_depth']
    def __init__(self, config_width, depth = 2, name = None):
        name = name or "cfgctrl_x{}_d{}".format(config_width, depth)
        super(ConfigWidechainCtrl, self).__init__(name)
        self._ports = OrderedDict()
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1))

        self._add_port(ConfigOutputPort(self, 'cfg_full', 1))
        self._add_port(ConfigInputPort(self, 'cfg_i', config_width + 1))
        self._add_port(ConfigInputPort(self, 'cfg_wr', 1))

        self._add_port(ConfigInputPort(self, 'cfg_full_next', 1))
        self._add_port(ConfigOutputPort(self, 'cfg_o', config_width + 1))
        self._add_port(ConfigOutputPort(self, 'cfg_wr_next', 1))

        self._add_port(ConfigOutputPort(self, 'cfg_data_head', config_width))
        self._add_port(ConfigInputPort(self, 'cfg_data_tail', config_width))
        self._add_port(ConfigOutputPort(self, 'cfg_data_we', 1))

        self._depth = depth
        try:
            self._log2_depth = depth.bit_length()
        except AttributeError:
            self._log2_depth = len(bin(depth).lstrip('-0b'))

    # == low-level API =======================================================
    @property
    def depth(self):
        """:obj:`int`: Depth of the internal FIFO."""
        return self._depth

    @property
    def log2_depth(self):
        """obj:`int`: int(ceil(log(depth, 2)))"""
        return self._log2_depth

    @property
    def widechain_class(self):
        """`ConfigWidechainModuleClass`: Module class specific to widechain configuration circuitry."""
        return ConfigWidechainModuleClass.ctrl

    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.config

    @property
    def verilog_template(self):
        return "cfg_ctrl.tmpl.v"
