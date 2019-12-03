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

__all__ = ['CONFIG_WIDECHAIN_TEMPLATE_SEARCH_PATH', 'ConfigWidechain']

CONFIG_WIDECHAIN_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- Configuration Widechain Module ------------------------------------------
# ----------------------------------------------------------------------------
class ConfigWidechain(BaseModule, AbstractLeafModule):
    """Configuration circuitry: wide chain.

    Args:
        width (:obj:`int`): Number of config bits in this chain
        cfg_width (:obj:`int`): Width of the config input port
        name (:obj:`str`): Name of this module. Default to 'cfg_widechain_{width}_x{cfg_width}'
    """

    __slots__ = ['_ports']
    def __init__(self, width, cfg_width, name = None):
        name = name or "cfg_widechain_{}_x{}".format(width, cfg_width)
        super(ConfigWidechain, self).__init__(name)
        self._ports = OrderedDict()
        self._add_port(ConfigClockPort(self, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_e', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_we', 1, 'cfg_clk'))
        self._add_port(ConfigInputPort(self, 'cfg_i', cfg_width, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_o', cfg_width, 'cfg_clk'))
        self._add_port(ConfigOutputPort(self, 'cfg_d', width, 'cfg_clk'))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.config

    @property
    def verilog_template(self):
        return "cfg_widechain.tmpl.v"
