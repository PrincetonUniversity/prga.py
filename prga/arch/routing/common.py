# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position, Orientation
from prga.arch.net.common import RoutingNodeType
from prga.arch.block.port import AbstractBlockPort
from prga.util import Abstract, Object, Enum, uno
from prga.exception import PRGAInternalError

from collections import namedtuple
from abc import abstractproperty
from copy import copy

__all__ = ['SegmentPrototype', 'SegmentBridgeType', 'SegmentID', 'BlockPortID']

# ----------------------------------------------------------------------------
# -- Segment Prototype -------------------------------------------------------
# ----------------------------------------------------------------------------
class SegmentPrototype(Object):
    """Defining a segment prototype.

    Args:
        name (:obj:`str`): Name of this segment
        width (:obj:`int`): Number of wire segments originated from one tile to one orientation
        length (:obj:`int`): Length of this segment
    """

    __slots__ = ['name', 'width', 'length']
    def __init__(self, name, width, length):
        self.name = name
        self.width = width
        self.length = length

# ----------------------------------------------------------------------------
# -- Segment Bridge Type -----------------------------------------------------
# ----------------------------------------------------------------------------
class SegmentBridgeType(Enum):
    """Segment bridge type."""
    # bridges used in switch boxes
    sboxin_regular = 0      #: Segment driven by another switch box
    sboxin_cboxout = 1      #: Output of a connection box
    sboxin_cboxout2 = 2     #: In case two connection boxes are used per routing channel
    # bridges used in connection boxes
    cboxin = 3              #: Connection box input. Segment driven by a switch box
    cboxout = 4             #: Connection box output. Routed into a switch box then switched to drive a segment
    # bridges used in tile/array
    array_regular = 5       #: Connected all the way to a segment driver in a switch box
    array_cboxout = 6       #: Connection box output
    array_cboxout2 = 7      #: Connection box output

