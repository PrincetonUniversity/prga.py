# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..util import Abstract, Object, Enum, uno
from ..exception import PRGAInternalError

from collections import namedtuple
from abc import abstractproperty
from copy import copy

__all__ = ['Dimension', 'Direction', 'Orientation', 'Corner', 'Subtile', 'Position',
        'NetClass', 'ModuleClass', 'PrimitiveClass', 'PrimitivePortClass',
        'Global', 'Segment', 'SegmentType', 'SegmentID', 'BlockPinID']

# ----------------------------------------------------------------------------
# -- Dimension ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class Dimension(Enum):
    """Segment/connection block dimensions."""
    x = 0   #: X-dimension
    y = 1   #: Y-dimension

    @property
    def perpendicular(self):
        """`Dimension`: The perpendicular dimension of this dimension."""
        if self is Dimension.x:
            return Dimension.y
        elif self is Dimension.y:
            return Dimension.x
        else:
            raise PRGAInternalError("{} does not have a perpendicular Dimension".format(self))

# ----------------------------------------------------------------------------
# -- Direction ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class Direction(Enum):
    """Segment/relative directions."""
    inc = 0         #: increasing direction
    dec = 1         #: decreasing direction

    @property
    def opposite(self):
        """`Direction`: The opposite direction."""
        if self is Direction.inc:
            return Direction.dec
        elif self is Direction.dec:
            return Direction.inc
        else:
            raise PRGAInternalError("{} does not have an opposite Direction".format(self))

# ----------------------------------------------------------------------------
# -- Orientation -------------------------------------------------------------
# ----------------------------------------------------------------------------
class Orientation(Enum):
    """Orientation in a 2D grid."""
    north = 0       #: Direction.inc x Dimension.y
    east = 1        #: Direction.inc x Dimension.x
    south = 2       #: Direction.dec x Dimension.y
    west = 3        #: Direction.dec x Dimension.x
    auto = 4        #: automatically determine the orientation. Not valid in some cases

    @property
    def dimension(self):
        """:obj:`Dimension`: The dimension of this orientation."""
        if self in (Orientation.north, Orientation.south):
            return Dimension.y
        elif self in (Orientation.east, Orientation.west):
            return Dimension.x
        else:
            raise PRGAInternalError("{} does not have a corresponding dimension".format(self))

    @property
    def direction(self):
        """:obj:`Direction`: The direction of this orientation."""
        if self in (Orientation.north, Orientation.east):
            return Direction.inc
        elif self in (Orientation.south, Orientation.west):
            return Direction.dec
        else:
            raise PRGAInternalError("{} does not have a corresponding direction".format(self))

    @property
    def opposite(self):
        """`Orientation`: The opposite orientation of this orientation."""
        if self is Orientation.north:
            return Orientation.south
        elif self is Orientation.east:
            return Orientation.west
        elif self is Orientation.south:
            return Orientation.north
        elif self is Orientation.west:
            return Orientation.east
        elif self is Orientation.auto:
            return Orientation.auto
        else:
            raise PRGAInternalError("{} does not have an opposite Orientation".format(self))

    def decompose(self):
        """Decompose this orientation into dimension and direcion.

        Returns:
            `Dimension`:
            `Direction`:
        """
        return self.dimension, self.direction

    def to_subtile(self):
        """`Subtile`: Convert to sub-tile position."""
        try:
            return Subtile[self.name]
        except KeyError:
            raise PRGAInternalError("{} does not have corresponding sub-tile position".format(self))

    @classmethod
    def compose(cls, dimension, direction):
        """Compose a dimension and a direction to an orientation.

        Args:
            dimension (`Dimension`):
            direction (`Direction`):
        """
        return dimension.case(direction.case(Orientation.east, Orientation.west),
                direction.case(Orientation.north, Orientation.south))

# ----------------------------------------------------------------------------
# -- Corner ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Corner(Enum):
    """Corner in a 2D grid."""
    northeast = 0   #: Orientation.north x Orientation.east
    northwest = 1   #: Orientation.north x Orientation.west
    southeast = 2   #: Orientation.south x Orientation.east
    southwest = 3   #: Orientation.south x Orientation.west

    @classmethod
    def compose(cls, ori_a, ori_b):
        """Compose two orientations to make a corner.

        Args:
            ori_a (`Orientation`):
            ori_b (`Orientation`):

        Retusn:
            `Corner`:
        """
        if ori_a.dimension is ori_b.dimension:
            raise PRGAInternalError("Cannot compose '{}' and '{}'".format(ori_a, ori_b))
        return ori_a.case(
                ori_b.case(west = Corner.northwest, east = Corner.northeast),
                ori_b.case(north = Corner.northeast, south = Corner.southeast),
                ori_b.case(west = Corner.southwest, east = Corner.southwest),
                ori_b.case(north = Corner.northwest, south = Corner.southwest))

    @property
    def opposite(self):
        """`Corner`: The opposite corner of this corner."""
        return self.case(
                Corner.southwest,
                Corner.southeast,
                Corner.northwest,
                Corner.northeast)

    def decompose(self):
        """:obj:`tuple` (`Orientation`, `Orientation`): Decompose this corner into two `Orientation`s. Y-dimension
        first."""
        return self.case(
                (Orientation.north, Orientation.east),
                (Orientation.north, Orientation.west),
                (Orientation.south, Orientation.east),
                (Orientation.south, Orientation.west))

    def dotx(self, dim):
        """`Direction`: Direction in `Dimension` ``dim``."""
        return self.case(
                dim.case(Direction.inc, Direction.inc),
                dim.case(Direction.dec, Direction.inc),
                dim.case(Direction.inc, Direction.dec),
                dim.case(Direction.dec, Direction.dec))

    def to_subtile(self):
        """`Subtile`: Convert to sub-tile position."""
        try:
            return Subtile[self.name]
        except KeyError:
            raise PRGAInternalError("{} does not have corresponding sub-tile position".format(self))

