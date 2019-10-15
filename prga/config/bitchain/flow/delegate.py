# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.flow.delegate import ConfigCircuitryDelegate
from prga.config.bitchain.design.primitive import CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH, ConfigBitchain
from prga.config.bitchain.algorithm.injection import ConfigBitchainLibraryDelegate, inject_config_chain

__all__ = ['BitchainConfigCircuitryDelegate']

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Delegate for Bitchain-based configuration -------
# ----------------------------------------------------------------------------
class BitchainConfigCircuitryDelegate(ConfigBitchainLibraryDelegate, ConfigCircuitryDelegate):

    __slots__ = ['_bitchains']
    def __init__(self, context):
        super(BitchainConfigCircuitryDelegate, self).__init__(context)
        self._bitchains = {}

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def additional_template_search_paths(self):
        return (CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH, )

    def get_or_create_bitchain(self, width):
        try:
            return self._bitchains[width]
        except KeyError:
            module = ConfigBitchain(width)
            self._bitchains[width] = self._context._modules[module.name] = module
            return module
