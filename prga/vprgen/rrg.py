# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position
from prga.flow.util import iter_all_tiles
from prga.algorithm.util.hierarchy import hierarchical_position
from prga.algorithm.util.array import get_hierarchical_tile

from itertools import product

__all__ = ['vpr_rrg_xml']

# ----------------------------------------------------------------------------
# -- Helper Class for Generating VPR's Routing Resource Graph XML ------------
# ----------------------------------------------------------------------------
class _VPRRoutingResourceGraph(object):
    """Helper class for generating VPR's routing resource graph XML.

    Args:
        context (`BaseArchitectureContext`):
    """

    def __init__(self, context):
        self.channel_width = 2 * sum(segment.width for segment in itervalues(context.segments))
        self.segment_id = {segment.name: i for i, segment in enumerate(itervalues(context.segments))}
        self.block_id = {}
        self.block_pin_num = {}
        self.pin_ptc = {}
        for i, tile in enumerate(iter_all_tiles(context)):
            self.block_id[tile.name] = i + 1
            pin_ptc = self.pin_ptc[tile.name] = {}
            block_pin_num = 0
            for port in itervalues(tile.block.ports):
                pin_ptc[port.name] = block_pin_num
                block_pin_num += port.width
            self.block_pin_num[tile.name] = block_pin_num

# ----------------------------------------------------------------------------
# -- Generate Full VPR Routing Resource Graph XML ----------------------------
# ----------------------------------------------------------------------------
def vpr_rrg_xml(xmlgen, context):
    """Generate full VPR's routing resource graph XML.

    Args:
        xmlgen (`XMLGenerator`):
        context (`BaseArchitectureContext`):
    """
    rrg = _VPRRoutingResourceGraph(context)
    with xmlgen.element('rr_graph'):
        # channels
        with xmlgen.element('channels'):
            xmlgen.element_leaf('channel', {
                'chan_width_max':   str(rrg.channel_width),
                'x_min':            str(rrg.channel_width),
                'y_min':            str(rrg.channel_width),
                'x_max':            str(rrg.channel_width),
                'y_max':            str(rrg.channel_width),
                })
            for x in range(context.top.width):
                xmlgen.element_leaf('y_list', {'index': str(x), 'info': str(rrg.channel_width)})
            for y in range(context.top.height):
                xmlgen.element_leaf('x_list', {'index': str(y), 'info': str(rrg.channel_width)})
        # switches: fake
        with xmlgen.element('switches'):
            with xmlgen.element('switch', {
                'id': '0',
                'type': 'mux',
                'name': 'default',
                }):
                xmlgen.element_leaf('timing', {
                    'R': '0.0',
                    'Cin': '0.0',
                    'Cout': '0.0',
                    'Tdel': '1e-11',
                    })
                xmlgen.element_leaf('sizing', {
                    'mux_trans_size': '0.0',
                    'buf_size': '0.0',
                    })
        # segments
        with xmlgen.element('segments'):
            for segment in itervalues(context.segments):
                with xmlgen.element('segment', {
                    'name': segment.name,
                    'id': rrg.segment_id[segment.name],
                    }):
                    xmlgen.element_leaf('timing', {
                        'R_per_meter': "0.0",
                        'C_per_meter': "0.0",
                        })
        # block types
        with xmlgen.element('block_types'):
            xmlgen.element_leaf('block_type', {
                'id': '0',
                'name': 'EMPTY',
                'width': '1',
                'height': '1',
                })
            for tile in iter_all_tiles(context):
                with xmlgen.element('block_type', {
                    'id': str(rrg.block_id[tile.name]),
                    'name': tile.name,
                    'width': str(tile.width),
                    'height': str(tile.height),
                    }):
                    for subblock, port in product(range(tile.capacity), itervalues(tile.block.ports)):
                        for i in range(port.width):
                            with xmlgen.element('pin_class', {'type': port.direction.case('INPUT', 'OUTPUT')}):
                                xmlgen.element_leaf('pin', {'ptc': str(subblock * rrg.block_pin_num[tile.name] +
                                        rrg.pin_ptc[tile.name][port.name] + i)},
                                        '{}[{}].{}[{}]'.format(tile.name, subblock, port.name, i))
        # grid
        with xmlgen.element('grid'):
            for x, y in product(range(context.top.width), range(context.top.height)):
                tile = get_hierarchical_tile(context.top, (x, y))
                rootpos = Position(x, y) if tile is None else hierarchical_position(tile)
                xmlgen.element_leaf('grid_loc', {
                    'x': str(x),
                    'y': str(y),
                    'block_type_id': '0' if tile is None else str(rrg.block_id[tile[-1].model.name]),
                    'width_offset': str(x - rootpos.x),
                    'height_offset': str(y - rootpos.y),
                    })
