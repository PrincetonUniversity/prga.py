# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.flow.flow import AbstractPass
from prga.flow.delegate import (PrimitiveRequirement, PRGAPrimitiveNotFoundError, ConfigCircuitryDelegate,
        BuiltinPrimitiveLibrary)
from prga.flow.util import get_switch_path
from prga.config.widechain.design.primitive import CONFIG_WIDECHAIN_TEMPLATE_SEARCH_PATH, ConfigWidechain
from prga.config.widechain.algorithm.injection import ConfigWidechainLibraryDelegate, inject_config_chain
from prga.exception import PRGAInternalError
from prga.util import Object

__all__ = ['WidechainConfigCircuitryDelegate', 'InjectWidechainConfigCircuitry']

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Delegate for Widechain-based configuration ------
# ----------------------------------------------------------------------------
class WidechainConfigCircuitryDelegate(ConfigWidechainLibraryDelegate, ConfigCircuitryDelegate):

    __slots__ = ['_cfg_width', '_widechains', '_total_config_bits']
    def __init__(self, context, cfg_width = 1):
        super(WidechainConfigCircuitryDelegate, self).__init__(context)
        self._cfg_width = cfg_width
        self._widechains = {}
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
    def cfg_width(self):
        """:obj:`int`: Width of the config chain."""
        return self._cfg_width

    # -- implementing properties/methods required by superclass --------------
    def get_primitive_library(self, context):
        return BuiltinPrimitiveLibrary(context)

    def get_or_create_widechain(self, width):
        try:
            return self._widechains[width]
        except KeyError:
            module = ConfigWidechain(width, self._cfg_width)
            self._widechains[width] = self._context._modules[module.name] = module
            return module

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Injection Pass ----------------------------------
# ----------------------------------------------------------------------------
class InjectWidechainConfigCircuitry(Object, AbstractPass):
    """Inject widechain configuration circuitry."""

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
        inject_config_chain(context.config_circuitry_delegate, context.top)
        # context.config_circuitry_delegate._total_config_bits = get_config_bit_count(context, context.top)
        # clear out hierarchy cache
        del context._cache['util.hierarchy']
