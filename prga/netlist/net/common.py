# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...util import Enum, Abstract

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
    port = 2            #: port in a module
    pin = 3             #: [hierarchical] pin

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

    @abstractproperty
    def node(self):
        """:obj:`Hashable`: A hashable value to index this net in the connection graph."""
        raise NotImplementedError

    @abstractproperty
    def parent(self):
        """`AbstractModule`: Parent module of this net."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def bus_type(self):
        return BusType.nonref

# ----------------------------------------------------------------------------
# -- Abstract Port -----------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractPort(AbstractGenericNet):
    """Abstract class for ports."""

    @abstractproperty
    def direction(self):
        """`PortDirection`: Direction of this port."""
        raise NotImplementedError

    @abstractproperty
    def key(self):
        """:obj:`Hashable`: A hashable key to index this port in its parent module's ports mapping."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.port

    @property
    def is_source(self):
        return self.direction.is_input

    @property
    def is_sink(self):
        return self.direction.is_output

# ----------------------------------------------------------------------------
# -- Abstract Pin ------------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractPin(AbstractGenericNet):
    """Abstract class for [hierarchical] pins."""

    @abstractproperty
    def model(self):
        """`AbstractPort`: Model port of this pin."""
        raise NotImplementedError

    @abstractproperty
    def hierarchy(self):
        """:obj:`Sequence` [`AbstractInstance`]: Hierarchy of instances down to the pin in ascending order.

        For example, assume 1\) module 'clb' has an instance 'alm0' of module 'alm', and 2\) module 'alm' has an
        instance 'lutA' of module 'LUT4', and 3\) module 'LUT4' has an input port 'in'. This net can be referred to by
        a pin, whose model is the port, and the hierarchy is [instance 'lutA', instance 'alm0']."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.pin

    @property
    def is_source(self):
        return len(self.hierarchy) == 1 and self.model.is_sink

    @property
    def is_sink(self):
        return len(self.hierarchy) == 1 and self.model.is_source

    @property
    def parent(self):
        return self.hierarchy[-1].parent
