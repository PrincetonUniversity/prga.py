# -*- encoding: ascii -*-

from ..util import Enum

__all__ = ["InterfaceClass"]

# ----------------------------------------------------------------------------
# -- Interface Classes -------------------------------------------------------
# ----------------------------------------------------------------------------
class InterfaceClass(Enum):
    """Interface classes."""

    syscon = 0          #: common system control signals (clk and rst_n)
    ccm = 1             #: cache-coherent memory interface
    reg = 2             #: register-based interface
    # axi4lite = 3        #: AXI4Lite interface
