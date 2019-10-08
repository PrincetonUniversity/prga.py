# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.vprgen.block import vpr_arch_block, vpr_arch_primitive
from prga.vprgen.layout import vpr_arch_tile, vpr_arch_layout
from prga.vprgen.routing import vpr_arch_segment, vpr_arch_default_switch
from prga.flow.util import iter_all_arrays, iter_all_tiles

from itertools import chain

__all__ = ['vpr_arch_xml']

# ----------------------------------------------------------------------------
# -- Generate Full VPR Architecture XML --------------------------------------
# ----------------------------------------------------------------------------
def vpr_arch_xml(xmlgen, context):
    """Generate the full VPR architecture XML for ``context``.

    Args:
        xmlgen (`XMLGenerator`):
        context (`BaseArchitectureContext`):
    """
    with xmlgen.element('architecture'):
        # models
        with xmlgen.element('models'):
            for primitive in itervalues(context.primitives):
                if primitive.primitive_class.is_custom or primitive.primitive_class.is_memory:
                    vpr_arch_primitive(xmlgen, primitive)
        # tiles
        with xmlgen.element('tiles'):
            for tile in iter_all_tiles(context):
                vpr_arch_tile(xmlgen, tile)
        # layout
        vpr_arch_layout(xmlgen, context.top)
        # device: faked
        with xmlgen.element('device'):
            xmlgen.element_leaf('sizing', {'R_minW_nmos': '0.0', 'R_minW_pmos': '0.0'})
            xmlgen.element_leaf('connection_block', {'input_switch_name': 'default'})
            xmlgen.element_leaf('area', {'grid_logic_tile_area': '0.0'})
            xmlgen.element_leaf('switch_block', {'type': 'wilton', 'fs': '3'})
            xmlgen.element_leaf('default_fc',
                    {'in_type': 'frac', 'in_val': '1.0', 'out_type': 'frac', 'out_val': '1.0'})
            with xmlgen.element('chan_width_distr'):
                xmlgen.element_leaf('x', {'distr': 'uniform', 'peak': '1.0'})
                xmlgen.element_leaf('y', {'distr': 'uniform', 'peak': '1.0'})
        # switchlist
        with xmlgen.element('switchlist'):
            vpr_arch_default_switch(xmlgen)
        # segmentlist
        with xmlgen.element('segmentlist'):
            for segment in itervalues(context.segments):
                vpr_arch_segment(xmlgen, segment)
        # complexblocklist
        with xmlgen.element('complexblocklist'):
            for tile in iter_all_tiles(context):
                vpr_arch_block(xmlgen, tile.block, tile.name)
