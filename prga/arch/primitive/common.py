# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Enum

__all__ = ['PrimitiveClass', 'PrimitivePortClass']

# ----------------------------------------------------------------------------
# -- Primitive Class ---------------------------------------------------------
# ----------------------------------------------------------------------------
class PrimitiveClass(Enum):
    """Enum types for VPR's 'class' attribute of leaf 'pb_type's.

    These 'class'es are only used for VPR inputs generation.
    """
    # built-in primitives
    lut         = 0     #: look-up table
    flipflop    = 1     #: D-flipflop
    inpad       = 2     #: input pad
    outpad      = 3     #: output pad 
    iopad       = 4     #: half-duplex input/output pad
    # user-defined primitives
    memory      = 5     #: user-defined memory
    custom      = 6     #: user-defined primitives
    multimode   = 7     #: user-defined multi-mode primitives

# ----------------------------------------------------------------------------
# -- Primitive Port Class ----------------------------------------------------
# ----------------------------------------------------------------------------
class PrimitivePortClass(Enum):
    """Enum types for VPR's 'port_class' attribute of ports.

    These 'port_class'es are only used for VPR inputs generation.
    """
    clock       = 0     #: clock for flipflop and memory
    lut_in      = 1     #: lut input
    lut_out     = 2     #: lut output
    D           = 3     #: flipflop data input
    Q           = 4     #: flipflop data output
    address     = 5     #: address input for single-port memory
    write_en    = 6     #: write enable for single-port memory
    data_in     = 7     #: data input for single-port memory
    data_out    = 8     #: data output for single-port memory
    address1    = 9     #: 1st address input for dual-port memory
    write_en1   = 10    #: 1st write enable for single-port memory
    data_in1    = 11    #: 2st data input for dual-port memory
    data_out1   = 12    #: 1st data output for dual-port memory
    address2    = 13    #: 2nd address input for dual-port memory
    write_en2   = 14    #: 2nd write enable for single-port memory
    data_in2    = 15    #: 2nd data input for dual-port memory
    data_out2   = 16    #: 2nd data output for dual-port memory
