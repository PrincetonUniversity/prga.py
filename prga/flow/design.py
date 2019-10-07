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

__all__ = ['RoutingBoxCompleter', 'SwitchCompleter', 'ConnectionCompleter']

# ----------------------------------------------------------------------------
# -- Routing Box Completer ---------------------------------------------------
# ----------------------------------------------------------------------------
class RoutingBoxCompleter(Object, AbstractPass):
    """Connection box and switch box completer.

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
        return "completer.routing"

    @property
    def passes_after_self(self):
        return ("completer.switch", "completer.connection", "rtl", "vpr", "config", "asicflow")

    def __process_array(self, context, array):
        hierarchy = analyze_hierarchy(context)
        for module in itervalues(hierarchy[array.name]):
            if module.module_class.is_array:
                self.__process_array(context, module)
            elif module.module_class.is_switch_box:
                generate_wilton(module, itervalues(context.segments), cycle_free = self.cycle_free)
            elif module.module_class.is_tile:
                cboxify(context.connection_box_library, module, module.orientation.opposite)
                for (position, orientation), cbox_inst in iteritems(module.cbox_instances):
                    generate_fc(cbox_inst.model, itervalues(context.segments), module.block, orientation,
                            self.block_fc.get(module.block.name, self.default_fc), module.capacity,
                            position, orientation.case((0, 0), (0, 0), (0, -1), (-1, 0)))
        sboxify(context.switch_box_library, array)

    def run(self, context):
        self.__process_array(context.top)

# ----------------------------------------------------------------------------
# -- Switch Completer --------------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchCompleter(Object, AbstractPass):
    """Switch completer."""

    @property
    def key(self):
        """Key of this pass."""
        return "completer.switch"

    @property
    def passes_after_self(self):
        """Passes that should be run after this pass."""
        return ("completer.connection", "rtl", "vpr", "config", "asicflow")

    def run(self, context):
        for module in chain(itervalues(context.clusters),
                itervalues(context.io_blocks),
                itervalues(context.logic_blocks),
                itervalues(context.connection_boxes),
                itervalues(context.switch_boxes)):
            switchify(context.switch_library, module)

# ----------------------------------------------------------------------------
# -- Connection Completer ----------------------------------------------------
# ----------------------------------------------------------------------------
class ConnectionCompleter(Object, AbstractPass):
    """Connect all nets."""

    @property
    def key(self):
        """Key of this pass."""
        return "completer.connection"

    @property
    def passes_after_self(self):
        """Passes that should be run after this pass."""
        return ("rtl", "vpr", "config", "asicflow")

    def __process_array(self, context, array):
        hierarchy = analyze_hierarchy(context)
        for module in itervalues(hierarchy[array.name]):
            if module.module_class.is_tile:
                netify_tile(module)
            elif module.module_class.is_array:
                self.__process_array(context, module)
        netify_array(array)

    def run(self, context):
        self.__process_array(context.top)
