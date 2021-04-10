# -*- encoding: ascii -*-

from ...netlist import PortDirection
from ...core.common import Position, OrientationTuple, IOType, PortDirection
from ...exception import PRGAAPIError, PRGAInternalError
from ...util import Object, uno

import re, os, sys, logging
_logger = logging.getLogger(__name__)

__all__ = ["IOPlanner"]

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
    
    _reprog_bit = re.compile('^(?P<out>out:)?(?P<name>.*?)(?:\[(?P<index>\d+)\])?$')

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

    def use(self, direction, position, subtile):
        """Mark the IO at the specified location as used.

        Args:
            direction (`PortDirection` or :obj:`str`):
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            subtile (:obj:`int`):
        """
        if (io := self.avail_globals.pop( (position, subtile), None )) is None:
            if (io := self.avail_nonglobals.pop( (position, subtile), None )) is None:
                if (io := self.used.get( (position, subtile) )) is None:
                    raise PRGAAPIError("No IO found at {}, {}".format(Position(*position), subtile))
                else:
                    raise PRGAAPIError("IO at {}, {} is already used".format(Position(*position), subtile))
        direction = PortDirection.construct(direction)
        if direction not in io.directions:
            raise PRGAAPIError("IO at {}, {} cannot be used as {:r}".format(Position(*position), subtile, direction))
        self.used[position, subtile] = io

    def pop(self, direction, *, force_change_tile = False, use_global_driver_as_normal = False):
        """Pop the next available IO of for ``direction``.

        Args:
            direction (`PortDirection` or :obj:`str`):

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
        io = None
        direction = PortDirection.construct(direction)
        while True:
            key = self.position, self.subtile
            if (io := self.avail_nonglobals.get( key, None )) is None:
                if not use_global_driver_as_normal or (io := self.avail_globals.get( key, None )) is None:
                    self.__next_position()
                    continue
            if direction in io.directions:
                self.avail_nonglobals.pop( key, None )
                self.avail_globals.pop( key, None )
                break
            else:
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
    def autoplan(cls, summary, app):
        """Automatically generate IO constraints and write into ``app``.

        Args:
            summary (`Context` or `ContextSummary`):
            app (`AppIntf`): Interface of the application. May contain partial IO constraints.
        """
        planner = cls(summary)
        # process existing partial constraints
        for port in app.ports.values():
            for _, io in port.iter_io_constraints():
                if io is not None:
                    planner.use(port.direction, *io)
        # complete the constraints
        for port in app.ports.values():
            for i, io in port.iter_io_constraints():
                if io is None:
                    port.set_io_constraint(*planner.pop(port.direction), i)

    @classmethod
    def parse_io_constraints(cls, app, f):
        """Parse a partial or complete IO constraint file.

        Args:
            app (`AppIntf`): Interface of the application.
            f (:obj:`str` of file-like object):
        """
        if isinstance(f, str):
            f = open(f)

        for lineno, line in enumerate(f):
            line = line.split("#")[0].strip()
            if line == '':
                continue
            try:
                name, x, y, subtile = line.split()
                x, y, subtile = map(int, (x, y, subtile))
            except ValueError:
                raise PRGAAPIError("Invalid constraint at line {}".format(lineno + 1))
            if (matched := cls._reprog_bit.match(name)) is None:
                raise PRGAAPIError("Invalid port name at line {}: {}".format(lineno + 1, name))

            out, name, index = matched.group("out", "name", "index")
            if index is not None:
                index = int(index)

            if (port := app.ports.get(name)) is None:
                _logger.warning("Application '{}' does not have port '{}'".format(app.name, name))

            elif port.direction.case(bool(out), not out):
                raise PRGAAPIError("Port '{}' of app '{}' is an {}"
                        .format(name, app.name, port.direction.case("input", "output")))
            else:
                port.set_io_constraint((x, y), subtile, index)

    @classmethod
    def print_io_constraints(cls, app, ostream = sys.stdout):
        """Print IO constraints.

        Args:
            app (`AppIntf`): Interface of the application.
            ostream (:obj:`str` or file-like object):
        """
        if isinstance(ostream, str):
            if d := os.path.dirname(ostream):
                os.makedirs(d, exist_ok = True)
            ostream = open(ostream, "w")
        for port in app.ports.values():
            for i, io in port.iter_io_constraints():
                if io is not None:
                    if i is None:
                        ostream.write("{}{} {} {} {}\n"
                                .format(port.direction.case("", "out:"), port.name, io[0][0], io[0][1], io[1]))
                    else:
                        ostream.write("{}{}[{}] {} {} {}\n"
                                .format(port.direction.case("", "out:"), port.name, i, io[0][0], io[0][1], io[1]))
