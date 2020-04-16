# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.config.packetizedchain.algorithm.stats import ConfigPacketizedChainStatsAlgorithms as sa
from prga.exception import PRGAInternalError

__all__ = ['packetizedchain_hop2ranges', 'packetizedchain_packetize']

def packetizedchain_hop2ranges(context):
    config_width = context.config_circuitry_delegate.config_width
    total_config_bits = context.config_circuitry_delegate.total_config_bits
    total_hopcount = context.config_circuitry_delegate.total_hopcount
    if total_hopcount > 0x10000:
        raise PRGAInternalError("Architecture '{}' has more than 65536 hops."
                .format(context.top.name))
    # hop boundaries
    hop2hierarchy = [tuple() for _ in range(total_hopcount)]
    hop2bounds = [None for _ in range(total_hopcount)]
    stack = [(context.top, 0, 0, tuple())]
    while stack:
        m, hopbase, bitbase, hierarchy = stack.pop()
        hopmap = sa.get_config_hopmap(context, m)
        if hopmap is None:  # we reached the leaf hop
            if hop2bounds[hopbase] is not None:
                raise PRGAInternalError("Duplicate hop ID detected at {}".format(hopbase))
            hop2bounds[hopbase] = bitbase
            hop2hierarchy[hopbase] = hierarchy
        else:               # more hops below
            bitmap = sa.get_config_bitmap(context, m)
            for instance in itervalues(m.logical_instances):
                hopoffset = hopmap.get(instance.name)
                if hopoffset is None:
                    continue
                stack.append( (instance.model, hopbase + hopoffset, bitbase + bitmap[instance.name],
                            hierarchy + (instance, )) )
    hop2bounds.append( total_config_bits )
    for hop, elem in enumerate(hop2bounds):
        if elem is None:
            raise PRGAInternalError("Unassigned hop ID detected at {}".format(hop))
    hop2ranges = [hop2bounds[i + 1] - hop2bounds[i] for i in range(total_hopcount)]
    return hop2ranges

def packetizedchain_packetize(length, max_payload = 0x10000):
    remainder = length
    while remainder:
        hoc_head = remainder == length
        hoc_tail = False
        effective_payload = max_payload - (32 if hoc_head else 0)
        if remainder <= effective_payload:
            if remainder <= effective_payload - 32:
                effective_payload = remainder
                hoc_tail = True
            else:
                effective_payload = remainder - config_width
        yield hoc_head, effective_payload, hoc_tail
        remainder -= effective_payload
