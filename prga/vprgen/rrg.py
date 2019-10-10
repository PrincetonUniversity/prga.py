# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position, Dimension, Direction, Orientation
from prga.arch.routing.common import SegmentID, BlockPortID
from prga.arch.array.tile import Tile
from prga.flow.util import iter_all_tiles
from prga.algorithm.util.hierarchy import hierarchical_position
from prga.algorithm.util.array import get_hierarchical_tile

from prga.exception import PRGAInternalError

from itertools import product
from collections import OrderedDict

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
        self.context = context
        # segment
        self.segment_id = OrderedDict()             # segment name -> segment_id
        self.segment_ptc = {}                       # segment name -> PTC base
        self.segment_node_id_base = {}              # segment name -> node base in non-truncated channel
        self.segment_node_id_base_truncated = {}    # segment name -> node base in truncated channel
        ptc = 0
        segment_node_id_base = 0
        segment_node_id_base_truncated = 0
        for i, (name, segment) in enumerate(iteritems(context.segments)):
            self.segment_id[name] = i
            self.segment_ptc[name] = ptc
            ptc += 2 * segment.width * segment.length
            self.segment_node_id_base[name] = segment_node_id_base
            segment_node_id_base += segment.width
            self.segment_node_id_base_truncated[name] = segment_node_id_base_truncated
            segment_node_id_base_truncated += segment.width * segment.length
        self.channel_width = ptc
        self.channel_nodes = segment_node_id_base
        self.channel_nodes_truncated = segment_node_id_base_truncated
        # block
        self.block_type_id = OrderedDict()          # tile name -> block_type_id
        self.block_num_pins = {}                    # tile name -> total number of pins of thie block
        self.block_pin_ptc = {}                     # tile name, port name -> PTC base
        for i, tile in enumerate(iter_all_tiles(context)):
            self.block_type_id[tile.name] = i + 1
            block_pin_ptc = self.block_pin_ptc[tile.name] = OrderedDict()
            block_num_pins = 0
            for port in itervalues(tile.block.ports):
                if port.direction.is_input and not port.is_clock:
                    block_pin_ptc[port.name] = block_num_pins
                    block_num_pins += port.width
            for port in itervalues(tile.block.ports):
                if port.direction.is_output:
                    block_pin_ptc[port.name] = block_num_pins
                    block_num_pins += port.width
            for port in itervalues(tile.block.ports):
                if port.direction.is_input and port.is_clock:
                    block_pin_ptc[port.name] = block_num_pins
                    block_num_pins += port.width
            self.block_num_pins[tile.name] = block_num_pins

    def iter_tiles(self):
        self.grid = [[None for _ in range(self.context.top.height)] for _ in range(self.context.top.width)]
        for x, y in product(range(self.context.top.width), range(self.context.top.height)):
            tile = get_hierarchical_tile(self.context.top, (x, y))
            if tile is not None:
                rootpos = hierarchical_position(tile)
                if rootpos == (x, y):
                    self.grid[x][y] = tile[-1].model
                    yield (x, y), tile[-1].model, (0, 0)
                else:
                    self.grid[x][y] = Position(x, y) - rootpos
                    yield (x, y), tile[-1].model, self.grid[x][y]
            else:
                yield (x, y), None, (0, 0)

    def iter_nodes(self):
        # scan channel first
        # VPR node: CHANX. [x][y] -> node_id_base, consecutive channels to the left, ... to the right
        self.chanx_node_id_base = [[(None, 0, 0) for _ in range(self.context.top.height)]
                for _ in range(self.context.top.width)]
        for y in range(self.context.top.height - 1):
            startx = self.context.top.width
            for x in range(self.context.top.width):
                if not self.context.top.runs_channel((x, y), Dimension.x):  # no channel here
                    for xx in range(startx, x):
                        self.chanx_node_id_base[xx][y] = (0, xx - startx, x - 1 - xx)
                    startx = self.context.top.width
                elif x < startx:
                    startx = x
        # VPR node: CHANY. [x][y] -> node_id_base, consecutive channels from below, ... from above
        self.chany_node_id_base = [[(None, 0, 0) for _ in range(self.context.top.height)]
                for _ in range(self.context.top.width)]
        for x in range(self.context.top.width - 1):
            starty = self.context.top.height
            for y in range(self.context.top.height):
                if not self.context.top.runs_channel((x, y), Dimension.y):  # no channel here
                    for yy in range(starty, y):
                        self.chany_node_id_base[x][yy] = (0, yy - starty, y - 1 - yy)
                    starty = self.context.top.height
                elif y < starty:
                    starty = y
        # assign node ID bases and iterate through nodes
        self.num_nodes = 0
        # VPR node: SOURCE & SINK
        self.srcsink_node_id_base = [[None for _ in range(self.context.top.height)]
                for _ in range(self.context.top.width)]
        # VPR node: IPIN & OPIN
        self.iopin_node_id_base = [[None for _ in range(self.context.top.height)]
                for _ in range(self.context.top.width)]
        for x, y in product(range(self.context.top.width), range(self.context.top.height)):
            # block pin nodes
            tile = self.grid[x][y]
            if isinstance(tile, Tile):
                self.srcsink_node_id_base[x][y] = self.num_nodes
                for subblock, (name, ptc_base) in product(range(tile.capacity), iteritems(self.block_pin_ptc[tile.name])):
                    ptc_base += subblock * self.block_num_pins[tile.name]
                    port = tile.block.ports[name]
                    for i in range(port.width):
                        yield (self.num_nodes, port.direction.case('SINK', 'SOURCE'),
                                (x + port.position.x, y + port.position.y, ptc_base + i))
                        self.num_nodes += 1
                self.iopin_node_id_base[x][y] = self.num_nodes
                for subblock, (name, ptc_base) in product(range(tile.capacity), iteritems(self.block_pin_ptc[tile.name])):
                    ptc_base += subblock * self.block_num_pins[tile.name]
                    port = tile.block.ports[name]
                    for i in range(port.width):
                        ptc = subblock * self.block_num_pins[tile.name] + self.block_pin_ptc[tile.name][name] + i
                        yield (self.num_nodes, port.direction.case('IPIN', 'OPIN'),
                                (x + port.position.x, y + port.position.y, ptc_base + i,
                                    port.orientation if tile.orientation.is_auto else tile.orientation.opposite))
                        self.num_nodes += 1
            # channel nodes
            for dim in Dimension:
                node_id_base, before, after = dim.case(self.chanx_node_id_base, self.chany_node_id_base)[x][y]
                if node_id_base is not None:
                    for name, dir_ in product(self.segment_id, Direction):
                        segment = self.context.segments[name]
                        ori = Orientation.compose(dim, dir_)
                        for section, i in product(range(1 if dir_.case(before, after) > 0 else segment.length),
                                range(segment.width)):
                            remainder = ori.case(
                                    y - section + segment.length - 1,
                                    x - section + segment.length - 1,
                                    y + section,
                                    x + section) % segment.length
                            ptc = self.segment_ptc[name] + 2 * remainder * segment.width + i * 2 + dir_.case(0, 1)
                            yield (self.num_nodes,                                                      # node_id
                                    dim.case('CHANX', 'CHANY'),                                         # type
                                    (dir_.case('INC_DIR', 'DEC_DIR'),                                   # direction
                                    ori.case(x, x, x, x - min(before, segment.length - 1 - section)),   # xlow
                                    ori.case(x, x + min(after, segment.length - 1 - section), x, x),    # xhigh
                                    ori.case(y, y, y - min(before, segment.length - 1 - section), y),   # ylow
                                    ori.case(y + min(after, segment.length - 1 - section), y, y, y),    # yhigh
                                    ptc,                                                                # ptc
                                    self.segment_id[name]))                                             # segment_id
                            self.num_nodes += 1

    def get_tile(self, x, y):
        tile = self.grid[x][y]
        if isinstance(tile, Position):
            root = self.grid[x - tile.x][y - tile.y]
            return root, tile
        else:
            return tile, (0, 0)

    def calc_srcsink_id(self, tile, node, i):
        node_id_base = self.srcsink_node_id_base[node.position.x][node.position.y]
        return (node_id_base + self.block_num_pins[tile.name] * node.subblock + 
                self.block_pin_ptc[tile.name][node.prototype.name] + i)

    def calc_iopin_id(self, tile, node, i):
        node_id_base = self.iopin_node_id_base[node.position.x][node.position.y]
        return (node_id_base + self.block_num_pins[tile.name] * node.subblock + 
                self.block_pin_ptc[tile.name][node.prototype.name] + i)

    # def calc_track_id(self, node, i):
    #     (x, y), segment, orientation, section = node
    #     node_id_base, before, after = orientation.dimension.case(
    #             self.chanx_node_id_base, self.chany_node_id_base)[x][y]
    #     if node_id_base is None:
    #         raise PRGAInternalError("Node ID not assigned for node '{}'".format(node))
    #     elif section > 0 and orientation.direction.case(before, after):
    #         raise PRGAInternalError("Truncated segment found in consecutive routing channels: {}".format(node))
    #     segment_node_id_base = (self.segment_node_id_base if orientation.direction.case(before, after) else
    #             self.segment_node_id_base_truncated)[segment.name]
    #     return node_id_base + segment_node_id_base + i + orientation.direction.case(0,
    #             self.channel_nodes if before else self.channel_nodes_truncated)

    # def calc_track_ptc(self, node, i):
    #     (x, y), segment, orientation, section = node
    #     section = orientation.case(
    #             y - section - 1 + segment.length,
    #             x - section - 1 + segment.length, 
    #             y + section + 1,
    #             x + section + 1) % segment.length
    #     ptc_base = self.segment_ptc[segment.name]
    #     ptc_offset = 2 * (section * segment.width + i) + orientation.direction.case(1, 0)
    #     return ptc_base + ptc_offset

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
            for name, segment_id in iteritems(rrg.segment_id):
                with xmlgen.element('segment', {
                    'name': name,
                    'id': str(segment_id),
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
            for name, block_type_id in iteritems(rrg.block_type_id):
                tile = context.tiles[name]
                with xmlgen.element('block_type', {
                    'id': str(block_type_id),
                    'name': name,
                    'width': str(tile.width),
                    'height': str(tile.height),
                    }):
                    for subblock, (name, ptc_base) in product(range(tile.capacity),
                            iteritems(rrg.block_pin_ptc[tile.name])):
                        ptc_base += subblock * rrg.block_num_pins[tile.name]
                        port = tile.block.ports[name]
                        for i in range(port.width):
                            with xmlgen.element('pin_class', {'type': port.direction.case('INPUT', 'OUTPUT')}):
                                xmlgen.element_leaf('pin', {'ptc': str(ptc_base + i)},
                                        '{}[{}].{}[{}]'.format(tile.name, subblock, name, i)
                                        if tile.block.module_class.is_io_block else
                                        '{}.{}[{}]'.format(tile.name, name, i))
        # grid
        with xmlgen.element('grid'):
            for (x, y), tile, (xoffset, yoffset) in rrg.iter_tiles():
                xmlgen.element_leaf('grid_loc', {
                    'x': str(x),
                    'y': str(y),
                    'block_type_id': '0' if tile is None else str(rrg.block_type_id[tile.name]),
                    'width_offset': str(xoffset),
                    'height_offset': str(yoffset),
                    })
        # routing resource nodes
        with xmlgen.element('rr_nodes'):
            for node in rrg.iter_nodes():
                id_, type_, info = node
                if type_ in ('SOURCE', 'SINK'):
                    x, y, ptc = info
                    with xmlgen.element('node', {'id': str(id_), 'type': type_, 'capacity': '1'}):
                        xmlgen.element_leaf('loc', {'xlow': str(x), 'xhigh': str(x), 'ylow': str(y), 'yhigh': str(y),
                            'ptc': str(ptc)})
                        xmlgen.element_leaf('timing', {'R': '0', 'C': '0'})
                elif type_ in ('IPIN', 'OPIN'):
                    x, y, ptc, ori = info
                    with xmlgen.element('node', {'id': str(id_), 'type': type_, 'capacity': '1'}):
                        xmlgen.element_leaf('loc', {'xlow': str(x), 'xhigh': str(x), 'ylow': str(y), 'yhigh': str(y),
                            'side': ori.case('TOP', 'RIGHT', 'BOTTOM', 'LEFT'), 'ptc': str(ptc)})
                        xmlgen.element_leaf('timing', {'R': '0', 'C': '0'})
                elif type_ in ('CHANX', 'CHANY'):
                    dir_, xlow, xhigh, ylow, yhigh, ptc, segment_id = info
                    with xmlgen.element('node', {'id': str(id_), 'type': type_, 'capacity': '1', 'direction': dir_}):
                        xmlgen.element_leaf('loc', {'xlow': str(xlow), 'xhigh': str(xhigh),
                            'ylow': str(ylow), 'yhigh': str(yhigh), 'ptc': str(ptc)})
                        xmlgen.element_leaf('timing', {'R': '0', 'C': '0'})
                        xmlgen.element_leaf('segment', {'segment_id': str(segment_id)})
        # routing edges
        with xmlgen.element('rr_edges'):
            # source/sink <-> ipin/opin
            for x, y in product(range(context.top.width), range(context.top.height)):
                tile, (xx, yy) = rrg.get_tile(x, y)
                if tile is not None and xx == 0 and yy == 0:
                    for subblock, name in product(range(tile.capacity), rrg.block_pin_ptc[tile.name]):
                        port = tile.block.ports[name]
                        node = BlockPortID((x, y), port, subblock)
                        for i in range(port.width):
                            if port.direction.is_input:
                                xmlgen.element_leaf('edge', {
                                    'src_node': str(rrg.calc_iopin_id(tile, node, i)),
                                    'sink_node': str(rrg.calc_srcsink_id(tile, node, i)),
                                    'switch_id': '0',
                                    })
                            else:
                                xmlgen.element_leaf('edge', {
                                    'src_node': str(rrg.calc_srcsink_id(tile, node, i)),
                                    'sink_node': str(rrg.calc_iopin_id(tile, node, i)),
                                    'switch_id': '0',
                                    })
        xmlgen.element_leaf('num_nodes', {'v': str(rrg.num_nodes)})
