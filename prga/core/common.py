# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Common enums for FPGA builders."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..util import Abstract, Object, Enum, uno
from ..exception import PRGAInternalError

from collections import namedtuple
from abc import abstractproperty
from copy import copy
from math import ceil

__all__ = ['Dimension', 'Direction', 'Orientation', 'OrientationTuple', 'Corner', 'Position',
        'NetClass', 'IOType', 'ModuleClass', 'PrimitiveClass', 'PrimitivePortClass', 'ModuleView',
        'Global', 'Segment', 'DirectTunnel', 'BridgeType', 'SegmentID', 'BlockPinID',
        'BlockPortFCValue', 'BlockFCValue', 'SwitchBoxPattern']

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
    west = 3       #: Direction.dec x Dimension.x

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
        else:
            raise PRGAInternalError("{} does not have an opposite Orientation".format(self))

    def decompose(self):
        """Decompose this orientation into dimension and direcion.

        Returns:
            `Dimension`:
            `Direction`:
        """
        return self.dimension, self.direction

    @classmethod
    def compose(cls, dimension, direction):
        """Compose a dimension and a direction to an orientation.

        Args:
            dimension (`Dimension`):
            direction (`Direction`):
        """
        if isinstance(dimension, Direction):
            dimension, direction = direction, dimension
        return dimension.case(direction.case(Orientation.east, Orientation.west),
                direction.case(Orientation.north, Orientation.south))

# ----------------------------------------------------------------------------
# -- Orientation Tuple -------------------------------------------------------
# ----------------------------------------------------------------------------
class OrientationTuple(namedtuple('OrientationTuple', 'north east south west')):
    """A tuple of values, one for each orientation.

    Args:
        default: Default value for all orientations if no override is provided

    Keyword Args:
        north: Value for the north orientation
        east: Value for the east orientation
        south: Value for the south orientation
        west: Value for the west orientation

    Notes:
        The specific value of an orientation can be accessed simply by indexing this tuple with that orientation enum.
        For example: ``t = OrientationTuple(False); print(t[Orientation.north])``
    """

    def __new__(cls, default = None, *, north = None, east = None, south = None, west = None):
        return super(OrientationTuple, cls).__new__(cls,
                north = north if north is not None else default,
                east = east if east is not None else default,
                south = south if south is not None else default,
                west = west if west is not None else default)

    def __getnewargs_ex__(self):
        return (None, ), {"north": self.north, "east": self.east, "south": self.south, "west": self.west}

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
        if ori_a.is_north:
            return ori_b.case(west = Corner.northwest, east = Corner.northeast)
        elif ori_a.is_east:
            return ori_b.case(north = Corner.northeast, south = Corner.southeast)
        elif ori_a.is_south:
            return ori_b.case(west = Corner.southwest, east = Corner.southeast)
        else:
            return ori_b.case(north = Corner.northwest, south = Corner.southwest)

    @property
    def opposite(self):
        """`Corner`: The opposite corner of this corner."""
        return self.case(
                Corner.southwest,
                Corner.southeast,
                Corner.northwest,
                Corner.northeast)

    def decompose(self):
        """:obj:`tuple` (`Orientation`, `Orientation`): Decompose this corner into two `Orientation`s. X-dimension
        first."""
        return self.case(
                (Orientation.east, Orientation.north),
                (Orientation.west, Orientation.north),
                (Orientation.east, Orientation.south),
                (Orientation.west, Orientation.south))

    def dotx(self, dim):
        """`Direction`: Direction in `Dimension` ``dim``."""
        return self.case(
                dim.case(Direction.inc, Direction.inc),
                dim.case(Direction.dec, Direction.inc),
                dim.case(Direction.inc, Direction.dec),
                dim.case(Direction.dec, Direction.dec))

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

    def __repr__(self):
        return 'Position({}, {})'.format(self.x, self.y)

# ----------------------------------------------------------------------------
# -- Net Class ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class NetClass(Enum):
    """Class for nets."""
    # within block
    user = 0                #: input/outputs of user-visible modules (e.g. primitive, mode, cluster)

    # routing resources
    block = 1               #: block ports
    segment = 2             #: segment driver
    bridge = 3              #: bridges between blocks, boxes and arrays

    # logical-only nets
    io = 4                  #: chip-level inputs/outputs
    global_ = 5             #: global nets
    switch = 6              #: switch input/outputs
    cfg = 7                 #: configuration ports

