# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Dimension, Direction, Orientation
from prga.arch.net.common import PortDirection
from prga.arch.routing.common import SegmentBridgeID, SegmentBridgeType
from prga.util import Abstract

from abc import abstractmethod
from itertools import product

__all__ = ['ConnectionBoxLibraryDelegate', 'cboxify', 'netify_tile'] #, 'cboxify_double_sided']

# ----------------------------------------------------------------------------
# -- Connection Box Library Delegate -----------------------------------------
# ----------------------------------------------------------------------------
class ConnectionBoxLibraryDelegate(Abstract):
    """Connection box library supplying connection box modules for instantiation."""

    @abstractmethod
    def get_cbox(self, block, orientation, position = None, channel = (0, 0)):
        """Get a single-sided connection box module.

        Args:
            block (`AbstractBlock`):
            orientation (`Orientation`):
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            channal (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
        """
        raise NotImplementedError

    @abstractmethod
    def get_cbox_double_sided(self, dimension,
            block_ne = None, position_ne = None, block_sw = None, position_sw = None):
        """Get a double-sided connection box module.

        Args:
            dimension (`Dimension`): Dimension of the connectio box
            block_ne (`AbstractBlock` or ``None``): Block to the north of this connection box if ``dimension`` is
                horizontal, or block to the east of this connection box if ``dimension`` is vertical
            position_ne (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of this connection box relative to
                ``block_ne``
            block_sw (`AbstractBlock` or ``None``): Block to the south of this connection box if ``dimension`` is
                horizontal, or block to the west of this connection box if ``dimension`` is vertical
            position_sw (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of this connection box relative to
                ``block_sw``
        """
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Algorithms for Instantiating Connection Boxes in Tiles ------------------
# ----------------------------------------------------------------------------
def cboxify(lib, tile, orientation = Orientation.auto):
    """Create and instantiate single-sided connection boxes in ``tile``.

    Args:
        lib (`ConnectionBoxLibraryDelegate`):
        tile (`Tile`):
        orientation (`Orientation`): If the block instantiated in ``tile`` is an IO block with auto-oriented
            ports, orientation is required
    """
    if orientation is Orientation.auto:
        if tile.block.is_io_block:
            raise PRGAInternalError("Non-'Orientation.auto' value is required for IO blocks.")
        # horizontal
        for dir_ in Direction:
            x = dir_.switch(0, tile.width - 1)
            ori = Orientation.compose(Dimension.x, dir_)
            for y in range(tile.height):
                tile.instantiate_cbox(lib.get_cbox(tile.block, ori, (x, y), (dir_.switch(0, -1), 0)), ori, (x, y))
        # vertical
        for dir_ in Direction:
            y = dir_.switch(0, tile.height - 1)
            ori = Orientation.compose(Dimension.y, dir_)
            for x in range(tile.width):
                tile.instantiate_cbox(lib.get_cbox(tile.block, ori, (x, y), (0, dir_.switch(0, -1))), ori, (x, y))
    elif orientation.dimension.is_x:
        x = orientation.direction.switch(tile.width - 1, 0)
        for y in range(tile.height):
            tile.instantiate_cbox(lib.get_cbox(tile.block, orientation, (x, y),
                (orientation.direction.switch(0, -1), 0)), orientation, (x, y))
    else:
        y = orientation.direction.switch(tile.height - 1, 0)
        for x in range(tile.width):
            tile.instantiate_cbox(lib.get_cbox(tile.block, orientation, (x, y),
                (0, orientation.direction.switch(0, -1))), orientation, (x, y))

# ----------------------------------------------------------------------------
# -- Algorithms for Exposing Ports and Connect Nets in Tiles -----------------
# ----------------------------------------------------------------------------
def netify_tile(tile):
    """Expose ports and connect nets in tile.

    Args:
        tile (`Tile`):
    """
    for orientation, x, y in product(iter(Orientation), range(tile.width), range(tile.height)):
        if orientation.switch(
                north = y != tile.height - 1,
                east = x != tile.width - 1,
                south = y != 0,
                west = x != 0,
                auto = True):
            continue
        cboxinst = tile.cbox_instances.get( ((x, y), orientation.dimension.perpendicular), None )
        if cboxinst is None:
            continue
        for node, boxpin in iteritems(cboxinst.all_nodes):
            if node.node_type.is_blockport_bridge:
                port = tile.block.ports.get(node.prototype.name, None)
                if (port is None or port.position + node.position != (0, 0) or
                        port.orientation not in (Orientation.auto, orientation)):
                    continue
                blockpin = tile.block_instances[node.subblock].all_pins[port.name]
                if port.direction.is_input:
                    blockpin.source = boxpin
                else:
                    boxpin.source = blockpin
            elif node.node_type.is_segment_bridge:
                if node.bridge_type.is_cboxin:
                    boxpin.source = tile.get_or_create_node(
                            boxpin.node_id.to_bridge_id(bridge_type = SegmentBridgeType.array_regular),
                            PortDirection.input_)
                elif node.bridge_type.is_cboxout:
                    tile.get_or_create_node(
                            boxpin.node_id.to_bridge_id(bridge_type = SegmentBridgeType.array_cboxout),
                            PortDirection.output).source = boxpin
