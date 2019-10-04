# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Dimension, Direction, Orientation
from prga.arch.net.common import PortDirection
from prga.arch.routing.common import SegmentBridgeID, SegmentBridgeType, BlockPortID
from prga.arch.array.port import ArrayExternalInputPort, ArrayExternalOutputPort
from prga.util import Abstract

from abc import abstractmethod, abstractproperty
from itertools import product

__all__ = ['ConnectionBoxLibraryDelegate', 'cboxify', 'netify_tile'] #, 'cboxify_double_sided']

# ----------------------------------------------------------------------------
# -- Connection Box Library Delegate -----------------------------------------
# ----------------------------------------------------------------------------
class ConnectionBoxLibraryDelegate(Abstract):
    """Connection box library supplying connection box modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractmethod
    def get_or_create_cbox(self, block, orientation, position = None, channel = (0, 0)):
        """Get a single-sided connection box module.

        Args:
            block (`AbstractBlock`):
            orientation (`Orientation`):
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            channal (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
        """
        raise NotImplementedError

    @abstractproperty
    def is_empty(self):
        """:obj:`bool`: Test if the library is empty."""
        raise NotImplementedError

    def get_or_create_cbox_double_sided(self, dimension,
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
        raise NotImplementedError("Double-sided connection box not supported yet""")

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
        if tile.block.module_class.is_io_block:
            raise PRGAInternalError("Non-'Orientation.auto' value is required for IO blocks.")
    # scan positions and orientations
    sides = set()
    for port in itervalues(tile.block.ports):
        if port.net_class.is_blockport:
            sides.add( (port.orientation, port.position) )
    # instantiate cboxes
    for ori, position in sides:
        if ori.is_auto:
            ori = orientation
        if orientation in (ori, Orientation.auto):
            tile.instantiate_cbox(lib.get_or_create_cbox(tile.block, ori, position,
                ori.case((0, 0), (0, 0), (0, -1), (-1, 0))), ori, position)

# ----------------------------------------------------------------------------
# -- Algorithms for Creating Ports and Connecting Nets in Tiles --------------
# ----------------------------------------------------------------------------
def netify_tile(tile):
    """Create ports and connect nets in tile.

    Args:
        tile (`Tile`):
    """
    for orientation, x, y in product(iter(Orientation), range(tile.width), range(tile.height)):
        if orientation.case(
                north = y != tile.height - 1,
                east = x != tile.width - 1,
                south = y != 0,
                west = x != 0,
                auto = True):
            continue
        cboxinst = tile.cbox_instances.get( ((x, y), orientation), None )
        if cboxinst is None:
            continue
        for boxpin in itervalues(cboxinst.all_nodes):
            node = boxpin.node
            if node.node_type.is_blockport_bridge:
                port = tile.block.ports.get(node.prototype.key, None)
                if (port is None or
                        port.orientation not in (Orientation.auto, orientation) or
                        node.position - port.position != (0, 0)):
                    # TODO: for block not positioned at (0, 0), create ports
                    continue
                blockpin = tile.block_instances[node.subblock].all_pins[port.key]
                if port.direction.is_input:
                    blockpin.source = boxpin
                else:
                    boxpin.source = blockpin
            elif node.node_type.is_segment_bridge:
                if node.bridge_type.is_cboxin:
                    boxpin.source = tile.get_or_create_node(
                            node.to_bridge_id(bridge_type = SegmentBridgeType.array_regular),
                            PortDirection.input_)
                elif node.bridge_type.is_cboxout:
                    tile.get_or_create_node(
                            node.to_bridge_id(bridge_type = SegmentBridgeType.array_cboxout),
                            PortDirection.output).source = boxpin
    # external ports
    for subblock, blkinst in iteritems(tile.block_instances):
        for pin in itervalues(blkinst.all_pins):
            if pin.net_class.is_io:
                if pin.direction.is_input:
                    pin.source = tile._add_port(ArrayExternalInputPort(tile,
                        BlockPortID((0, 0), pin.model, subblock)))
                else:
                    tile._add_port(ArrayExternalOutputPort(tile,
                        BlockPortID((0, 0), pin.model, subblock))).source = pin
            elif pin.net_class.is_global:
                pin.source = tile.get_or_create_global_input(pin.model.global_)
