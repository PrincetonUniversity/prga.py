# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...netlist.net.common import PortDirection
from ...core.common import Position, OrientationTuple, IOType
from ...core.context import Context
from ...exception import PRGAAPIError, PRGAInternalError
from ...util import Object, uno

import re

__all__ = ["IOPlanner"]

_reprog_bit = re.compile('^(?P<name>.*?)(?:\[(?P<index>\d+)\])?$')

# ----------------------------------------------------------------------------
# -- IO Planner --------------------------------------------------------------
# ----------------------------------------------------------------------------
class IOPlanner(Object):
    """Helper class for I/O assignment.
    
    Args:
        summary (`Context` or `ContextSummary`):
        start_pos (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Starting position for scanning
        start_subtile (:obj:`int`): Starting subtile for scanning
        counterclockwise (:obj:`bool`): If set, scan IO in counter-clockwise order.
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

        if isinstance(summary, Context):
            summary = summary.summary

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

    def use(self, position, subtile, iotype):
        """Mark the IO at the specified location as used.

        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            subtile (:obj:`int`):
            iotype (`IOType`):
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

    @classmethod
    def autoplan(cls, context, mod_top, fixed = None):
        """Automatically generate an IO assignment.

        Args:
            context (`Context` or `ContextSummary`):
            mod_top (`VerilogModule`): Top-level module of target design
            fixed (:obj:`Mapping` [:obj:`str`, :obj:`tuple` [`Position`, :obj:`int` ]]): Manually assigned
                IOs

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`tuple` [`Position`, :obj:`int` ]]): Mapping from port names
                to IOs
        """
        assigned = {}
        planner = cls(context)
        # process fixed assignments
        for name, (position, subtile) in iteritems(uno(fixed, {})):
            direction = PortDirection.input_
            if name.startswith('out:'):
                name = name[4:]
                direction = PortDirection.output
            matched = _reprog_bit.match(name)
            port_name, index = matched.group('name', 'index')
            index = None if index is None else int(index)
            if (port := mod_top.ports.get(port_name)) is None:
                raise PRGAAPIError("Port '{}' not found in module '{}'"
                        .format(port_name, mod_top.name))
            elif port.direction is not direction:
                raise PRGAAPIError("Direction mismatch: port '{}' is {} in behavioral model but {} in IO bindings"
                        .format(port_name, port.direction.name, direction))
            elif index is None and (port.low is not None and port.high - port.low > 1):
                raise PRGAAPIError("Port '{}' is a multi-bit bus and requires an index"
                        .format(port_name))
            elif index is not None and (port.low is None or index < port.low or index >= port.high):
                raise PRGAAPIError("Bit index '{}' is not in port '{}'"
                        .format(index, port_name))
            planner.use( position, subtile, direction.case(IOType.ipin, IOType.opin) )
            assigned[name] = position, subtile
        # assign IOs
        for port_name, port in iteritems(mod_top.ports):
            key = port.direction.case("", "out:") + port_name
            if port.low is None or port.high - port.low == 1:
                if key in assigned:
                    continue
                assigned[key] = planner.pop(port.direction.case(IOType.ipin, IOType.opin))
            else:
                for i in range(port.low, port.high):
                    bit_name = '{}[{}]'.format(key, i)
                    if bit_name in assigned:
                        continue
                    assigned[bit_name] = planner.pop(port.direction.case(IOType.ipin, IOType.opin))
        return assigned
