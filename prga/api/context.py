# -*- encoding: ascii -*-

"""`ArchitectureContext` and related API."""

# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Orientation
from prga.arch.array.common import ChannelCoverage
from prga.algorithm.design.cbox import BlockPortFCValue, BlockFCValue
from prga.flow.context import ArchitectureContext

__all__ = [
        "Orientation",
        "ChannelCoverage",
        "BlockPortFCValue",
        "BlockFCValue",
        "ArchitectureContext",
        ]
