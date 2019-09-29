# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Direction, Orientation, Position
from prga.arch.routing.common import SegmentPrototype, SegmentBridgeType, SegmentBridgeID, BlockPortID
from prga.util import uno
from prga.exception import PRGAInternalError

from math import ceil
from collections import namedtuple
from itertools import product

__all__ = ['BlockPortFCValue', 'BlockFCValue', 'populate_connection_box', 'generate_fc']

# ----------------------------------------------------------------------------
# -- Block FC ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class BlockPortFCValue(namedtuple('BlockPortFCValue', 'default overrides')):
    """A named tuple used for defining FC values for a specific block port.

    Args:
        default (:obj:`int` or :obj:`float`): the default FC value for this port
        overrides (:obj:`Mapping` [:obj:`str`, :obj:`int` or :obj:`float` ]): the FC value for a
            specific segment type
    """

    def __new__(cls, default, overrides = None):
        return super(BlockPortFCValue, cls).__new__(cls, default, uno(overrides, {}))

    @property
    def default(self):
        """:obj:`int` or :obj:`float`: Default FC value for this block port."""
        return super(BlockPortFCValue, self).default

    @property
    def overrides(self):
        """:obj:`Mapping` [:obj:`str`, :obj:`int` or :obj:`float` ]): the FC value for a specific segment type."""
        return super(BlockPortFCValue, self).overrides

    def segment_fc(self, segment, all_sections = False):
        """Get the FC value for a specific segment.

        Args:
            segment (`SegmentPrototype`):
            all_sections (:obj:`bool`): if all sections of a segment longer than 1 should be taken into consideration

        Returns:
            :obj:`int`: the calculated FC value
        """
        multiplier = segment.length if all_sections else 1
        fc = self.overrides.get(segment.name, self.default)
        if isinstance(fc, int):
            if fc < 0 or fc >= segment.width:
                raise PRGAInternalError("Invalid FC value ({}) for segment '{}'".format(fc, segment.name))
            return fc * multiplier
        elif isinstance(fc, float):
            if fc < 0 or fc > 1:
                raise PRGAInternalError("Invalid FC value ({}) for segment '{}'".format(fc, segment.name))
            return int(ceil(fc * segment.width * multiplier))
        else:
            raise PRGAInternalError("Invalid FC value ({}) for segment '{}'".format(fc, segment.name))

class BlockFCValue(namedtuple('BlockFCValue', 'default_in default_out overrides')):
    """A named tuple used for defining FC values for a specific block.

    Args:
        default_in (`BlockPortFCValue`): the default FC value for all input ports
        default_out (`BlockPortFCValue`): the default FC value for all output ports. Same as the default value for
            input ports if not set
        overrides (:obj:`Mapping` [:obj:`str`, `BlockPortFCValue` ]): the FC value for a specific segment type
    """
    def __new__(cls, default_in, default_out = None, overrides = None):
        return super(BlockFCValue, cls).__new__(cls, default_in,
                uno(default_out, default_in),
                uno(overrides, {}))

    def port_fc(self, port, segment, all_sections = False):
        """Get the FC value for a specific port and a specific segment.

        Args:
            port (`AbstractBlockPort`): 
            segment (`SegmentPrototype`):
            all_sections (:obj:`bool`): if all sections of a segment longer than 1 should be taken into consideration

        Returns:
            :obj:`int`: the calculated FC value
        """
        return self.overrides.get(port.name, port.direction.switch(self.default_in, self.default_out)).segment_fc(
                segment, all_sections)

