# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.flow.flow import AbstractPass
from prga.flow.delegate import (PrimitiveRequirement, PRGAPrimitiveNotFoundError, ConfigCircuitryDelegate,
        BuiltinPrimitiveLibrary)
from prga.flow.util import get_switch_path, iter_all_blocks, iter_all_cboxes, iter_all_sboxes
from prga.config.widechain.design.primitive import (CONFIG_WIDECHAIN_TEMPLATE_SEARCH_PATH,
        ConfigWidechain, ConfigWidechainCtrl)
from prga.config.widechain.algorithm.injection import ConfigWidechainLibraryDelegate, inject_widechain
from prga.config.widechain.algorithm.stats import get_config_widechain_bitcount
from prga.exception import PRGAInternalError
from prga.util import Abstract, Object

from abc import abstractmethod
from itertools import chain

__all__ = ['WidechainConfigCircuitryDelegate', 'InjectWidechainConfigCircuitry']

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Delegate for Widechain-based configuration ------
# ----------------------------------------------------------------------------
class WidechainConfigCircuitryDelegate(ConfigWidechainLibraryDelegate, ConfigCircuitryDelegate):

    __slots__ = ['_config_width', '_widechains', '_ctrls', '_total_config_bits']
    def __init__(self, context, config_width = 1):
        super(WidechainConfigCircuitryDelegate, self).__init__(context)
        self._config_width = config_width
        self._widechains = {}
        self._ctrls = {}
        context._additional_template_search_paths += (CONFIG_WIDECHAIN_TEMPLATE_SEARCH_PATH, )

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

    def get_or_create_widechain(self, width):
        try:
            return self._widechains[width]
        except KeyError:
            module = ConfigWidechain(width, self._config_width)
            self._widechains[width] = self._context._modules[module.name] = module
            return module

    def get_or_create_ctrl(self, depth = 2):
        try:
            return self._ctrls[depth]
        except KeyError:
            module = ConfigWidechainCtrl(self._config_width, depth)
            self._ctrls[depth] = self._context._modules[module.name] = module
            return module

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Injection Pass ----------------------------------
# ----------------------------------------------------------------------------
class InjectWidechainConfigCircuitry(Object, AbstractPass):
    """Inject widechain configuration circuitry.

    Args:
        guide (`ConfigWidechainInjectionGuide`): Helper class for the internal injection algorithm.
    """

    __slots__ = ['_guide']
    def __init__(self, guide = None):
        self._guide = guide

    @property
    def key(self):
        return "config.injection"

    @property
    def passes_before_self(self):
        return ("completion", )

    @property
    def passes_after_self(self):
        return ("physical", "rtl", "syn", "vpr", "asicflow")

    def run(self, context):
        inject_widechain(context, context.config_circuitry_delegate, context.top, self._guide)
        context.config_circuitry_delegate._total_config_bits = get_config_widechain_bitcount(context, context.top)
        # clear out hierarchy cache
        del context._cache['util.hierarchy']
