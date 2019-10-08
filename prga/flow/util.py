# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

__all__ = ['analyze_hierarchy']

# ----------------------------------------------------------------------------
# -- Helper Function ---------------------------------------------------------
# ----------------------------------------------------------------------------
def analyze_hierarchy(context, drop_cache = False):
    """Analyze the hierarchy of the top-level array of ``context``."""
    if not drop_cache:
        cache = context._cache.get('hierarchy', None)
        if cache is not None:
            return cache
    hierarchy = context._cache['hierarchy'] = {}
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
