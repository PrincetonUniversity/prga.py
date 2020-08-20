# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .util import find_verilog_top, parse_io_bindings, create_argparser, docstring_from_argparser
from ..netlist.net.common import PortDirection
from ..core.context import Context
from ..util import enable_stdout_logging, uno
from ..exception import PRGAAPIError

from itertools import product

import re, sys, logging

_logger = logging.getLogger(__name__)
_reprog_bit = re.compile('^(?P<name>.*?)(?:\[(?P<index>\d+)\])?$')

__all__ = ['iobind']

# Argument parser
import argparse
_parser = create_argparser(__name__, description="IO assignment generator")

_parser.add_argument('summary', type=argparse.FileType(OpenMode.rb),
        help="Pickled context or summary object")
_parser.add_argument('-o', '--output', type=str, dest="output",
        help="Generated IO assignments")
_parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
        help="Source file(s) for behavioral model")
_parser.add_argument('--model_top', type=str,
        help="Top-level module name of the behavioral model. Required if the model comprises multiple files/modules")
_parser.add_argument('-f', '--fix', type=str, dest="fixed",
        help="Partial assignments")

# update docstring
__doc__ = docstring_from_argparser(_parser)

def iobind(summary, mod_top, fixed = None):
    """Generate IO assignment.

    Args:
        summary (`ContextSummary`): The architecture context of the custom FPGA
        mod_top (`VerilogModule`): Top-level module of target design
        fixed (:obj:`Mapping` [:obj:`str`, :obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int` ]]): Manually assigned IOs
    """
    # prepare assignment map
    available = {PortDirection.input_: set(), PortDirection.output: set()}
    for iotype, (x, y), subtile in summary.ios:
        available[iotype.case(PortDirection.input_, PortDirection.output)].add( (x, y, subtile) )
    assigned = {}   # port -> io
    # process fixed assignments
    for name, assignment in iteritems(uno(fixed, {})):
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
        elif index is None and (port.low is not None and port.high - port.low > 1):
            raise PRGAAPIError("Port '{}' is a bus and requires an index"
                    .format(port_name))
        elif index is not None and (port.low is None or index < port.low or index >= port.high):
            raise PRGAAPIError("Bit index '{}' is not in port '{}'"
                    .format(index, port_name))
        elif not assignment in available[port.direction]:
            raise PRGAAPIError("Conflicting or invalid assignment at ({}, {}, {})"
                    .format(*assignment))
        available[port.direction].remove( assignment )
        available[port.direction.opposite].discard( assignment )
        assigned[port.direction.case("", "out:") + name] = assignment
    # assign IOs
    for port_name, port in iteritems(mod_top.ports):
        key = port.direction.case("", "out:") + port_name
        if port.low is None or port.high - port.low == 1:
            if key in assigned:
                continue
            try:
                assignment = available[port.direction].pop()
            except KeyError:
                raise PRGAAPIError("Ran out of IOs when assigning '{}'".format(port_name))
            available[port.direction.opposite].discard( assignment )
            assigned[key] = assignment
        else:
            for i in range(port.low, port.high):
                bit_name = '{}[{}]'.format(key, i)
                if bit_name in assigned:
                    continue
                try:
                    assignment = available[port.direction].pop()
                except KeyError:
                    raise PRGAAPIError("Ran out of IOs when assigning '{}'".format(bit_name))
                available[port.direction.opposite].discard( assignment )
                assigned[bit_name] = assignment
    return assigned

if __name__ == "__main__":
    args = _parser.parse_args()
    enable_stdout_logging(__name__, logging.INFO)
    summary = Context.unpickle(args.summary)
    if isinstance(summary, Context):
        summary = summary.summary
    _logger.info("Architecture context summary parsed")
    assignments = iobind(summary, find_verilog_top(args.model, args.model_top),
            parse_io_bindings(args.fixed) if args.fixed is not None else {})
    # print results
    ostream = sys.stdout if args.output is None else open(args.output, 'w')
    for name, (x, y, subtile) in iteritems(assignments):
        ostream.write("{} {} {} {}\n".format(name, x, y, subtile))
    _logger.info("Assignment generated. Bye")