# ----------------------------------------------------------------------------
# -- Abstract Routing Node ID ------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractRoutingNodeID(Hashable, Abstract):
    """Abstract base class for routing node IDs."""

    # == low-level API =======================================================
    def move(self, position, inplace = False):
        """`AbstractRoutingNodeID`: Move this routing node ID by ``position``."""
        id_ = self if inplace else copy(self)
        id_.position += position
        return id_

    # -- properties/methods to be overriden by subclasses --------------------
    @abstractproperty
    def position(self):
        """`Position`: Anchor position of this node ID."""
        raise NotImplementedError

    @abstractproperty
    def prototype(self):
        """`AbstractBlockPort` or `SegmentPrototype`: Prototype of this routing node ID."""
        raise NotImplementedError

    @abstractproperty
    def node_type(self):
        """`RoutingNodeType`: Type of this node ID."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Segment ID --------------------------------------------------------------
# ----------------------------------------------------------------------------
class SegmentID(Object, AbstractRoutingNodeID):
    """ID of segments.

    Args:
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): anchor position
        prototype (`SegmentPrototype`):
        orientation (`Orientation`): orientation
        section (:obj:`int`): section of the segment if longer than 1

    Supports the following operators:
        ``+``(`SegmentID` + :obj:`int`): get a new `SegmentID` object referring to the same segment but from an anchor
            position further from the origin
        ``+=``(`SegmentID` += :obj:`int`): modify the `SegmentID` object in place
        ``-``(`SegmentID` - :obj:`int`): get a new `SegmentID` object referring to the same segment but from an anchor
            position closer to the origin
        ``-=``(`SegmentID` -= :obj:`int`): modify the `SegmentID` object in place

    These operators don't validate the argument passed in. Validate before adding/subtracting.

    Tips: get the origin with ``origin = segment_id - segment_id.section`` (not in-place) or ``segment_id -=
    segment_id.section`` (in-place)
    """

    __slots__ = ['position', 'prototype', 'orientation', 'section']
    def __init__(self, position, prototype, orientation, section = 0):
        self.position = Position(*position)
        self.prototype = prototype
        self.orientation = orientation
        self.section = section

    def __hash__(self):
        return hash( (self.position.x, self.position.y, self.prototype.name, self.orientation, self.section) )

    def __str__(self):
        return 'SegmentID(({}, {}), {}, {}, {})'.format(
                self.position.x, self.position.y, self.prototype.name, self.orientation.name, self.section)

    def __add__(self, n):
        return type(self)(self.position + self.orientation.case( (0, n), (n, 0), (0, -n), (-n, 0)),
                self.prototype, self.orientation, self.section + n)

    def __iadd__(self, n):
        self.position += self.orientation.case( (0, n), (n, 0), (0, -n), (-n, 0) )
        self.section += n
        return self

    def __sub__(self, n):
        return type(self)(self.position - self.orientation.case( (0, n), (n, 0), (0, -n), (-n, 0)),
                self.prototype, self.orientation, self.section - n)

    def __isub__(self, n):
        self.position -= self.orientation.case( (0, n), (n, 0), (0, -n), (-n, 0) )
        self.section -= n
        return self

    def __eq__(self, other):
        return (other.node_type.is_segment_driver and
                self.position == other.position and
                self.prototype is other.prototype and
                self.orientation is other.orientation and
                self.section == other.section)

    def __ne__(self, other):
        return not self.__eq__(other)

    def to_driver_id(self, position = None, section = None):
        """`SegmentID`: Convert to segment driver ID."""
        return SegmentID(
                uno(position, self.position),
                self.prototype,
                self.orientation,
                uno(section, self.section))

    def to_bridge_id(self, position = None, section = None, bridge_type = None):
        """`SegmentBridgeID`: Convert to another segment bridge ID."""
        if self.node_type.is_segment_driver and bridge_type is None:
            raise PRGAInternalError("'bridge_type' required when converting segment driver to segment bridge ID")
        return SegmentBridgeID(
                uno(position, self.position),
                self.prototype,
                self.orientation,
                uno(section, self.section),
                uno(bridge_type, getattr(self, "bridge_type", None)))

    @property
    def node_type(self):
        return RoutingNodeType.segment_driver

# ----------------------------------------------------------------------------
# -- Segment Bridge ID -------------------------------------------------------
# ----------------------------------------------------------------------------
class SegmentBridgeID(SegmentID):
    """ID of segment bridges.

    Args:
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): anchor position
        prototype (`SegmentPrototype`):
        orientation (`Orientation`): orientation
        section (:obj:`int`): section of the segment if longer than 1
        bridge_type (`SegmentBridgeType`): type of this segment bridge
    """

    __slots__ = ['bridge_type']
    def __init__(self, position, prototype, orientation, section, bridge_type):
        super(SegmentBridgeID, self).__init__(position, prototype, orientation, section)
        self.bridge_type = bridge_type

    def __hash__(self):
        return hash( (self.position.x, self.position.y, self.prototype.name, self.orientation, self.section,
            self.bridge_type) )

    def __str__(self):
        return 'SegmentBridgeID({}, ({}, {}), {}, {}, {})'.format(
                self.bridge_type.name, self.position.x, self.position.y, self.prototype.name, self.orientation.name,
                self.section)

    def __add__(self, n):
        return type(self)(self.position + self.orientation.case( (0, n), (n, 0), (0, -n), (-n, 0)),
                self.prototype, self.orientation, self.section + n, self.bridge_type)

    def __sub__(self, n):
        return type(self)(self.position - self.orientation.case( (0, n), (n, 0), (0, -n), (-n, 0)),
                self.prototype, self.orientation, self.section - n, self.bridge_type)

    def __eq__(self, other):
        return (other.node_type.is_segment_bridge and
                self.position == other.position and
                self.prototype is other.prototype and
                self.orientation is other.orientation and
                self.section == other.section and
                self.bridge_type is other.bridge_type)

    @property
    def node_type(self):
        return RoutingNodeType.segment_bridge

# ----------------------------------------------------------------------------
# -- Block Port ID -----------------------------------------------------------
# ----------------------------------------------------------------------------
class BlockPortID(Object, AbstractRoutingNodeID):
    """ID of block ports.

    Args:
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): anchor position
        prototype (`AbstractBlockPort`):
        subblock (:obj:`int`): sub-block in a tile
    """

    __slots__ = ['position', 'prototype', 'subblock']
    def __init__(self, position, prototype, subblock = 0):
        self.position = Position(*position)
        self.prototype = prototype
        self.subblock = subblock

    def __hash__(self):
        return hash( (self.position.x, self.position.y, self.prototype.parent.name, self.prototype.name,
            self.subblock) )

    def __str__(self):
        return 'BlockPortID(({}, {}, {}), {}.{})'.format(
                self.position.x, self.position.y, self.subblock,
                self.prototype.parent.name, self.prototype.name)

    def __eq__(self, other):
        return (other.node_type.is_blockport_bridge and
                self.position == other.position and
                self.prototype is other.prototype and
                self.subblock == other.subblock)

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def node_type(self):
        return RoutingNodeType.blockport_bridge