# ----------------------------------------------------------------------------
# -- Subtile -----------------------------------------------------------------
# ----------------------------------------------------------------------------
class Subtile(Enum):
    """Sub-tile positions in a tile."""
    center = 0      #: center of the tile, typically occupied by a logic/io block

    # edges
    north = 1       #: north edge of the tile, typically occupied by a connection box
    east = 2        #: east edge of the tile, typically occupied by a connection box
    south = 3       #: south edge of the tile, typically occupied by a connection box
    west = 4        #: west edge of the tile, typically occupied by a connection box

    # corners
    northeast = 5   #: northeast corner of the tile, typically occupied by a switch box
    northwest = 6   #: northeast corner of the tile, typically occupied by a switch box
    southeast = 7   #: northeast corner of the tile, typically occupied by a switch box
    southwest = 8   #: northeast corner of the tile, typically occupied by a switch box

    def to_orientation(self):
        """`Orientation`: Convert to orientation."""
        try:
            return Orientation[self.name]
        except KeyError:
            raise PRGAInternalError("{} does not have corresponding orientation".format(self))

    def to_corner(self):
        """`Corner`: Convert to corner."""
        try:
            return Corner[self.name]
        except KeyError:
            raise PRGAInternalError("{} does not have corresponding corner".format(self))

# ----------------------------------------------------------------------------
# -- Position ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class Position(namedtuple('Position', 'x y')):
    """A tuple speiciying a position in a 2D array.

    Args:
        x (:obj:`int`): The X-dimensional position
        y (:obj:`int`): The Y-dimensional position
    """

    def __add__(self, position):
        return Position(self.x + position[0], self.y + position[1])

    def __iadd__(self, position):
        return self.__add__(position)

    def __sub__(self, position):
        return Position(self.x - position[0], self.y - position[1])

    def __isub__(self, position):
        return self.__sub__(position)

    def __neg__(self):
        return Position(-self.x, -self.y)

    def __str__(self):
        return 'Position({}, {})'.format(self.x, self.y)

# ----------------------------------------------------------------------------
# -- Net Class ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class NetClass(Enum):
    """Class for nets."""
    primitive = 0           #: input/outputs of primitives
    mode = 1                #: input/outputs of a multi-mode primitive mapped into one of its logical modes
    cluster = 2             #: input/outputs of intermediate level modules inside blocks
    blockport = 3           #: input/outputs of blocks
    io = 4                  #: external input/outputs of IOB/arrays
    global_ = 5             #: global wires/clocks of blocks/arrays
    segment = 6             #: routing wire segments and bridges
    blockpin = 7            #: ports in connection box that correspond to block ports

# ----------------------------------------------------------------------------
# -- Module Class ------------------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleClass(Enum):
    """Class for modules."""
    primitive = 0           #: user available primitive cells
    cluster = 1             #: clusters
    mode = 2                #: one logical mode of a multi-mode primitive
    io_block = 3            #: IO block
    logic_block = 4         #: logic block
    switch_box = 5          #: switch box
    connection_box = 6      #: connection box
    array = 7               #: array
    switch = 8              #: switch

    @property
    def is_block(self):
        """:obj:`bool`: Test if this module is a block."""
        return self in (ModuleClass.io_block, ModuleClass.logic_block)

    @property
    def is_routing_box(self):
        """:obj:`bool`: Test if this module is a routing box."""
        return self in (ModuleClass.switch_box, ModuleClass.connection_box)

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

