# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.algorithm.util.hierarchy import hierarchical_instance

__all__ = ['get_hierarchical_tile']

# ----------------------------------------------------------------------------
# -- Array Helper Functions --------------------------------------------------
# ----------------------------------------------------------------------------
def get_hierarchical_tile(array, position, hierarchy = None):
    """Get the tile at ``position`` down the hierarchy."""
    instance = array.get_root_element(position)
    if instance is None:
        return None
    elif instance.module_class.is_tile:
        return hierarchical_instance(instance, hierarchy, True)
    else:   # instance.module_class.is_array
        return get_hierarchical_tile(instance.model, position - instance.position,
                hierarchical_instance(instance, hierarchy, True))
