# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from itertools import chain

__all__ = ['physicalify']

# ----------------------------------------------------------------------------
# -- Complete Physical Connections -------------------------------------------
# ----------------------------------------------------------------------------
def physicalify(module):
    """Complete physical connections in ``module``."""
    for bus in filter(lambda bus: bus.is_sink, chain(itervalues(module.logical_ports),
            iter(pin for instance in itervalues(module.logical_instances)
                for pin in itervalues(instance.logical_pins)))):
        for bit in bus:
            source, sink = bit.logical_source, bit
            if source.physical_cp is not source or sink.physical_cp is not sink:
                sink.physical_cp.physical_source = source.physical_cp
