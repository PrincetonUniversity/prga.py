# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position
from prga.arch.routing.common import BlockPortID
from prga.algorithm.util.hierarchy import hierarchical_instance

__all__ = ['get_hierarchical_tile', 'get_hierarchical_sbox']

# ----------------------------------------------------------------------------
# -- Array Helper Functions --------------------------------------------------
# ----------------------------------------------------------------------------
def get_hierarchical_tile(array, position, hierarchy = None):
    """Get the tile at ``position`` down the hierarchy."""
    position = Position(*position)
    instance = array.get_root_element(position)
    if instance is None:
        return None
    elif instance.module_class.is_tile:
        return hierarchical_instance(instance, hierarchy, True)
    else:   # instance.module_class.is_array
        return get_hierarchical_tile(instance.model, position - instance.position,
                hierarchical_instance(instance, hierarchy, True))

def get_external_port(array, position, subblock, direction):
    """Get the external port."""
    tile = get_hierarchical_tile(array, position)
    if tile is None:
        return None
    tile = tile[-1].model
    if not tile.block.module_class.is_io_block:
        return None
    port = tile.block.physical_ports.get(direction.case('exti', 'exto'))
    if port is None:
        return None
    node = BlockPortID(position, port, subblock)
    port = array.physical_ports.get(node)
    if port is None:
        return None
    return port

def get_hierarchical_sbox(array, position, hierarchy = None):
    """Get the switch box at ``position`` down the hierarchy."""
    position = Position(*position)
    instance = array.get_root_element_for_sbox(position)
    if instance is None:
        return None
    elif instance.module_class.is_switch_box:
        return hierarchical_instance(instance, hierarchy, True)
    else:   # instance.module_class.is_array
        return get_hierarchical_sbox(instance.model, position - instance.position,
                hierarchical_instance(instance, hierarchy, True))
