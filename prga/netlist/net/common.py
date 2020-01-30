# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Enum, Abstract

from abc import abstractproperty

__all__ = ['NetType', 'BusType', 'PortDirection']

# ----------------------------------------------------------------------------
# -- Bus Type ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class BusType(Enum):
    """Enum type for buses."""
    nonref = 0          #: bus (not a reference)

    # references
    slice_ = 1          #: a consecutive subset (slice) of a multi-bit bus
    concat = 2          #: a concatenation of buses and/or subsets

# ----------------------------------------------------------------------------
# -- Net Type ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class NetType(Enum): 
    """Enum type for nets."""
    # constant net types
    unconnected = 0     #: unconnected
    const = 1           #: constant value

    # netlist net types
    logic = 2           #: non-interface net
    port = 3            #: port in a module
    pin = 4             #: pin in an instance

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
# -- Abstract Generic Bus ----------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractGenericBus(Abstract, Sequence):
    """Abstract class for all buses."""

    @abstractproperty
    def bus_type(self):
        """`BusType`: Type of this bus."""
        raise NotImplementedError

    @abstractproperty
    def name(self):
        """:obj:`str`: String name of this net (to be used in Verilog/VPR)"""
        raise NotImplementedError

    @abstractproperty
    def is_source(self):
        """:obj:`bool`: Test if this net can be used as drivers of other nets."""
        raise NotImplementedError

    @abstractproperty
    def is_sink(self):
        """:obj:`bool`: Test if this net can be driven by other nets."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Generic Net ----------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractGenericNet(AbstractGenericBus):
    """Abstract class for all nets."""

    @abstractproperty
    def net_type(self):
        """`NetType`: Type of this net."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Port/Pin/Logic Net ---------------------------------------------
# ----------------------------------------------------------------------------
class AbstractNet(AbstractGenericNet):
    """Abstract class for all port/pin/logic nets."""

    @abstractproperty
    def parent(self):
        """`AbstractNetlistObject`: Parent module/instance of this net."""
        raise NotImplementedError

    @abstractproperty
    def key(self):
        """:obj:`Hashable`: A hashable key used to index this net in the parent module/instance."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Port/Pin Net ---------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractInterfaceNet(AbstractNet):
    """Abstract class for all port/pin nets."""

    @abstractproperty
    def direction(self):
        """`PortDirection`: Direction of this port/pin."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_source(self):
        return self.net_type.case(port = self.direction.is_input,
                pin = self.direction.is_output)

    @property
    def is_sink(self):
        return self.net_type.case(port = self.direction.is_output,
                pin = self.direction.is_input)
