# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.algorithm.design.cbox import generate_fc
from prga.algorithm.design.sbox import populate_switch_box, generate_wilton
from prga.algorithm.design.switch import switchify
from prga.algorithm.design.tile import cboxify, netify_tile
from prga.algorithm.design.array import sboxify, netify_array
from prga.flow.flow import AbstractPass
from prga.flow.util import analyze_hierarchy
from prga.util import uno, Object

from itertools import chain

__all__ = ['CompleteRoutingBox', 'CompleteSwitch', 'CompleteConnection']

# ----------------------------------------------------------------------------
# -- Create and Instantiate Routing Boxes ------------------------------------
# ----------------------------------------------------------------------------
class CompleteRoutingBox(Object, AbstractPass):
    """Create and instantiate connection & switch boxes.

    Args:
        default_fc (`BlockFCValue`): Default FC value used to generate connection box
        block_fc (:obj:`Mapping` [:obj:`str`, `BlockFCValue` ]): FC overrides for each block type
        cycle_free (:obj:`bool`): If set, cycle-free switch boxes will be used
    """

    __slots__ = ['default_fc', 'block_fc', 'cycle_free']
    def __init__(self, default_fc, block_fc = None, cycle_free = True):
        self.default_fc = default_fc
        self.block_fc = uno(block_fc, {})
        self.cycle_free = cycle_free

    @property
    def key(self):
        return "completion.routing"

    @property
    def passes_after_self(self):
        return ("completion.switch", "completion.connection", "rtl", "vpr", "config", "asicflow")

    def __process_array(self, context, array, segments):
        hierarchy = analyze_hierarchy(context)
        for module in itervalues(hierarchy[array.name]):
            if module.module_class.is_array:
                self.__process_array(context, module)
            elif module.module_class.is_tile:
                cboxify(context.connection_box_library, module, module.orientation.opposite)
                for (position, orientation), cbox in iteritems(module.cbox_instances):
                    if cbox.model.name in hierarchy[module.name]:
                        continue
                    generate_fc(cbox.model, segments, module.block, orientation,
                            self.block_fc.get(module.block.name, self.default_fc), module.capacity,
                            position, orientation.case((0, 0), (0, 0), (0, -1), (-1, 0)))
                    hierarchy.setdefault(cbox.model.name, {})
                    hierarchy[module.name][cbox.model.name] = cbox.model
        sboxify(context.switch_box_library, array)
        for sbox in itervalues(array.sbox_instances):
            if sbox.model.name in hierarchy[array.name]:
                continue
            generate_wilton(sbox.model, segments, cycle_free = self.cycle_free)
            hierarchy.setdefault(sbox.model.name, {})
            hierarchy[array.name][sbox.model.name] = sbox.model

    def run(self, context):
        self.__process_array(context, context.top, tuple(itervalues(context.segments)))

# ----------------------------------------------------------------------------
# -- Convert User-defined Connections to Switches ----------------------------
# ----------------------------------------------------------------------------
class CompleteSwitch(Object, AbstractPass):
    """Convert user-defined connections to switches."""

    @property
    def key(self):
        """Key of this pass."""
        return "completion.switch"

    @property
    def passes_after_self(self):
        """Passes that should be run after this pass."""
        return ("completion.connection", "rtl", "vpr", "config", "asicflow")

    def run(self, context):
        hierarchy = analyze_hierarchy(context)
        modules = list(chain(itervalues(context.clusters),
            itervalues(context.io_blocks),
            itervalues(context.logic_blocks),
            itervalues(context.connection_boxes),
            itervalues(context.switch_boxes)))
        for module in modules:
            switchify(context.switch_library, module)
            for inst in itervalues(module.all_instances):
                if inst.module_class.is_switch:
                    hierarchy.setdefault(inst.model.name, {})
                    hierarchy[module.name][inst.model.name] = inst.model

# ----------------------------------------------------------------------------
# -- Create and Connect Ports/Pins in Tiles & Arrays -------------------------
# ----------------------------------------------------------------------------
class CompleteConnection(Object, AbstractPass):
    """Create and connect ports/pins in tiles & arrays."""

    @property
    def key(self):
        """Key of this pass."""
        return "completion.connection"

    @property
    def passes_after_self(self):
        """Passes that should be run after this pass."""
        return ("rtl", "vpr", "config", "asicflow")

    def __process_array(self, context, array, top = False):
        hierarchy = analyze_hierarchy(context)
        for module in itervalues(hierarchy[array.name]):
            if module.module_class.is_tile:
                netify_tile(module)
            elif module.module_class.is_array:
                self.__process_array(context, module)
        netify_array(array, top)

    def run(self, context):
        self.__process_array(context, context.top, True)
