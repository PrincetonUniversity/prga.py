# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Orientation
from prga.arch.routing.common import SegmentPrototype, SegmentBridgeType, SegmentID, SegmentBridgeID
from prga.util import uno, ReadonlyMappingProxy, Object
from prga.exception import PRGAInternalError

from collections import namedtuple
from itertools import product

__all__ = ['SwitchBoxEnvironment', 'WiltonSwitchBoxPattern', 'populate_switch_box', 'generate_wilton']

# ----------------------------------------------------------------------------
# -- Switch Box Environment --------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchBoxEnvironment(namedtuple('SwitchBoxEnvironment', 'north east south west')):
    """Tuple used to define the environment of a switch box.

    Args:
        north (:obj:`bool`): if routing channel exists to the north of this box
        east (:obj:`bool`): if routing channel exists to the east of this box
        south (:obj:`bool`): if routing channel exists to the south of this box
        west (:obj:`bool`): if routing channel exists to the west of this box
    """
    def __new__(cls, north = True, east = True, south = True, west = True):
        return super(SwitchBoxEnvironment, cls).__new__(cls, north, east, south, west)

    def __getitem__(self, key):
        if isinstance(key, Orientation):
            return key.case(north = self.north, east = self.east,
                    south = self.south, west = self.west)
        else:
            return super(SwitchBoxEnvironment, self).__getitem__(key)

# ----------------------------------------------------------------------------
# -- Algorithms for switch boxes ---------------------------------------------
# ----------------------------------------------------------------------------
def _innode(segment, orientation, section = 0):
    return SegmentBridgeID(orientation.case((0, 0), (0, 0), (0, 1), (1, 0)),
            segment, orientation, section, SegmentBridgeType.sboxin_regular)

def _outnode(segment, orientation, section = 0):
    return SegmentID(orientation.case((0, 1), (1, 0), (0, 0), (0, 0)),
            segment, orientation, section)

def populate_switch_box(box, segments, env = SwitchBoxEnvironment(), drive_truncated = True):
    """Populate switch box.

    Args:
        box (`SwitchBox`):
        segments (:obj:`Sequence` [`SegmentPrototype` ]):
        env (`SwitchBoxEnvironment`):
        drive_truncated (:obj:`bool`): if truncated segments should be driven by this switch box
    """
    for sgmt, ori in product(iter(segments), iter(Orientation)):
        if ori.is_auto:
            continue
        if env[ori]:
            # 1 output segment driver
            driver = box.get_or_create_node(_outnode(sgmt, ori))
            # 2 truncated segment driver
            for section in range(1, sgmt.length if not env[ori.opposite] and drive_truncated else 1):
                box.get_or_create_node(_outnode(sgmt, ori, section))
            # 3 input bridges
            for section in range(sgmt.length):
                box.get_or_create_node(_innode(sgmt, ori.opposite, section))

class WiltonSwitchBoxPattern(Object):
    """Host of two prebuilt wilton switch box patterns."""

    _clockwise = ( 
            (Orientation.east, Orientation.south),
            (Orientation.south, Orientation.west),
            (Orientation.west, Orientation.north),
            (Orientation.north, Orientation.east),
            )

    _counterclockwise = (
            (Orientation.south, Orientation.east),
            (Orientation.east, Orientation.north),
            (Orientation.north, Orientation.west),
            (Orientation.west, Orientation.south),
            )

    classic = ReadonlyMappingProxy({
        # clockwise
        (Orientation.east, Orientation.south): 1,
        (Orientation.south, Orientation.west): 1,
        (Orientation.west, Orientation.north): -1,
        (Orientation.north, Orientation.east): 1,
        # counter-clockwise
        (Orientation.south, Orientation.east): -1,
        (Orientation.east, Orientation.north): 1,
        (Orientation.north, Orientation.west): 1,
        (Orientation.west, Orientation.south): 1,
        })

    cfoptimal = ReadonlyMappingProxy({
        # clockwise
        (Orientation.east, Orientation.south): 1,
        (Orientation.south, Orientation.west): 1,
        (Orientation.west, Orientation.north): 1,
        (Orientation.north, Orientation.east): -2,
        # counter-clockwise
        (Orientation.south, Orientation.east): 1,
        (Orientation.east, Orientation.north): 1,
        (Orientation.north, Orientation.west): 1,
        (Orientation.west, Orientation.south): -2,
        })

def generate_wilton(box, segments, pattern = None, cycle_free = False):
    """Generate a variation of Wilton switch block.

    Args:
        box (`SwitchBox`):
        segments (:obj:`Sequence` [`SegmentPrototype` ]):
        pattern (:obj:`Mapping` [:obj:`tuple` [`Orientation`, `Orientation` ], :obj:`int` ]): switch block pattern, a
            mapping from turns \(from_orientation, to_orientation\) to offsets. Note that U-turn and straight
            connection patterns will be ignored
        cycle_free (:obj:`bool`): If set, some connections are to be removed so the routing graph is acyclic
    """
    pattern = uno(pattern, WiltonSwitchBoxPattern.cfoptimal if cycle_free else WiltonSwitchBoxPattern.classic)
    # find all nodes
    inputs, outputs = {}, {}
    for ori in iter(Orientation):
        if ori.is_auto:
            continue
        inodes = inputs.setdefault(ori, [])
        onodes = outputs.setdefault(ori, [])
        for sgmt in segments:
            base = len(inodes)
            inodes.extend([] for idx in range(sgmt.width))
            onodes.extend([] for idx in range(sgmt.width))
            for section in range(sgmt.length):
                inode = box.all_nodes.get(_innode(sgmt, ori, section), None)
                if inode is not None:
                    for idx in range(sgmt.width):
                        inodes[base + idx].append(inode[idx])
                onode = box.all_nodes.get(_outnode(sgmt, ori, section), None)
                if onode is not None:
                    for idx in range(sgmt.width):
                        onodes[base + idx].append(onode[idx])
            # straight connections
            source = box.all_nodes.get(_innode(sgmt, ori, sgmt.length - 1), None)
            sink = box.all_nodes.get(_outnode(sgmt, ori, 0), None)
            if source is not None and sink is not None:
                box.connect(source, sink)
    # generate connections
    W = sum(sgmt.width for sgmt in segments)
    for turns in (WiltonSwitchBoxPattern._clockwise, WiltonSwitchBoxPattern._counterclockwise):
        logical_class_offset = 0
        for turn_id, (from_ori, to_ori) in enumerate(turns):
            track_offset = pattern.get((from_ori, to_ori), None)
            cycle_free_offset = logical_class_offset + track_offset
            if track_offset is None:
                raise PRGAInternalError("No offset given for {}-{} turn"
                        .format(from_ori.name, to_ori.name))
            assert W == len(inputs[from_ori])
            for i, inodes in enumerate(inputs[from_ori]):
                o = (W + i + track_offset) % W
                onodes = outputs[to_ori][o]
                if len(inodes) == 0 or len(onodes) == 0:
                    continue
                elif cycle_free and turn_id == 3 and o < cycle_free_offset:
                    continue
                box.connect(inodes, onodes, fully_connected = True)
            logical_class_offset += track_offset
