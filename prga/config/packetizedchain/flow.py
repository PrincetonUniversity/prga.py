# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Corner
from prga.flow.flow import AbstractPass
from prga.flow.delegate import (PrimitiveRequirement, PRGAPrimitiveNotFoundError, ConfigCircuitryDelegate,
        BuiltinPrimitiveLibrary)
from prga.flow.util import analyze_hierarchy, get_switch_path
from prga.config.packetizedchain.design.primitive import (CONFIG_PACKETIZED_CHAIN_TEMPLATE_SEARCH_PATH,
        ConfigWidechain, ConfigPacketizedChainCtrl)
from prga.config.packetizedchain.algorithm.stats import ConfigPacketizedChainStatsAlgorithms
from prga.config.packetizedchain.algorithm.injection import (ConfigPacketizedChainLibraryDelegate,
        ConfigPacketizedChainInjectionAlgorithms)
from prga.exception import PRGAInternalError
from prga.util import Object

__all__ = ['PacketizedChainConfigCircuitryDelegate', 'InjectPacketizedChainConfigCircuitry']

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Delegate for Packetized-chain-based configuration
# ----------------------------------------------------------------------------
class PacketizedChainConfigCircuitryDelegate(ConfigPacketizedChainLibraryDelegate, ConfigCircuitryDelegate):

    __slots__ = ['_config_width', '_chains', '_ctrl', '_total_config_bits']
    def __init__(self, context, config_width = 1):
        super(PacketizedChainConfigCircuitryDelegate, self).__init__(context)
        self._config_width = config_width
        self._chains = {}
        self._ctrl = None
        context._additional_template_search_paths += (CONFIG_PACKETIZED_CHAIN_TEMPLATE_SEARCH_PATH, )

    # == low-level API =======================================================
    @property
    def total_config_bits(self):
        """:obj:`int`: Total number of configuration bits."""
        try:
            return self._total_config_bits
        except AttributeError:
            raise PRGAInternalError("Total number of configuration bits not set yet.""")

    @property
    def config_width(self):
        """:obj:`int`: Width of the config chain."""
        return self._config_width

    # -- implementing properties/methods required by superclass --------------
    def get_primitive_library(self, context):
        return BuiltinPrimitiveLibrary(context)

    def get_or_create_chain(self, width):
        try:
            return self._chains[width]
        except KeyError:
            module = ConfigWidechain(width, self._config_width)
            self._chains[width] = self._context._modules[module.name] = module
            return module

    def get_or_create_ctrl(self):
        if self._ctrl is None:
            self._ctrl = ConfigPacketizedChainCtrl(self._config_width)
        return self._ctrl

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Injection Pass ----------------------------------
# ----------------------------------------------------------------------------
class InjectPacketizedChainConfigCircuitry(Object, AbstractPass):
    """Inject packetized configuration circuitry.

    Args:
        func_ctrl_injection (:obj:`Function` \(`AbstractModule` \) -> :obj:`bool` ): Lambda function testing if chain
            controller/router should be injected in a module. By default 1 single router is injected, which in most
            cases is not the desired behavior
        corner (`Corner`): The corner of the top-level array from where the configuration chain runs in
    """

    __slots__ = ['_func', '_corner', '_processed']
    def __init__(self, func_ctrl_injection = lambda m: m.module_class.is_array,
            corner = Corner.southwest):
        super(InjectPacketizedChainConfigCircuitry, self).__init__()
        self._func = func_ctrl_injection
        self._corner = corner
        self._processed = set()

    @property
    def key(self):
        return 'config.injection'

    @property
    def passes_before_self(self):
        return ("completion", )

    @property
    def passes_after_self(self):
        return ("physical", "rtl", "syn", "vpr", "asicflow")

    def __process_module(self, context, module):
        self._processed.add(module.name)
        hierarchy = analyze_hierarchy(context)
        if self._func(module):
            for submod_name, submod in iteritems(hierarchy[module.name]):
                if submod_name not in self._processed:
                    self._processed.add(submod_name)
                    ConfigPacketizedChainInjectionAlgorithms.inject_config_chain(context.config_circuitry_delegate,
                            submod)
            ConfigPacketizedChainInjectionAlgorithms.inject_config_ctrl(context, context.config_circuitry_delegate,
                    module, self._corner)
        else:
            for submod_name, submod in iteritems(hierarchy[module.name]):
                if submod_name not in self._processed:
                    self.__process_module(context, submod)
            ConfigPacketizedChainInjectionAlgorithms.connect_config_chain(context.config_circuitry_delegate,
                    module, self._corner)

    def run(self, context):
        self.__process_module(context, context.top)
        context.config_circuitry_delegate._total_config_bits = \
                ConfigPacketizedChainStatsAlgorithms.get_config_bitcount(context, context.top)
        del context._cache['util.hierarchy']