# ----------------------------------------------------------------------------
# -- IO Type -----------------------------------------------------------------
# ----------------------------------------------------------------------------
class IOType(Enum):
    """Types of top-level IOs."""
    ipin = 0                #: input 
    opin = 1                #: output 
    oe = 2                  #: output enable 

    @property
    def opposite(self):
        """`IOType`: Opposite type of the IO."""
        if self is IOType.ipin:
            return IOType.opin
        elif self is IOType.opin:
            return IOType.ipin
        else:
            raise PRGAInternalError("{} does not have an opposite IO type"
                    .format(self))

# ----------------------------------------------------------------------------
# -- Module Class ------------------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleClass(Enum):
    """Class for modules."""
    # below block
    primitive = 0           #: user available primitive cells
    cluster = 1             #: clusters
    mode = 2                #: one logical mode of a multi-mode primitive

    # block
    io_block = 3            #: IO block
    logic_block = 4         #: logic block

    # routing boxes
    switch_box = 5          #: switch box
    connection_box = 6      #: connection box

    # tiles & arrays
    tile = 7                #: tile (containing blocks and connection boxes)
    leaf_array = 8          #: leaf array (containing tiles and switch boxes)
    nonleaf_array = 9       #: non-leaf array (containing leaf arrays and non-leaf arrays)

    # logical-only modules
    switch = 10              #: switch
    cfg = 11                #: configuration modules

    @property
    def is_block(self):
        """:obj:`bool`: Test if this module is a block."""
        return self in (ModuleClass.io_block, ModuleClass.logic_block)

    @property
    def is_routing_box(self):
        """:obj:`bool`: Test if this module is a routing box."""
        return self in (ModuleClass.switch_box, ModuleClass.connection_box)

    @property
    def is_array(self):
        """:obj:`bool`: Test if this module is an array."""
        return self in (ModuleClass.leaf_array, ModuleClass.nonleaf_array)

# ----------------------------------------------------------------------------
# -- Primitive Class ---------------------------------------------------------
# ----------------------------------------------------------------------------
class PrimitiveClass(Enum):
    """Enum types for VPR's `class`_ attribute of leaf `pb_type`_ .

    .. _class:
        https://docs.verilogtorouting.org/en/latest/arch/reference/#arch-classes

    .. _pb_type:
        https://docs.verilogtorouting.org/en/latest/arch/reference/#tag-%3Cpb_typename=
    """
    # built-in primitives
    lut         = 0     #: look-up table
    flipflop    = 1     #: D-flipflop
    inpad       = 2     #: input pad
    outpad      = 3     #: output pad 

    # user-defined primitives
    memory      = 4     #: user-defined memory
    custom      = 5     #: user-defined primitives
    multimode   = 6     #: user-defined multi-mode primitives

