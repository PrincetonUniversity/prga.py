# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...netlist import PortDirection
from ...core.common import Position, OrientationTuple, IOType
from ...exception import PRGAAPIError, PRGAInternalError
from ...util import Object, uno

import re, os, sys

__all__ = ["IOPlanner"]

_reprog_bit = re.compile('^(?P<out>out:)?(?P<name>.*?)(?:\[(?P<index>\d+)\])?$')

# ----------------------------------------------------------------------------
# -- IO Constraints List -----------------------------------------------------
# ----------------------------------------------------------------------------
class IOConstraints(MutableSequence):
    """IO constraints of a port.

    Args:
        type_ (`IOType`): Type of IO
        low (:obj:`int`): LSB index of the port
        high (:obj:`int`): MSB + 1 index of the port
    """

    __slots__ = ["type_", "low", "_elements"]

    def __init__(self, type_, low = None, high = None):
        self.type_ = type_
        self.low = uno(low, 0)
        high = uno(high, self.low + 1)
        self._elements = [None] * (high - self.low)

    def __getitem__(self, index):
        return self._elements[index - self.low]

    def __setitem__(self, index, value):
        self._elements[index - self.low] = value

    def __delitem__(self, index):
        raise NotImplementedError("Cannot delete from IOConstraints")

    def insert(self, index, value):
        raise NotImplementedError("Cannot insert to IOConstraints")

    def __len__(self):
        return len(self._elements)

    def __iter__(self):
        for i in self._elements:
            yield i

    def resize(self, low = None, high = None):
        if low is not None:
            if low < self.low:
                self._elements = [None] * (self.low - low) + self._elements
            elif low > self.low:
                self._elements = self._elements[low - self.low:]
            self.low = low
        if high is not None:
            if high - self.low > len(self._elements):
                self._elements += [None] * (high - self.low)
            elif high - self.low < len(self._elements):
                self._elements = self._elements[:high - self.low]

