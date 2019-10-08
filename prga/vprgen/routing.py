# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

__all__ = ['vpr_arch_segment', 'vpr_arch_default_switch']

# ----------------------------------------------------------------------------
# -- Segment to VPR Architecture Description ---------------------------------
# ----------------------------------------------------------------------------
def vpr_arch_segment(xmlgen, segment):
    """Convert a segment to VPR architecture description.

    Args:
        xmlgen (`XMLGenerator`):
        segment (`Segment`):
    """
    with xmlgen.element('segment', {
        'freq': '1.0',
        'length': str(segment.length),
        'type': 'unidir',
        'Rmetal': '0.0',
        'Cmetal': '0.0',
        }):
        # fake switch
        xmlgen.element_leaf('mux', {'name': 'default'})
        xmlgen.element_leaf('sb', {'type': 'pattern'}, ' '.join(iter('1' for i in range(segment.length + 1))))
        xmlgen.element_leaf('cb', {'type': 'pattern'}, ' '.join(iter('1' for i in range(segment.length))))

def vpr_arch_default_switch(xmlgen):
    """Generate a default switch tag to VPR architecture description.

    Args:
        xmlgen (`XMLGenerator`):
    """
    xmlgen.element_leaf('switch', {
        'type': 'mux',
        'name': 'default',
        'R': '0.0',
        'Cin': '0.0',
        'Cout': '0.0',
        'Tdel': '1e-11',
        'mux_trans_size': '0.0',
        'buf_size': '0.0',
        })