# ----------------------------------------------------------------------------
# -- Primitive Port Class ----------------------------------------------------
# ----------------------------------------------------------------------------
class PrimitivePortClass(Enum):
    """Enum types for VPR's `port_class`_ attribute of leaf ports.

    .. _port_class:
        https://docs.verilogtorouting.org/en/latest/arch/reference/#classes
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
# -- Module View -------------------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleView(Enum):
    """A specific view of a module.
    
    Currently PRGA only uses the ``user`` view and the ``logical`` view.
    """

    user = 0        #: user view of a module
    logical = 1     #: logical view of a module
    physical = 2    #: physical view of a module

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

    __slots__ = ['_name', '_width', '_is_clock', '_bound_to_position', '_bound_to_subtile']
    def __init__(self, name, width = 1, is_clock = False):
        if is_clock and width != 1:
            raise PRGAInternalError("Clock wire must be 1-bit wide")
        self._name = name
        self._width = width
        self._is_clock = is_clock
        self._bound_to_position = None
        self._bound_to_subtile = None

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
    def bound_to_subtile(self):
        """:obj:`int` or ``None``: The IO block that the global wire is bound to."""
        return self._bound_to_subtile

    def bind(self, position, subtile):
        """Bind the global wire to the ``subtile``-th IO block at ``position``.
        
        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            subtile (:obj:`int`):
        """
        self._bound_to_position = Position(*position)
        self._bound_to_subtile = subtile

# ----------------------------------------------------------------------------
# -- Direct Inter-block Tunnel -----------------------------------------------
# ----------------------------------------------------------------------------
class DirectTunnel(namedtuple("DirectTunnel", "name source sink offset")):
    """Direct inter-block tunnels.

    Args:
        name (:obj:`str`): Name of the inter-block tunnel
        source (`Port`): Source of the tunnel. Must be a logic block output port
        sink (`Port`): Sink of the tunnel. Must be a logic block input port
        offset (`Position`): Position of the source port relative to the sink port
            This definition is the opposite of how VPR defines a ``direct`` tag. In addition, ``offset`` is
            defined based on the position of the ports, not the blocks
    """

    def __new__(cls, name, source, sink, offset):
        return super(DirectTunnel, cls).__new__(cls, name, source, sink, Position(*offset))

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
# -- Bridge Type -------------------------------------------------------------
# ----------------------------------------------------------------------------
class BridgeType(Enum):
    """Bridge types."""

    # regular
    regular_input = 0       #: regular segment input
    regular_output = 1      #: regular segment output

    # cboxout-sboxin bridge
    cboxout = 2             #: cboxout-sboxin
    cboxout2 = 3            #: secondary cboxout-sboxin

# ----------------------------------------------------------------------------
# -- Abstract Routing Node ID ------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractRoutingNodeID(Hashable, Abstract):
    """Abstract base class for routing node IDs."""

    # == low-level API =======================================================
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
        """`NetClass`: Type of this node (block, segment or bridge)."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Segment ID --------------------------------------------------------------
# ----------------------------------------------------------------------------
class SegmentID(namedtuple('SegmentID', 'position prototype orientation'), AbstractRoutingNodeID):
    """ID of segments.

    Args:
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): anchor position
        prototype (`Segment`):
        orientation (`Orientation`): orientation
    """

    def __new__(cls, position, prototype, orientation):
        return super(SegmentID, cls).__new__(cls, Position(*position), prototype, orientation)

    def __hash__(self):
        return hash( (self.position.x, self.position.y, self.prototype.name, self.orientation) )

    def __repr__(self):
        return 'SegmentID({}, ({}, {}), {})'.format(
                self.prototype.name, self.position.x, self.position.y, self.orientation.name)

    def move(self, offset):
        """Create a new `SegmentID` with the specified adjustment to the position of this segment ID.

        Args:
            offset (:obj:`tuple` [:obj:`int`, :obj:`int` ]):

        Returns:
            `SegmentID`:
        """
        if offset == (0, 0):
            return self
        else:
            return SegmentID(self.position + offset, self.prototype, self.orientation)

    def convert(self, bridge_type = None):
        """Convert to a segment ID or bridge ID.

        Args:
            bridge_type (`BridgeType`): Convert to a `BridgeID` of the specified type, or a `SegmentID` if not
                specified
        
        Returns:
            `SegmentID` if ``bridge_type`` is not specified; Otherwise `BridgeID`
        """
        if bridge_type is None:
            return self
        else:
            return BridgeID(self.position, self.prototype, self.orientation, bridge_type)

    @property
    def node_type(self):
        return NetClass.segment

# ----------------------------------------------------------------------------
# -- Bridge ID -------------------------------------------------------
# ----------------------------------------------------------------------------
class BridgeID(namedtuple('BridgeID', 'position prototype orientation bridge_type'), AbstractRoutingNodeID):
    """ID of bridges.

    Args:
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): anchor position
        prototype (`Segment`):
        orientation (`Orientation`): orientation
        bridge_type (`BridgeType`): type of the bridge
    """

    def __new__(cls, position, prototype, orientation, bridge_type):
        return super(BridgeID, cls).__new__(cls, Position(*position), prototype, orientation, bridge_type)

    def __hash__(self):
        return hash( (self.position.x, self.position.y, self.prototype.name, self.orientation, self.bridge_type) )

    def __repr__(self):
        return 'BridgeID[{}]({}, ({}, {}), {})'.format(self.bridge_type.name,
                self.prototype.name, self.position.x, self.position.y, self.orientation.name)

    def move(self, offset):
        """Create a new `BridgeID` with the specified adjustment to the position of this bridge ID.

        Args:
            offset (:obj:`tuple` [:obj:`int`, :obj:`int` ]):

        Returns:
            `BridgeID`:
        """
        if offset == (0, 0):
            return self
        else:
            return BridgeID(self.position + offset, self.prototype, self.orientation, self.bridge_type)

    def convert(self, bridge_type = None):
        """Convert to a segment ID or bridge ID.

        Args:
            bridge_type (`BridgeType`): Convert to a `BridgeID` of the specified type, or a `SegmentID` if not
                specified
        
        Returns:
            `SegmentID` if ``bridge_type`` is not specified; Otherwise `BridgeID`
        """
        if bridge_type is None:
            return SegmentID(self.position, self.prototype, self.orientation)
        elif bridge_type is self.bridge_type:
            return self
        else:
            return BridgeID(self.position, self.prototype, self.orientation, bridge_type)

    @property
    def node_type(self):
        return NetClass.bridge

