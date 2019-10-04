# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

__doc__ = """
Algorithms for querying and traversing the hierarchy.

Because of performance concerns, we are not using a class to refer to a hierarchical object, i.e., a instance
or a net viewed from a few levels up in the hierarchy. Instead, we use a sequence of instances down the hierarchy
to refer to a hierarchical instance, and 2-tuple \(a hierarchical instance and the net in the leaf instance\) to refer
to a hierarchical net.
"""

from prga.arch.common import Position
from prga.arch.net.const import UNCONNECTED
from prga.util import uno
from prga.exception import PRGAInternalError
from copy import copy

# ----------------------------------------------------------------------------
# -- Convert Regular Instance to Hierarchical Instance -----------------------
# ----------------------------------------------------------------------------
def hierarchical_instance(instance, hierarchy = None, inplace = False):
    """Convert a instance to a hierarchical instance."""
    if hierarchy is None:
        return [instance]
    elif inplace:
        hierarchy.append(instance)
        return hierarchy
    else:
        return hierarchy + [instance]

# ----------------------------------------------------------------------------
# -- Convert Regular Net to Hierarchical Net ---------------------------------
# ----------------------------------------------------------------------------
def hierarchical_net(net, hierarchy = None, inplace = False):
    """Convert a net to a hierarchical net.
    
    If ``net`` is a pin bus/bit, it will be converted to one level of hierarchical instance and the corresponding
    port bus/bit.
    """
    if net.is_pin:
        if net.is_bus:
            return hierarchical_instance(net.parent, hierarchy, inplace), net.model
        else:
            return hierarchical_instance(net.parent, hierarchy, inplace), net.bus.model[net.index]
    elif inplace:
        return uno(hierarchy, []), net
    elif hierarchy is None:
        return [], net
    else:
        return copy(hierarchy), net

# ----------------------------------------------------------------------------
# -- Position of a Hierarchical Instance -------------------------------------
# ----------------------------------------------------------------------------
def hierarchical_position(instance):
    """Calculate the position of ``instance`` in the top-level array."""
    return sum(inst.position for inst in instance)

# ----------------------------------------------------------------------------
# -- Iterate Combinational Upstream of a Hierarchical Net --------------------
# ----------------------------------------------------------------------------
def iter_combinatinal_sources(net, inplace = False):
    """Iterate the direct driver of hierarchical bit, ``net``."""
    instance, bit = net
    if bit.is_bus:
        raise PRGAInternalError("'{}' is a bus".format(net))
    elif bit.net_type.is_pin:
        raise PRGAInternalError("'{}' is a pin".format(net))
    if bit.direction.is_output:
        if bit.parent.is_leaf_module or bit.source is UNCONNECTED:
            # we don't search combinational paths through a leaf module here.
            # do that in the caller's context
            return
            yield
        else:
            yield hierarchical_net(bit.source, instance, inplace)
    elif len(instance) == 0:
        return
        yield
    else:
        if inplace:
            leaf = instance.pop()
        else:
            instance, leaf = instance[:-1], instance[-1]
        source_bit = leaf.all_pins[bit.key][bit.index].source
        if source_bit is UNCONNECTED:
            return
            yield
        else:
            yield hierarchical_net(source_bit, instance, inplace)
