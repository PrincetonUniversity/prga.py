# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.exception import PRGAInternalError

__all__ = ['analyze_hierarchy', 'iter_all_arrays', 'iter_all_tiles', 'iter_all_sboxes',
        'get_switch_path']

# ----------------------------------------------------------------------------
# -- Helper Function ---------------------------------------------------------
# ----------------------------------------------------------------------------
def analyze_hierarchy(context, drop_cache = False):
    """Analyze the hierarchy of the top-level array of ``context``."""
    if not drop_cache:
        cache = context._cache.get('util.hierarchy', None)
        if cache is not None:
            return cache
    hierarchy = context._cache['util.hierarchy'] = {}
    modules = {context.top.name: context.top}
    while modules:
        name, module = modules.popitem()
        subhierarchy = hierarchy.setdefault(name, {})
        for instance in itervalues(module.all_instances):
            if instance.model.name not in hierarchy:
                modules[instance.model.name] = instance.model
            subhierarchy[instance.model.name] = instance.model
    return hierarchy

def iter_all_arrays(context, drop_cache = False):
    """Iterate through all arrays in use in ``context``."""
    hierarchy = analyze_hierarchy(context, drop_cache)
    visited = set()
    queue = {context.top.name: context.top}
    while queue:
        name, array = queue.popitem()
        visited.add(name)
        yield array
        for subname, sub in iteritems(hierarchy[name]):
            if not (subname in visited or subname in queue):
                queue[subname] = sub

def iter_all_tiles(context, drop_cache = False):
    """Iterate through all tiles in use in ``context``."""
    hierarchy = analyze_hierarchy(context, drop_cache)
    visited = set()
    queue = {context.top.name: context.top}
    while queue:
        name, array = queue.popitem()
        visited.add(name)
        for subname, sub in iteritems(hierarchy[name]):
            if subname in visited or subname in queue:
                continue
            elif sub.module_class.is_array:
                queue[subname] = sub
            elif sub.module_class.is_tile:
                yield sub
                visited.add(subname)

def iter_all_sboxes(context, drop_cache = False):
    """Iterate through all switch boxes in use in ``context``."""
    hierarchy = analyze_hierarchy(context, drop_cache)
    visited = set()
    queue = {context.top.name: context.top}
    while queue:
        name, array = queue.popitem()
        visited.add(name)
        for subname, sub in iteritems(hierarchy[name]):
            if subname in visited or subname in queue:
                continue
            elif sub.module_class.is_array:
                queue[subname] = sub
            elif sub.module_class.is_switch_box:
                yield sub
                visited.add(subname)

# ----------------------------------------------------------------------------
# -- Switch Path -------------------------------------------------------------
# ----------------------------------------------------------------------------
def _in_cache_bit_id(bit):
    return id(bit.bus), bit.index

def get_switch_path(context, source, sink, drop_cache = False):
    """Get the switch path from ``source`` to ``sink``.

    Args:
        context (`ArchitectureContext`):
        source (`AbstractSourceBit`):
        sink (`AbstractSinkBit`):
        drop_cache (:obj:`bool`):

    Returns:
        :obj:`Sequence` [`AbstractSinkBit` ]: A sequence of switch input bits
    """
    if sink.source is source:
        return tuple()
    module = source.parent if source.net_type.is_port else source.parent.parent
    if not drop_cache:
        cache = context._cache.get('util.switch_path', {}).get(module.name, {}).get(
                _in_cache_bit_id(sink), None)
        if cache is not None:
            path = cache.get(_in_cache_bit_id(source))
            if path is None:
                raise PRGAInternalError("No path from '{}' to '{}' in module '{}'"
                        .format(source, sink, module))
            else:
                return path
    # map all sources of sink
    sink_id = _in_cache_bit_id(sink)
    stack = [(sink, tuple())]
    cache = context._cache.setdefault('util.switch_path', {}).setdefault(module.name, {}).setdefault(
            _in_cache_bit_id(sink), {})
    while stack:
        cur_sink, cur_path = stack.pop()
        cur_source = cur_sink.source
        if cur_source.net_type.is_const:    # UNCONNECTED or CONSTANT connection
            continue
        if cur_source.net_type.is_pin and cur_source.net_class.is_switch:       # switch output
            for next_sink in cur_source.parent.switch_inputs:
                stack.append( (next_sink, cur_path + (next_sink, )) )
        else:                                                                   # other stuff
            cache[_in_cache_bit_id(cur_source)] = cur_path
    try:
        return cache[_in_cache_bit_id(source)]
    except KeyError:
        raise PRGAInternalError("No path from '{}' to '{}' in module '{}'"
                .format(source, sink, module))
