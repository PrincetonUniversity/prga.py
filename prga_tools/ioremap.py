# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.algorithm.util.array import get_hierarchical_tile
from prga.flow.context import ArchitectureContext
from prga.util import enable_stdout_logging
from prga.exception import PRGAAPIError

from prga_tools.util import parse_io_bindings

import sys
import lxml.etree as et
import re
import logging

_logger = logging.getLogger(__name__)
_reprog_instance = re.compile('^(?P<name>.*?)(?P<index>\[\d+\])$')

__all__ = ['ioremap']

class _RemapTarget(object):
    """``ParserTarget`` to be used by ``etree.XMLParser``.
    
    Args:
        context (`ArchitectureContext`):
        output (:obj:`str` or file-like object):
        io_bindings (:obj:`Mapping` [:obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int`], :obj:`str` ]): Mapping from
            \(x, y, subblock\) to port name in the behavioral model
    """

    def __init__(self, context, output, io_bindings):
        self.context = context
        self.io_bindings = io_bindings
        if isinstance(output, str):
            output = open(output, 'w')
        self.xmlfile = et.xmlfile(output)
        self.stack = []
        self.filectx = None
        self.remapping = None

    def start(self, tag, attrs, nsmap=None):
        if self.filectx is None:
            self.filectx = self.xmlfile.__enter__()   # we have to use context manager manually
        while tag == 'block' and len(self.stack) == 1:
            mapped = io_bindings.get(attrs['name'])
            if mapped is None:
                break
            x, y, subblock = mapped
            tile = get_hierarchical_tile(self.context.top, (x, y))
            if tile is None:
                break
            tile = tile[-1].model
            if not tile.block.module_class.is_io_block or subblock < 0 or subblock >= tile.capacity:
                raise PRGAAPIError("No IO block found at position ({}, {}, {})"
                        .format(x, y, subblock))
            matched = _reprog_instance.match(attrs['instance'])
            old_tile = context.tiles[matched.group('name')]
            if old_tile.block is not tile.block:
                raise PRGAAPIError("Tile '{}' at position ({}, {}) is not compatible with tile '{}'"
                        .format(tile.name, x, y, old_tile.name))
            attrs['instance'] = tile.name + matched.group('index')
            self.remapping = (old_tile.name, tile.name)
            break
        ctx = self.filectx.element(tag, attrs)
        self.stack.append( (tag, ctx) )
        ctx.__enter__()

    def end(self, tag):
        expected_tag, ctx = self.stack.pop()
        if len(self.stack) == 1:
            self.remapping = None
        if expected_tag != tag:
            raise ValueError("Closing tag mismatches with starting tag")
        ctx.__exit__(*sys.exc_info())

    def data(self, data):
        if self.remapping is not None:
            pat, sub = self.remapping
            data = data.replace(pat, sub)
        self.filectx.write(data)

    def close(self):
        if not self.filectx or self.stack:
            raise ValueError("Unexpected end of file")
        self.xmlfile.__exit__(*sys.exc_info())
        self.filectx = None

def ioremap(context, input_, output, io_bindings):
    """Remap io tiles.

    Args:
        context (`ArchitectureContext`):
        input_ (:obj:`str` or file-like object):
        output (:obj:`str` or file-like object):
        io_bindings (:obj:`Mapping` [:obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int`], :obj:`str` ]): Mapping from
            \(x, y, subblock\) to port name in the behavioral model
    """
    et.parse(input_, parser = et.XMLParser(target = _RemapTarget(context, output, io_bindings)))

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
            description="VPR's packing result remapper")
    
    parser.add_argument('context', type=argparse.FileType(OpenMode.rb),
            help="Pickled architecture context object")
    parser.add_argument('io', type=str,
            help="IO assignment constraint")
    parser.add_argument('input', type=argparse.FileType(OpenMode.rb),
            help="DESIGN.net: packing result produced by VPR")
    parser.add_argument('output', type=argparse.FileType(OpenMode.wb),
            help="OUTPUT.net: output. Remapped packing result")

    args = parser.parse_args()
    enable_stdout_logging(__name__, logging.INFO)
    context = ArchitectureContext.unpickle(args.context)
    io_bindings = parse_io_bindings(args.io)
    _logger.info("Architecture context parsed")
    ioremap(context, args.input, args.output, io_bindings) 
    _logger.info("Remappig done. Bye")