# ----------------------------------------------------------------------------
# -- IO Planner --------------------------------------------------------------
# ----------------------------------------------------------------------------
class IOPlanner(Object):
    """Helper class for creating I/O constraints.
    
    Args:
        summary (`Context` or `ContextSummary`):
        start_pos (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Starting position for auto-planning
        start_subtile (:obj:`int`): Starting subtile for auto-planning
        counterclockwise (:obj:`bool`): If set, auto-plan IO in counter-clockwise order.
    """

    __slots__ = ["xmax", "ymax", "avail_nonglobals", "avail_globals", "used", "globals_",
            # scanning
            "position", "subtile", "counterclockwise"]

    def __init__(self, summary, start_pos = (0, 0), subtile = 0, counterclockwise = False):
        self.xmax = 0
        self.ymax = 0
        self.avail_nonglobals = {}
        self.avail_globals = {}
        self.used = {}
        self.globals_ = {}
        self.position = Position(*start_pos)
        self.subtile = subtile
        self.counterclockwise = counterclockwise

        try:
            summary = summary.summary
        except AttributeError:
            pass

        for io in summary.ios:
            if io.global_ is None:
                self.avail_nonglobals[io.position, io.subtile] = io
            else:
                self.avail_globals[io.position, io.subtile] = io
                self.globals_[io.global_.name] = io
            self.xmax = max(self.xmax, io.position.x)
            self.ymax = max(self.ymax, io.position.y)

    def __next_position(self):
        self.subtile = 0
        edge = OrientationTuple(
                north = self.position.y == self.ymax,
                east = self.position.x == self.xmax,
                south = self.position.y == 0,
                west = self.position.x == 0,
                )
        if self.counterclockwise:
            if edge.north:
                if edge.west:
                    self.position -= (0, 1)
                else:
                    self.position -= (1, 0)
            elif edge.east:
                self.position += (0, 1)
            elif edge.south:
                self.position += (1, 0)
            elif edge.west:
                self.position -= (0, 1)
            else:
                raise PRGAInternalError("IO at {}, {} not on edge of the fabric"
                        .format(Position(*self.position), self.subtile))
        else:
            if edge.north:
                if edge.east:
                    self.position -= (0, 1)
                else:
                    self.position += (1, 0)
            elif edge.west:
                self.position += (0, 1)
            elif edge.south:
                self.position -= (1, 0)
            elif edge.east:
                self.position -= (0, 1)
            else:
                raise PRGAInternalError("IO at {}, {} not on edge of the fabric"
                        .format(Position(*self.position), self.subtile))

    def use(self, iotype, position, subtile):
        """Mark the IO at the specified location as used.

        Args:
            iotype (`IOType`):
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            subtile (:obj:`int`):
        """
        if (io := self.avail_globals.pop( (position, subtile), None )) is None:
            if (io := self.avail_nonglobals.pop( (position, subtile), None )) is None:
                if (io := self.used.get( (position, subtile) )) is None:
                    raise PRGAAPIError("No IO found at {}, {}".format(Position(*position), subtile))
                else:
                    raise PRGAAPIError("IO at {}, {} is already used".format(Position(*position), subtile))
        if iotype not in io.types:
            raise PRGAAPIError("IO at {}, {} cannot be used as {:r}".format(Position(*position), subtile, iotype))
        self.used[position, subtile] = io

    def pop(self, iotype, *, force_change_tile = False, use_global_driver_as_normal = False):
        """Pop the next available IO of type `iotype`.

        Args:
            iotype (`IOType`):

        Keyword Args:
            force_change_tile (:obj:`bool`): If set, the scanning will start from a new tile. This is useful when
                trying to reduce routing congestion
            use_global_driver_as_normal (:obj:`bool`): If set, global driver I/O pins are used as regular IO pins

        Returns:
            :obj:`tuple` [`Position`, :obj:`int` ]:
        """
        if len(self.avail_nonglobals) == 0 and (not use_global_driver_as_normal or len(self.avail_globals) == 0):
            raise PRGAAPIError("Ran out of IOs")
        if force_change_tile and self.subtile > 0:
            self.__next_position()
        while (io := self.avail_nonglobals.pop( (self.position, self.subtile), None )) is None:
            if (use_global_driver_as_normal and
                    (io := self.avail_globals.pop( (self.position, self.subtile), None )) is not None):
                break
            self.__next_position()
        self.used[io.position, io.subtile] = io
        self.subtile += 1
        return io.position, io.subtile

    def reset_scanning(self, position = None, subtile = None, counterclockwise = None):
        """Reset scanning pointer.

        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            subtile (:obj:`int`):
            counterclockwise (:obj:`bool`):
        """
        self.position = Position(*uno(position, self.position))
        self.subtile = uno(subtile, self.subtile)
        self.counterclockwise = uno(counterclockwise, self.counterclockwise)

    @classmethod
    def autoplan(cls, context, mod_top, fixed = None):
        """Automatically generate IO constraints.

        Args:
            context (`Context` or `ContextSummary`):
            mod_top (`VerilogModule`): Top-level module of target design
            fixed (:obj:`Mapping` [:obj:`str`, `IOConstraints`]): Manually constrained IOs. This mapping could be
                incomplete

        Returns:
            :obj:`Mapping` [:obj:`str`, `IOConstraints`]): Mapping from port names to list of IOs. Output ports are
                prefixed with "out:" to match VPR's naming convention
        """
        planner = cls(context)
        # initialize constraints
        constraints = {}
        for port_name, port in iteritems(mod_top.ports):
            constraints[port_name] = IOConstraints(port.direction.case(IOType.ipin, IOType.opin), port.low, port.high)
        # process manual constraints
        for name, fixed_constraints in iteritems(uno(fixed, {})):
            if (ios := constraints.get(name)) is None:
                continue
                raise PRGAAPIError("Port '{}' is not found in module '{}'"
                        .format(name, mod_top.name))
            for i, c in enumerate(fixed_constraints, fixed_constraints.low):
                if c is None:
                    continue
                planner.use(ios.type_, *c)
                ios[i] = c
        # complete the constraints
        for key, ios in iteritems(constraints):
            for i, c in enumerate(ios, ios.low):
                if c is not None:
                    continue
                ios[i] = planner.pop(ios.type_)
        return constraints

    @classmethod
    def parse_io_constraints(cls, file_):
        """Parse a partial or complete IO constraint file.

        Args:
            file_ (:obj:`str` of file-like object):

        Returns:
            :obj:`Mapping` [:obj:`str`, `IOConstraints`]: Mapping from port names in the behavioral model to
                IO constraints
        """
        constraints = {}
        if isinstance(file_, basestring):
            file_ = open(file_)
        for lineno, line in enumerate(file_):
            line = line.split("#")[0].strip()
            if line == '':
                continue
            name, x, y, subtile = line.split()
            try:
                x, y, subtile = map(int, (x, y, subtile))
            except ValueError:
                raise PRGAAPIError("Invalid constraint at line {}".format(lineno + 1))
            if (matched := _reprog_bit.match(name)) is None:
                raise PRGAAPIError("Invalid port name at line {}: {}".format(lineno + 1, name))
            out, name, index = matched.group("out", "name", "index")
            index = int(uno(index, 0))
            if (ios := constraints.get(name)) is None:
                ios = constraints[name] = IOConstraints(IOType.opin if out else IOType.ipin, index)
            elif index < ios.low:
                ios.resize(index)
            elif index - ios.low >= len(ios):
                ios.resize(high = index + 1)
            ios[index] = Position(x, y), subtile
        return constraints

    @classmethod
    def print_io_constraints(cls, constraints, ostream = sys.stdout):
        """Print IO constraints.

        Args:
            constraints (:obj:`Mapping` [:obj:`str`, `IOConstraints` ]):
            ostream (:obj:`str` or file-like object):
        """
        if isinstance(ostream, basestring):
            if d := os.path.dirname(ostream):
                makedirs(d)
            ostream = open(ostream, "w")
        for name, ios in iteritems(constraints):
            key = ios.type_.case(ipin = "", opin = "out:") + name
            if len(ios) == 1:
                (x, y), subtile = ios[ios.low]
                ostream.write("{} {} {} {}\n".format(key, x, y, subtile))
            else:
                for i, ((x, y), subtile) in enumerate(ios, ios.low):
                    ostream.write("{}[{}] {} {} {}\n".format(key, i, x, y, subtile))
