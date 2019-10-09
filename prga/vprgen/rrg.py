# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position, Dimension
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
        # channel width
        # segment
        self.segment_id = {}
        self.segment_node_id_offset = {}
        self.segment_ptc = {}
        channel_width = 0
        ptc = 0
        for i, (name, segment) in enumerate(iteritems(context.segments)):
            self.segment_id[name] = i
            self.segment_node_id_offset[name] = channel_width
            channel_width += 2 * segment.width
            self.segment_ptc[name] = ptc
            ptc += 2 * segment.width * segment.length
        self.channel_width = channel_width
        # block
        self.block_type_id = {}
        self.block_num_pins = {}
        self.block_pin_ptc = {}
        for i, tile in enumerate(iter_all_tiles(context)):
            self.block_type_id[tile.name] = i + 1
            block_pin_ptc = self.block_pin_ptc[tile.name] = {}
            block_num_pins = 0
            for port in itervalues(tile.block.ports):
                block_pin_ptc[port.name] = block_num_pins
                block_num_pins += port.width
            self.block_num_pins[tile.name] = block_num_pins
        # grid
        self.grid = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        # VPR node: SOURCE & SINK
        self.srcsink_node_id_base = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        # VPR node: IPIN & OPIN
        self.iopin_node_id_base = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        # VPR node: CHANX
        self.chanx_node_id_base = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        # VPR node: CHANY
        self.chany_node_id_base = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        node_id_base = 0
        for x, y in product(range(context.top.width), range(context.top.height)):
            # tile?
            tile = get_hierarchical_tile(context.top, (x, y))
            if tile is not None:
                rootpos = hierarchical_position(tile)
                if rootpos == (x, y):
                    self.grid[x][y] = tile[-1].model
                    num_pins = tile[-1].model.capacity * self.block_num_pins[tile[-1].model.name]
                    self.srcsink_node_id_base[x][y] = node_id_base
                    node_id_base += num_pins
                    self.iopin_node_id_base[x][y] = node_id_base
                    node_id_base += num_pins
                else:
                    self.grid[x][y] = Position(x, y) - rootpos
            # horizontal channel?
            if (x > 0 and x < context.top.width - 1 and y < context.top.height - 1 and
                    context.top.runs_channel((x, y), Dimension.x)):
                self.chanx_node_id_base[x][y] = node_id_base
                node_id_base += self.channel_width
            # vertical channel?
            if (y > 0 and x < context.top.width - 1 and y < context.top.height - 1 and
                    context.top.runs_channel((x, y), Dimension.y)):
                self.chany_node_id_base[x][y] = node_id_base
                node_id_base += self.channel_width
        self.num_nodes = node_id_base

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
    with xmlgen.element('rr_graph', {'num_nodes': rrg.num_nodes}):
        # channels
        with xmlgen.element('channels'):
            xmlgen.element_leaf('channel', {
                'chan_width_max':   str(rrg.channel_width),
                'x_min':            str(rrg.channel_width),
                'y_min':            str(rrg.channel_width),
                'x_max':            str(rrg.channel_width),
                'y_max':            str(rrg.channel_width),
                })
            for x in range(context.top.width - 1):
                xmlgen.element_leaf('y_list', {'index': str(x), 'info': str(rrg.channel_width)})
            for y in range(context.top.height - 1):
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
                    'id': str(rrg.block_type_id[tile.name]),
                    'name': tile.name,
                    'width': str(tile.width),
                    'height': str(tile.height),
                    }):
                    for subblock, port in product(range(tile.capacity), itervalues(tile.block.ports)):
                        for i in range(port.width):
                            with xmlgen.element('pin_class', {'type': port.direction.case('INPUT', 'OUTPUT')}):
                                xmlgen.element_leaf('pin', {'ptc': str(subblock * rrg.block_num_pins[tile.name] +
                                        rrg.block_pin_ptc[tile.name][port.name] + i)},
                                        '{}[{}].{}[{}]'.format(tile.name, subblock, port.name, i))
        # grid
        with xmlgen.element('grid'):
            for x, y in product(range(context.top.width), range(context.top.height)):
                tile = rrg.grid[x][y]
                attrs = {'x': str(x), 'y': str(y)}
                if tile is None:
                    attrs.update({'block_type_id': '0', 'width_offset': '0', 'height_offset': '0'})
                elif isinstance(tile, Position):
                    root = rrg.grid[x - tile.x][y - tile.y]
                    attrs.update({'block_type_id': str(rrg.block_type_id[root.name]),
                        'width_offset': str(tile.x), 'height_offset': str(tile.y)})
                else:
                    attrs.update({'block_type_id': str(rrg.block_type_id[tile.name]),
                        'width_offset': '0', 'height_offset': '0'})
                xmlgen.element_leaf('grid_loc', attrs)
        # routing resource nodes
        with xmlgen.element('rr_nodes'):
            for x, y in product(range(context.top.width), range(context.top.height)):
                tile = rrg.grid[x][y]
                if tile is None or isinstance(tile, Position):
                    continue
                # SOURCE & SINK
                for subblock, (name, port) in product(range(tile.capacity), iteritems(tile.block.ports)):
                    for i in range(port.width):
                        ptc = subblock * rrg.block_num_pins[tile.name] + rrg.block_pin_ptc[tile.name][name] + i
                        with xmlgen.element('node', {
                            'id': str(rrg.srcsink_node_id_base[x][y] + ptc),
                            'type': port.direction.case('SINK', 'SOURCE'),
                            'capacity': '1',
                            }):
                            xmlgen.element_leaf('loc', {
                                'xlow': str(x + port.position.x),
                                'xhigh': str(x + port.position.x),
                                'ylow': str(y + port.position.y),
                                'yhigh': str(y + port.position.y),
                                'ptc': ptc,
                                })
                            xmlgen.element_leaf('timing', {'R': '0', 'C': '0'})
                # IPIN & OPIN
                for subblock, (name, port) in product(range(tile.capacity), iteritems(tile.block.ports)):
                    for i in range(port.width):
                        ptc = subblock * rrg.block_num_pins[tile.name] + rrg.block_pin_ptc[tile.name][name] + i
                        with xmlgen.element('node', {
                            'id': str(rrg.iopin_node_id_base[x][y] + ptc),
                            'type': port.direction.case('IPIN', 'OPIN'),
                            'capacity': '1',
                            }):
                            xmlgen.element_leaf('loc', {
                                'xlow': str(x + port.position.x),
                                'xhigh': str(x + port.position.x),
                                'ylow': str(y + port.position.y),
                                'yhigh': str(y + port.position.y),
                                'ptc': ptc,
                                'side': port.orientation.case('TOP', 'RIGHT', 'BOTTOM', 'LEFT',
                                    tile.orientation.case('BOTTOM', 'LEFT', 'TOP', 'RIGHT', 'INVALID'))
                                })
                            xmlgen.element_leaf('timing', {'R': '0', 'C': '0'})
