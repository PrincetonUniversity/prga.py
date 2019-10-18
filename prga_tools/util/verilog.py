# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.exception import PRGAAPIError

from hdlparse.verilog_parser import VerilogExtractor as Vex
from hdlparse.verilog_parser import VerilogModule

__all__ = ['find_verilog_top', 'parse_io_bindings', 'parse_parameters']

def find_verilog_top(files, top = None):
    """Find and parse the top-level module in a list of Verilog files.

    Args:
        files (:obj:`Sequence` [:obj:`str` ]): Verilog files
        top (:obj:`str`): the name of the top-level module if there are more than one modules in the Verilog
            files

    Returns:
        `VerilogModule
        <https://kevinpt.github.io/hdlparse/apidoc/hdlparse.html#hdlparse.verilog_parser.VerilogModule>`_:
    """
    mods = {x.name : x for f in files for x in Vex().extract_objects(f)}
    if top is not None:
        try:
            return mods[top]
        except KeyError:
            raise PRGAAPIError("Module '{}' is not found in the file(S)")
    elif len(mods) > 1:
        raise PRGAAPIError('Multiple modules found in the file(s) but no top is specified')
    else:
        return next(iter(itervalues(mods)))

def parse_io_bindings(file_):
    """Parse the IO binding constraint file.

    Args:
        io_bindings (:obj:`str`):

    Returns:
        :obj:`dict`: a mapping from \(x, y, subblock\) to pin name
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
