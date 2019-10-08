# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position

__all__ = ['vpr_arch_tile', 'vpr_arch_layout']

# ----------------------------------------------------------------------------
# -- Tile to VPR Architecture Description ------------------------------------
# ----------------------------------------------------------------------------
def vpr_arch_tile(xmlgen, tile):
    """Convert a tile into VPR architecture description.
    
    Args:
        xmlgen (`XMLGenerator`):
        tile (`Tile`):
    """
    with xmlgen.element('tile', {
        'name': tile.name,
        'capacity': tile.capacity,
        'width': tile.width,
        'height': tile.height,
        }):
        # 1. emit ports
        for port in itervalues(tile.block.ports):
            attrs = {'name': port.name, 'num_pins': port.width}
            if port.net_class.is_global and not port.is_clock:
                attrs['is_non_clock_global'] = "true"
            xmlgen.element_leaf(
                    'clock' if port.is_clock else port.direction.case('input', 'output'),
                    attrs)
        # 2. equivalent sites
        with xmlgen.element('equivalent_sites'):
            xmlgen.element_leaf('site', {'pb_type': tile.name})

# ----------------------------------------------------------------------------
# -- Layout to VPR Architecture Description ----------------------------------
# ----------------------------------------------------------------------------
def _vpr_arch_array(xmlgen, array, position = (0, 0)):
    """Convert an array to 'single' elements.

    Args:
        xmlgen (`XMLGenerator`):
        array (`Array`):
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
    """
    position = Position(*position)
    for pos, instance in iteritems(array.element_instances):
        pos += position
        if instance.module_class.is_tile:
            xmlgen.element_leaf('single', {
                'type': instance.model.name,
                'priority': '1',
                'x': pos.x,
                'y': pos.y,
                })
        else:
            _vpr_arch_array(xmlgen, instance.model, pos)

def vpr_arch_layout(xmlgen, array):
    """Convert a top-level array to VPR architecture description.

    Args:
        xmlgen (`XMLGenerator`):
        array (`Array`):
    """
    with xmlgen.element('layout'):
        with xmlgen.element('fixed_layout', {'name': array.name, 'width': array.width, 'height': array.height}):
            _vpr_arch_array(xmlgen, array)
