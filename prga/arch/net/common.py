# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Enum

__all__ = ['NetType', 'ConstNetType', 'PortDirection', 'NetClass', 'RoutingNodeType']

# ----------------------------------------------------------------------------
# -- Net Type ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class NetType(Enum): 
    """Enum type for nets.

    In PRGA, only ports/pins are modeled. Wires are only created during RTL generation, and not modeled in our
    in-memory data structure.
    """
    # constant net types
    const = 0           #: constant net
    # netlist net types
    port = 1            #: ports of a module
    pin = 2             #: ports of an instantiated sub-module

# ----------------------------------------------------------------------------
# -- Constant Net Type -------------------------------------------------------
# ----------------------------------------------------------------------------
class ConstNetType(Enum):
    """Enum type for constant nets."""
    unconnected = 0     #: unconnected
    zero = 1            #: tied to constant logic 0
    one = 2             #: tied to constant logic 1

# ----------------------------------------------------------------------------
# -- Port Direction ----------------------------------------------------------
# ----------------------------------------------------------------------------
class PortDirection(Enum):
    """Enum type for port/pin directions."""
    input_ = 0  #: input direction
    output = 1  #: output direction

    @property
    def opposite(self):
        """The opposite of the this direction.

        Returns:
            `PortDirection`: the enum value of the opposite direction.
        """
        return self.case(PortDirection.output, PortDirection.input_)

# ----------------------------------------------------------------------------
# -- Net Class ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class NetClass(Enum):
    """Class for nets."""
    # physical-only
    io = 0                  #: IOB/array external ports
    global_ = 1             #: global wires
    # logical (and maybe physical as well)
    switch = 2              #: switch nets
    config = 3              #: configuration nets
    # logical & user (and maybe physical as well)
    blockport = 4           #: IPIN/OPIN of logic/io block
    node = 5                #: other routing nodes. Some of them may be in the user domain as well
    cluster = 6             #: input/output of an intermediate level inside blocks but above primitives
    primitive = 7           #: input/output of a single-mode primitive
    multimode = 8           #: input/output of a multi-mode primitive
    # logical-only (may be user as well)
    mode = 9                #: input/output of a multi-mode primitive mapped into one of its logical modes

# ----------------------------------------------------------------------------
# -- Routing Node Type -------------------------------------------------------
# ----------------------------------------------------------------------------
class RoutingNodeType(Enum):
    """Routing node type."""
    segment_driver = 0      #: SegmentID
    segment_bridge = 1      #: SegmentBridgeID
    blockport_bridge = 2    #: BlockportBridgeID
