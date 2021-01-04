# -*- encoding: ascii -*-

from ..util import Enum

__all__ = ["InterfaceClass"]

# ----------------------------------------------------------------------------
# -- Interface Classes -------------------------------------------------------
# ----------------------------------------------------------------------------
class InterfaceClass(Enum):
    """Interface classes."""

    syscon = 0          #: common system control signals (clk and rst_n)

    reg_simple = 1      #: simple register interface
    ccm_simple = 2      #: simple cache-coherent memory interface

    ccm_axi4 = 3        #: AXI4 interface for coherent memory access
                        #:  - Do not support:
                        #:      * AWPROT, AWQOS, AWREGION: all tied to constant zero
                        #:      * ARPROT, ARQOS, ARREGION: all tied to constant zero
                        #:  - Support AWID, ARID, BID, RID (PITON threads)
                        #:  - Non-standard use of AWLOCK and ARLOCK (refer to ACE5):
                        #:      * ARLOCK is treated as a "load-reserved" (LR) access
                        #:      * AWLOCK is treated as a "store-conditional" (SC) access
                        #:  - Non-standard use of AWCACHE and ARCACHE:
                        #:      * 0b1111:       coherent (cacheable) read/write
                        #:      * other value:  non-coherent (non-cacheable) read/write
                        #:  - Additional use of AWUSER, ARUSER:
                        #:      * ECC bit(s)