# ----------------------------------------------------------------------------
# -- Block Pin ID ------------------------------------------------------------
# ----------------------------------------------------------------------------
class BlockPinID(namedtuple('BlockPinID', 'position prototype subtile'), AbstractRoutingNodeID):
    """ID of block pin nodes.

    Args:
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): anchor position
        prototype (`Port`):
        subtile (:obj:`int`): subtile ID in a tile
    """

    def __new__(cls, position, prototype, subtile = 0):
        return super(BlockPinID, cls).__new__(cls, Position(*position), prototype, subtile)

    def __hash__(self):
        return hash( (self.position.x, self.position.y, self.prototype.parent.key, self.prototype.key,
            self.subtile) )

    def __repr__(self):
        return 'BlockPinID(({}, {}, {}), {}.{})'.format(
                self.position.x, self.position.y, self.subtile,
                self.prototype.parent.name, self.prototype.name)

    def move(self, offset):
        """Create a new `BlockPinID` with the specified adjustment to the position of this ID.

        Args:
            offset (:obj:`tuple` [:obj:`int`, :obj:`int` ]):

        Returns:
            `BlockPinID`:
        """
        if offset == (0, 0):
            return self
        else:
            return BlockPinID(self.position + offset, self.prototype, self.subtile)

    @property
    def node_type(self):
        return NetClass.block

# ----------------------------------------------------------------------------
# -- Block FC Value ----------------------------------------------------------
# ----------------------------------------------------------------------------
class BlockPortFCValue(namedtuple('BlockPortFCValue', 'default overrides')):
    """A named tuple used for defining FC values for a specific block port.

    Args:
        default (:obj:`int` or :obj:`float`): the default FC value for this port
        overrides (:obj:`Mapping` [:obj:`str`, :obj:`int` or :obj:`float` ]): the FC value for a
            specific segment type
    """

    def __new__(cls, default, overrides = None):
        return super(BlockPortFCValue, cls).__new__(cls, default, uno(overrides, {}))

    @classmethod
    def _construct(cls, *args):
        """Quick construction of a `BlockPortFCValue`."""
        if len(args) == 1:
            if isinstance(args[0], BlockPortFCValue):
                return args[0]
            elif isinstance(args[0], tuple):
                return cls(*args[0])
        return cls(*args)

    @property
    def default(self):
        """:obj:`int` or :obj:`float`: Default FC value for this block port."""
        return super(BlockPortFCValue, self).default

    @property
    def overrides(self):
        """:obj:`Mapping` [:obj:`str`, :obj:`int` or :obj:`float` ]): the FC value for a specific segment type."""
        return super(BlockPortFCValue, self).overrides

    def segment_fc(self, segment, all_sections = False):
        """Get the FC value for a specific segment.

        Args:
            segment (`Segment`):
            all_sections (:obj:`bool`): if all sections of a segment longer than 1 should be taken into consideration

        Returns:
            :obj:`int`: Number of tracks connected per port bit
        """
        multiplier = segment.length if all_sections else 1
        fc = self.overrides.get(segment.name, self.default)
        if isinstance(fc, int):
            if fc < 0 or fc >= segment.width * multiplier:
                raise PRGAInternalError("Invalid FC value ({}) for segment '{}'".format(fc, segment.name))
            return fc
        elif isinstance(fc, float):
            if fc < 0 or fc > 1:
                raise PRGAInternalError("Invalid FC value ({}) for segment '{}'".format(fc, segment.name))
            return int(ceil(fc * segment.width * multiplier))
        else:
            raise PRGAInternalError("Invalid FC value ({}) for segment '{}'".format(fc, segment.name))

