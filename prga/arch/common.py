# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Object, Enum
from prga.exception import PRGAInternalError

from collections import namedtuple

__all__ = ['Dimension', 'Direction', 'Orientation', 'Position']

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
    auto = 0        #: automatically determine the orientation. Not valid in some cases
    north = 1       #: Direction.inc x Dimension.y
    east = 2        #: Direction.inc x Dimension.x
    south = 3       #: Direction.dec x Dimension.y
    west = 4        #: Direction.dec x Dimension.x

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

    @classmethod
    def compose(cls, dimension, direction):
        """Compose a dimension and a direction to an orientation.

        Args:
            dimension (`Dimension`):
            direction (`Direction`):
        """
        return dimension.switch(x = direction.switch(inc = Orientation.east, dec = Orientation.west),
                                y = direction.switch(inc = Orientation.north, dec = Orientation.south))

# ----------------------------------------------------------------------------
# -- Position ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class Position(namedtuple('Position', 'x y')):
    """A tuple specifying a position in an array.

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
        return self._bound_to_position is None

    @property
    def bound_to_position(self):
        """`Position` or ``None``: The position of the tile in which the global wire is bound to."""
        return self._bound_to_position

    @property
    def bound_to_subblock(self):
        """:obj:`int` or ``None``: The sub-IOB in which the global wire is bound to."""
        return self._bound_to_subblock

    @property
    def bind(self, position, subblock):
        """Bind the global wire to the ``subblock``-th IOB at ``position``.
        
        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            subblock (:obj:`int`):
        """
        self._bound_to_position = Position(*position)
        self._bound_to_subblock = subblock
