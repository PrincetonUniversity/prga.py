# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..util import Enum

__all__ = ["InterfaceClass"]

# ----------------------------------------------------------------------------
# -- Interface Classes -------------------------------------------------------
# ----------------------------------------------------------------------------
class InterfaceClass(Enum):
    """Interface classes."""

    syscon = 0          #: common system control signals (clk and rst_n)
    ccm = 1             #: cache-coherent memory interface
    ureg = 2            #: register-based interface
    axi4lite = 3        #: AXI4Lite interface
