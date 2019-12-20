# -*- encoding: ascii -*-
"""API for configuration circuitry."""

# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

# Bit-chain
from prga.config.bitchain.flow import BitchainConfigCircuitryDelegate, InjectBitchainConfigCircuitry

# Wide multi-bit chain
from prga.config.widechain.algorithm.injection import ConfigWidechainInjectionGuide
from prga.config.widechain.flow import WidechainConfigCircuitryDelegate, InjectWidechainConfigCircuitry

__all__ = [
        'BitchainConfigCircuitryDelegate', 'InjectBitchainConfigCircuitry',
        'WidechainConfigCircuitryDelegate', 'InjectWidechainConfigCircuitry', 'ConfigWidechainInjectionGuide',
        ]
