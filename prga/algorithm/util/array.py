# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position
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