# ----------------------------------------------------------------------------
# -- Algorithms for connection boxes -----------------------------------------
# ----------------------------------------------------------------------------
def populate_connection_box(box, segments, block, orientation, position = None, channel = (0, 0)):
    """Populate connection box.

    Args:
        box (`ConnectionBox`):
        segments (:obj:`Sequence` [`SegmentPrototype` ]):
        block (`AbstractBlock`):
        orientation (`Orientation`):
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): position of the ports in ``block`` that are connected by
            this cbox. This argument can be omitted if ``block`` is 1x1
        channel (:obj:`tuple` [:obj:`int`, :obj:`int` ]): position of the routing channel relative to this cbox
    """
    if orientation.dimension.perpendicular is not box.dimension:
        raise PRGAInternalError("Connection box '{}' is {} and cannot be populated for '{}'"
                .format(box, box.dimension.switch("horizontal", "vertical"), orientation))
    orientation, position = block._validate_orientation_and_position(orientation, position)
    channel = Position(*channel)
    # 1. segment bridges
    for sgmt, direction in product(iter(segments), iter(Direction)):
        # 1.1 output segment bridge
        box.get_or_create_node(SegmentBridgeID(channel, sgmt, Orientation.compose(box.dimension, direction),
            0, SegmentBridgeType.cboxout))
        # 1.2 input segment bridge
        for section in range(sgmt.length):
            box.get_or_create_node(SegmentBridgeID(channel, sgmt, Orientation.compose(box.dimension, direction),
                section, SegmentBridgeType.cboxin))
    # 2. block port bridges
    # channel position relative to block
    pos_channel_rel_to_block = position + orientation.switch(
            north = (0, 0), east = (0, 0), south = (0, -1), west = (-1, 0))
    # block position relative to cbox
    pos_block_rel_to_cbox = channel - pos_channel_rel_to_block
    for port in itervalues(block.ports):
        if port.is_clock or not (port.position == position and port.orientation in (orientation, Orientation.auto)):
            continue
        for subblock in range(block.capacity):
            box.get_or_create_node(BlockPortID(pos_block_rel_to_cbox, port, subblock))

def generate_fc(box, segments, block, orientation, fc, position = None, channel = (0, 0)): 
    """Add port-segment connections using FC values.

    Args:
        box (`AbstractConnectionBox`):
        segments (:obj:`Sequence` [`SegmentPrototype` ]):
        block (`AbstractBlock`):
        orientation (`Orientation`):
        fc (`BlockFCValue`):
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): position of the ports in ``block`` that are connected by
            this cbox. This argument can be omitted if ``block`` is 1x1
        channel (:obj:`tuple` [:obj:`int`, :obj:`int` ]): position of the routing channel relative to this cbox
    """
    if orientation.dimension.perpendicular is not box.dimension:
        raise PRGAInternalError("Connection box '{}' is {} and cannot be populated for '{}'"
                .format(box, box.dimension.switch("horizontal", "vertical"), orientation))
    orientation, position = block._validate_orientation_and_position(orientation, position)
    channel = Position(*channel)
    # channel position relative to block
    pos_channel_rel_to_block = position + orientation.switch(
            north = (0, 0), east = (0, 0), south = (0, -1), west = (-1, 0))
    # block position relative to cbox
    pos_block_rel_to_cbox = channel - pos_channel_rel_to_block
    # start generation
    iti = [0 for _ in segments]     # input-to-track index
    oti = [0 for _ in segments]     # output-to-track index
    for port in itervalues(block.ports):
        if port.is_clock or not (port.position == position and port.orientation in (orientation, Orientation.auto)):
            continue
        for sgmt_idx, sgmt in enumerate(segments):
            nc = fc.port_fc(port, sgmt, port.direction.is_input)  # number of connections
            if nc == 0:
                continue
            imax = port.direction.switch(sgmt.length * sgmt.width, sgmt.width)
            istep = max(1, imax // nc)                  # index step
            for _, port_idx, subblock in product(range(nc), range(port.width), range(block.capacity)):
                # get the section and track id to be connected
                section = port.direction.switch(iti[sgmt_idx] % sgmt.length, 0)
                track_idx = port.direction.switch(iti[sgmt_idx] // sgmt.length, oti[sgmt_idx])
                for sgmt_dir in iter(Direction):
                    port_node = BlockPortID(pos_block_rel_to_cbox, port, subblock)
                    sgmt_node = SegmentBridgeID(
                            channel,
                            sgmt,
                            Orientation.compose(box.dimension, sgmt_dir),
                            section,
                            port.direction.switch(SegmentBridgeType.cboxin, SegmentBridgeType.cboxout))
                    # get the bits
                    port_bus = box.ports.get(port_node)
                    sgmt_bus = box.ports.get(sgmt_node)
                    if port_bus is None or sgmt_bus is None:
                        continue
                    if port.direction.is_input:
                        box.connect(sgmt_bus[track_idx], port_bus[port_idx])
                    else:
                        box.connect(port_bus[port_idx], sgmt_bus[track_idx])
                ni = port.direction.switch(iti, oti)[sgmt_idx] + istep    # next index
                if istep > 1 and ni >= imax:
                    ni += 1
                port.direction.switch(iti, oti)[sgmt_idx] = ni % imax
