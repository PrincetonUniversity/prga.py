# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import PortDirection
from prga.algorithm.util.array import get_hierarchical_tile
from prga.algorithm.util.hierarchy import hierarchical_position
from prga.flow.context import ArchitectureContext
from prga.util import enable_stdout_logging, uno
from prga.exception import PRGAAPIError

from prga_tools.util import find_verilog_top, parse_io_bindings

from itertools import product

import re
import logging
import sys

_logger = logging.getLogger(__name__)
_reprog_bit = re.compile('^(?P<name>.*?)(?:\[(?P<index>\d+)\])?$')

__all__ = ['iobind']

def _find_next_available_io(assignments, current, direction):
    width, height = len(assignments), len(assignments[0])
    x, y, subblock = (0, 0, 0) if current is None else current
    while True:
        unused, used = assignments[x][y]
        if direction.is_input:
            used, unused = unused, used
        for i in range(subblock, len(used)):
            if used[i] is None and (i >= len(unused) or unused[i] is None):
                return x, y, i
        if y == height - 1:
            if x == width - 1:
                return None
            x, y, subblock = x + 1, 0, 0
        else:
            y, subblock = y + 1, 0

def iobind(context, mod_top, fixed = None):
    """Generate IO assignment.

    Args:
        context (`ArchitectureContext`): The architecture context of the custom FPGA
        mod_top (`VerilogModule`): Top-level module of target design
        fixed (:obj:`Mapping` [:obj:`str`, :obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int` ]]): Manually assigned IOs
    """
    # prepare assignment map
    assignments = [[([], []) for _0 in range(context.top.height)] for _1 in range(context.top.width)]
    for x, y in product(range(context.top.width), range(context.top.height)):
        tile = get_hierarchical_tile(context.top, (x, y))
        if tile is not None and hierarchical_position(tile) == (x, y):
            tile = tile[-1].model
            if tile.block.module_class.is_io_block:
                i, o = map(tile.block.physical_ports.get, ("exti", "exto"))
                if i is not None:
                    i = [None] * tile.capacity
                else:
                    i = []
                if o is not None:
                    o = [None] * tile.capacity
                else:
                    o = []
                assignments[x][y] = i, o
    # process fixed assignments
    processed = {}
    for name, (x, y, subblock) in iteritems(uno(fixed, {})):
        direction = PortDirection.input_
        if name.startswith('out:'):
            name = name[4:]
            direction = PortDirection.output
        matched = _reprog_bit.match(name)
        port_name, index = matched.group('name', 'index')
        index = None if index is None else int(index)
        port = mod_top.ports.get(port_name)
        if port is None:
            raise PRGAAPIError("Port '{}' not found in module '{}'"
                    .format(port_name, mod_top.name))
        elif port.direction is not direction:
            raise PRGAAPIError("Direction mismatch: port '{}' is {} in behavioral model but {} in IO bindings"
                    .format(port_name, port.direction.name, direction))
        elif index is None and port.low is not None:
            raise PRGAAPIError("Port '{}' is a bus and requires an index"
                    .format(port_name))
        elif index is not None and (port.low is None or index < port.low or index >= port.high):
            raise PRGAAPIError("Bit index '{}' is not in port '{}'"
                    .format(index, port_name))
        try:
            if assignments[x][y][0][subblock] is not None or assignments[x][y][1][subblock] is not None:
                raise PRGAAPIError("Conflicting assignment at ({}, {}, {})"
                        .format(x, y, subblock))
            assignments[x][y][port.direction.case(0, 1)][subblock] = name
            processed[port.direction.case("", "out:") + name] = x, y, subblock
        except (IndexError, TypeError):
            raise PRGAAPIError("Cannot assign port '{}' to ({}, {}, {})"
                    .format(name, x, y, subblock))
    # assign IOs
    next_io = {d: None for d in PortDirection}
    for port_name, port in iteritems(mod_top.ports):
        key = port.direction.case("", "out:") + port_name
        if port.low is None:
            if key in processed:
                continue
            io = next_io[port.direction] = _find_next_available_io(assignments,
                    next_io[port.direction], port.direction)
            if io is None:
                raise PRGAAPIError("Ran out of IOs when assigning '{}'".format(port_name))
            x, y, subblock = io
            assignments[x][y][port.direction.case(0, 1)][subblock] = key
            processed[key] = io
        else:
            for i in range(port.low, port.high):
                bit_name = '{}[{}]'.format(key, i)
                if bit_name in processed:
                    continue
                io = next_io[port.direction] = _find_next_available_io(assignments,
                        next_io[port.direction], port.direction)
                if io is None:
                    raise PRGAAPIError("Ran out of IOs when assigning '{}'".format(bit_name))
                x, y, subblock = io
                assignments[x][y][port.direction.case(0, 1)][subblock] = bit_name
                processed[bit_name] = io
    return processed

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(
            description="IO assignment generator")
    
    parser.add_argument('context', type=argparse.FileType(OpenMode.rb),
            help="Pickled architecture context object")
    parser.add_argument('-o', '--output', type=str, dest="output",
            help="Generated IO assignments")
    parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
            help="Source file(s) for behavioral model")
    parser.add_argument('--model_top', type=str,
            help="Top-level module name of the behavioral model. Required if the model comprises multiple files/modules")
    parser.add_argument('-f', '--fix', type=str, dest="fixed",
            help="Partial assignments")

    args = parser.parse_args()
    enable_stdout_logging(__name__, logging.INFO)
    context = ArchitectureContext.unpickle(args.context)
    _logger.info("Architecture context parsed")
    assignments = iobind(context, find_verilog_top(args.model, args.model_top),
            parse_io_bindings(args.fixed) if args.fixed is not None else {})
    # print results
    ostream = sys.stdout if args.output is None else open(args.output, 'w')
    for name, (x, y, subblock) in iteritems(assignments):
        ostream.write("{} {} {} {}\n".format(name, x, y, subblock))
    _logger.info("Assignment generated. Bye")
