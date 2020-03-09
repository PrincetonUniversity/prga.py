# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.netlist.net.common import PortDirection
from prga.exception import PRGAAPIError
from prga.util import Object, uno

from hdlparse.verilog_parser import VerilogExtractor as Vex
import re

_reprog_width = re.compile('^.*?\[\s*(?P<start>\d+)\s*:\s*(?P<end>\d+)\s*\].*?$')

__all__ = ['find_verilog_top', 'parse_io_bindings', 'parse_parameters']

class VerilogPort(Object):
    """A port of a Verilog module.

    Args:
        name (:obj:`str`): Name of the connection
        direction (`PortDirection`): Direction of this port
        low (:obj:`int`): LSB
        high (:obj:`int`): MSB
    """

    __slots__ = ['name', 'direction', 'low', 'high']
    def __init__(self, name, direction, low = None, high = None):
        self.name = name
        self.direction = direction
        self.low = low
        self.high = high

class VerilogModule(Object):
    """A Verilog module.

    Args:
        name (:obj:`str`): Name of the module
        ports (:obj:`Mapping` [:obj:`str`, `VerilogPort` ]): Mapping from port names to ports
        parameters (:obj:`Mapping` [:obj:`str`, :obj:`str` ]): Parameters for this module
    """

    __slots__ = ['name', 'ports', 'parameters']
    def __init__(self, name, ports, parameters = None):
        self.name = name
        self.ports = ports
        self.parameters = uno(parameters, {})

def find_verilog_top(files, top = None):
    """Find and parse the top-level module in a list of Verilog files.

    Args:
        files (:obj:`Sequence` [:obj:`str` ]): Verilog files
        top (:obj:`str`): the name of the top-level module if there are more than one modules in the Verilog
            files

    Returns:
        `VerilogModule`:
    """
    mods = {x.name : x for f in files for x in Vex().extract_objects(f)}
    mod = next(iter(itervalues(mods)))
    if len(mods) > 1:
        if top is not None:
            try:
                mod = mods[top]
            except KeyError:
                raise PRGAAPIError("Module '{}' is not found in the file(s)")
        else:
            raise PRGAAPIError('Multiple modules found in the file(s) but no top is specified')
    ports = {}
    for port in mod.ports:
        matched = _reprog_width.match(port.data_type)
        direction = port.mode.strip()
        if direction == 'input':
            direction = PortDirection.input_
        elif direction == 'output':
            direction = PortDirection.output
        else:
            raise PRGAAPIError("Unknown port direction '{}'".format(direction))
        low, high = None, None
        matched = _reprog_width.match(port.data_type)
        if matched is not None:
            start, end = map(int, matched.group('start', 'end'))
            if start > end:
                low, high = end, start + 1
            elif end > start:
                low, high = start, end + 1
            else:
                low, high = start, start + 1
        ports[port.name] = VerilogPort(port.name, direction, low, high)
    return VerilogModule(mod.name, ports)

def parse_io_bindings(file_):
    """Parse the IO binding constraint file.

    Args:
        io_bindings (:obj:`str`):

    Returns:
        :obj:`Mapping` [:obj:`str` ], :obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int`]: Mapping from
           port name in the behavioral model to \(x, y, subblock\)
    """
    io_bindings = {}
    for line in open(file_):
        line = line.split('#')[0].strip()
        if line == '':
            continue
        name, x, y, subblock = line.split()
        io_bindings[name] = tuple(map(int, (x, y, subblock)))
    return io_bindings

def parse_parameters(parameters):
    """Parse the parameters defined via command-line arguments.

    Args:
        parameters (:obj:`list` [:obj:`str` ]): a list of 'PARAMETER=VALUE' strings

    Returns:
        :obj:`dict`: a mapping from parameter name to value
    """
    mapping = {}
    for p in parameters:
        k, v = p.split('=')
        mapping[k] = v
    return mapping
