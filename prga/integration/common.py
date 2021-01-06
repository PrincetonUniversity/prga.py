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
                        #:      * AWPROT, AWQOS, AWREGION, AWLOCK:  all tied to constant zero
                        #:      * ARPROT, ARQOS, ARREGION:          all tied to constant zero
                        #:  - Support AWID, ARID, BID, RID (PITON threads)
                        #:  - Non-standard use of ARLOCK:
                        #:      * ARLOCK marks the load as an atomic operation. AMO type and data in ARUSER
                        #:  - Non-standard use of AWCACHE and ARCACHE:
                        #:      * |AxCache[3:2]:    coherent (cacheable) read/write
                        #:      * other value:      non-coherent (non-cacheable) read/write
                        #:      * Device, bufferability, write-through/write-back, and allocatioin strategy are not respected
                        #:  - Additional use of AWUSER:
                        #:      * ECC bit(s)
                        #:  - Additional use of ARUSER:
                        #:      * ECC bit(s)
                        #:      * AMO opcode
                        #:      * AMO data