# ----------------------------------------------------------------------------
# -- Global ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Global(Object):
    """Defining a global wire.

    Args:
        name (:obj:`str`): Name of this global wire
        width (:obj:`int`): Number of bits of this global wire
        is_clock (:obj:`bool`): If the global wire is a clock wire
    """

    __slots__ = ['_name', '_width', '_is_clock', '_bound_to_position', '_bound_to_subblock']
    def __init__(self, name, width = 1, is_clock = False):
        if is_clock and width != 1:
            raise PRGAInternalError("Clock wire must be 1-bit wide")
        self._name = name
        self._width = width
        self._is_clock = is_clock
        self._bound_to_position = None
        self._bound_to_subblock = None

    @property
    def name(self):
        """:obj:`str`: Name of this global wire."""
        return self._name

    @property
    def width(self):
        """:obj:`int`: Number of bits of this global wire."""
        return self._width

    @property
    def is_clock(self):
        """:obj:`bool`: Test if this global wire is a clock wire."""
        return self._is_clock

    @property
    def is_bound(self):
        """:obj:`bool`: Test if this global wire is already bound to a specific IOB."""
        return self._bound_to_position is not None

    @property
    def bound_to_position(self):
        """`Position` or ``None``: The position of the tile in which the global wire is bound to."""
        return self._bound_to_position

    @property
    def bound_to_subblock(self):
        """:obj:`int` or ``None``: The sub-IOB in which the global wire is bound to."""
        return self._bound_to_subblock

    def bind(self, position, subblock):
        """Bind the global wire to the ``subblock``-th IOB at ``position``.
        
        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            subblock (:obj:`int`):
        """
        self._bound_to_position = Position(*position)
        self._bound_to_subblock = subblock

# ----------------------------------------------------------------------------
# -- Segment -----------------------------------------------------------------
# ----------------------------------------------------------------------------
class Segment(namedtuple('Segment', 'name width length')):
    """Defining a segment prototype.

    Args:
        name (:obj:`str`): Name of this segment
        width (:obj:`int`): Number of wire segments originated from one tile to one orientation
        length (:obj:`int`): Length of this segment
    """
    pass

# ----------------------------------------------------------------------------
# -- Segment/Bridge Type -----------------------------------------------------
# ----------------------------------------------------------------------------
class SegmentType(Enum):
    """Segment/Bridge types."""
    # switch box outputs
    sboxout = 0             #: switch box outputs
    # switch box inputs
    sboxin_regular = 1      #: switch box inputs that are connected all the way to a switch box output
    sboxin_cboxout = 2      #: switch box inputs that are connected all the way to a connection box output
    sboxin_cboxout2 = 3     #: in case two connection boxes are used per routing channel
    # connection box outputs
    cboxout = 4             #: connection box outputs
    # connection box inputs
    cboxin = 5              #: connection box inputs
    # array ports
    array_regular = 6       #: array inputs/outputs that are connected all the way to a switch box output
    array_cboxin = 7        #: array inputs/outputs that are connected all the way to a connection box output
    array_cboxin2 = 8       #: in case two connection boxes are used per routing channel

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
        """`Port` or `Segment`: Prototype of this routing node ID."""
        raise NotImplementedError

    @abstractproperty
    def node_type(self):
        """`NetClass`: Type of this node (blockpin or segment)."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Segment/Bridge ID -------------------------------------------------------
# ----------------------------------------------------------------------------
class SegmentID(Object, AbstractRoutingNodeID):
    """ID of segments and bridges.

    Args:
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): anchor position
        prototype (`Segment`):
        orientation (`Orientation`): orientation
        segment_type (`SegmentType`): type of the segment/bridge
    """

    __slots__ = ['position', 'prototype', 'orientation', 'segment_type']
    def __init__(self, position, prototype, orientation, segment_type):
        self.position = Position(*position)
        self.prototype = prototype
        self.orientation = orientation
        self.segment_type = segment_type

    def __hash__(self):
        return hash( (self.position.x, self.position.y, self.prototype.name, self.orientation, self.segment_type) )

    def __str__(self):
        return 'SegmentID({}, ({}, {}), {}, {})'.format(self.segment_type.name,
                self.position.x, self.position.y, self.prototype.name, self.orientation.name)

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return (self.position == other.position and
                self.prototype is other.prototype and
                self.orientation is other.orientation and
                self.segment_type is other.segment_type)

    def __ne__(self, other):
        return not self.__eq__(other)

    def convert(self, segment_type, override_position = None):
        """`SegmentID`: Convert to another segment ID.

        Args:
            segment_type (`SegmentType`): convert to another segment type
            override_position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): override the position of this segment ID
        """
        return SegmentID(uno(override_position, self.position), self.prototype, self.orientation, segment_type)

    @property
    def node_type(self):
        return NetClass.segment

# ----------------------------------------------------------------------------
# -- Block Pin ID ------------------------------------------------------------
# ----------------------------------------------------------------------------
class BlockPinID(Object, AbstractRoutingNodeID):
    """ID of block pin nodes.

    Args:
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): anchor position
        prototype (`Port`):
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
        return 'BlockPinID(({}, {}, {}), {}.{})'.format(
                self.position.x, self.position.y, self.subblock,
                self.prototype.parent.name, self.prototype.name)

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return (other.node_type.is_blockpin and
                self.position == other.position and
                self.prototype is other.prototype and
                self.subblock == other.subblock)

    def __ne__(self, other):
        return not self.__eq__(other)

    @property
    def node_type(self):
        return NetClass.blockpin