class BlockFCValue(namedtuple('BlockFCValue', 'default_in default_out overrides')):
    """A named tuple used for defining FC values for a specific block.

    Args:
        default_in (:obj:`int`, :obj:`float`, or `BlockPortFCValue`): the default FC value for all input ports
        default_out (:obj:`int`, :obj:`float`, or `BlockPortFCValue`): the default FC value for all output ports.
            Same as the default value for input ports if not set
        overrides (:obj:`Mapping` [:obj:`str`, :obj:`int` or :obj:`float` or `BlockPortFCValue` ]): the FC value for
            a specific port
    """
    def __new__(cls, default_in, default_out = None, overrides = None):
        default_in = BlockPortFCValue._construct(default_in)
        if default_out is None:
            default_out = default_in
        else:
            default_out = BlockPortFCValue._construct(default_out)
        if overrides is None:
            overrides = {}
        else:
            overrides = {k: BlockPortFCValue._construct(v) for k, v in iteritems(overrides)}
        return super(BlockFCValue, cls).__new__(cls, default_in, default_out, uno(overrides, {}))

    @classmethod
    def _construct(cls, *args):
        """Quick construction of a `BlockFCValue`."""
        if len(args) == 1:
            if isinstance(args[0], BlockFCValue):
                return args[0]
            elif isinstance(args[0], tuple):
                return cls(*args[0])
        return cls(*args)

    def port_fc(self, port, segment, all_sections = False):
        """Get the FC value for a specific port and a specific segment.

        Args:
            port (`Port`): 
            segment (`Segment`):
            all_sections (:obj:`bool`): if all sections of a segment longer than 1 should be taken into consideration

        Returns:
            :obj:`int`: Number of tracks connected per port bit
        """
        return self.overrides.get(port.key, port.direction.case(self.default_in, self.default_out)).segment_fc(
                segment, all_sections)

# ----------------------------------------------------------------------------
# -- Switch Box Pattern ------------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchBoxPattern(Object):
    """Switch box patterns."""

    class _pattern(Object):
        __slots__ = ["_fill_corners"]

        def __init__(self, fill_corners = Corner):
            try:
                self._fill_corners = set(iter(fill_corners))
            except TypeError:
                self._fill_corners = {fill_corners}

        def __call__(self, *args, **kwargs):
            return type(self)(*args, **kwargs)

        def __eq__(self, other):
            if not isinstance(other, type(self)) or other.fill_corners != self.fill_corners:
                return False
            else:
                for slot in self.__slots__:
                    if getattr(self, slot) != getattr(other, slot):
                        return False
                return True

        def __ne__(self, other):
            return not self.__eq__(other)

        def __getattr__(self, attr):
            if attr.startswith("is"):
                return attr[2:] == type(self).__name__
            raise AttributeError(attr)

        @property
        def fill_corners(self):
            return self._fill_corners

    class _subset(_pattern):
        pass

    class _universal(_pattern):
        pass

    class _wilton(_pattern):
        pass

    class _cycle_free(_pattern):
        pass

    class _span_limited(_pattern):
        __slots__ = ["_max_span"]

        def __init__(self, fill_corners = Corner, max_span = None):
            super(SwitchBoxPattern._span_limited, self).__init__(fill_corners)
            self._max_span = max_span

        @property
        def max_span(self):
            return self._max_span

    class _turn_limited(_pattern):
        __slots__ = ["_max_turn"]

        def __init__(self, fill_corners = Corner, max_turn = None):
            super(SwitchBoxPattern._turn_limited, self).__init__(fill_corners)
            self._max_turn = max_turn

        @property
        def max_turn(self):
            return self._max_turn

SwitchBoxPattern.subset = SwitchBoxPattern._subset()
SwitchBoxPattern.universal = SwitchBoxPattern._universal()
SwitchBoxPattern.wilton = SwitchBoxPattern._wilton()
SwitchBoxPattern.cycle_free = SwitchBoxPattern._cycle_free()
SwitchBoxPattern.span_limited = SwitchBoxPattern._span_limited()
SwitchBoxPattern.turn_limited = SwitchBoxPattern._turn_limited()
