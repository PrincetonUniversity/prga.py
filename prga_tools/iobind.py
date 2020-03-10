# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.netlist.net.common import PortDirection
from prga.core.context import Context
from prga.util import enable_stdout_logging, uno
from prga.exception import PRGAAPIError

from .util import find_verilog_top, parse_io_bindings

from itertools import product

import re
import logging
import sys

_logger = logging.getLogger(__name__)
_reprog_bit = re.compile('^(?P<name>.*?)(?:\[(?P<index>\d+)\])?$')

__all__ = ['iobind']

def iobind(summary, mod_top, fixed = None):
    """Generate IO assignment.

    Args:
        summary (`ContextSummary`): The architecture context of the custom FPGA
        mod_top (`VerilogModule`): Top-level module of target design
        fixed (:obj:`Mapping` [:obj:`str`, :obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int` ]]): Manually assigned IOs
    """
    # prepare assignment map
    available = {PortDirection.input_: set(), PortDirection.output: set()}
    for iotype, (x, y), subblock in summary.ios:
        available[iotype.case(PortDirection.input_, PortDirection.output)].add( (x, y, subblock) )
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
        elif index is None and port.low is not None:
            raise PRGAAPIError("Port '{}' is a bus and requires an index"
                    .format(port_name))
        elif index is not None and (port.low is None or index < port.low or index >= port.high):
            raise PRGAAPIError("Bit index '{}' is not in port '{}'"
                    .format(index, port_name))
        elif not assignment in available[port.direction]:
            raise PRGAAPIError("Conflicting or invalid assignment at ({}, {}, {})"
                    .format(x, y, subblock))
        available[port.direction].remove( assignment )
        available[port.direction.opposite].discard( assignment )
        assigned[port.direction.case("", "out:") + name] = assignment
    # assign IOs
    for port_name, port in iteritems(mod_top.ports):
        key = port.direction.case("", "out:") + port_name
        if port.low is None:
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
    import argparse
    parser = argparse.ArgumentParser(
            description="IO assignment generator")
    
    parser.add_argument('summary', type=argparse.FileType(OpenMode.rb),
            help="Pickled context or summary object")
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
    summary = Context.unpickle(args.summary)
    if isinstance(summary, Context):
        summary = summary.summary
    _logger.info("Architecture context summary parsed")
    assignments = iobind(summary, find_verilog_top(args.model, args.model_top),
            parse_io_bindings(args.fixed) if args.fixed is not None else {})
    # print results
    ostream = sys.stdout if args.output is None else open(args.output, 'w')
    for name, (x, y, subblock) in iteritems(assignments):
        ostream.write("{} {} {} {}\n".format(name, x, y, subblock))
    _logger.info("Assignment generated. Bye")
