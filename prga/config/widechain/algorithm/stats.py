# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.exception import PRGAInternalError

__all__ = ['get_config_widechain_bitcount', 'get_config_widechain_bitmap']

# ----------------------------------------------------------------------------
# -- Get the Configuration Bits Count ----------------------------------------
# ----------------------------------------------------------------------------
def get_config_widechain_bitcount(context, module, drop_cache = False):
    """Get the configuration bit count of ``module``.

    Args:
        context (`ArchitectureContext`):
        module (`AbstractModule`):
        drop_cache (:obj:`bool`):

    Returns:
        :obj:`Mapping` [:obj:`int` or None, :obj:`int` ]: A mapping from chain group ID to bit count
    """
    key = 'config.widechain.bitcount'
    if not drop_cache:
        cache = context._cache.get(key, {}).get(module.name)
        if cache is not None:
            return cache
    cfg_d = module.logical_ports.get('cfg_d')
    if cfg_d is not None:                       # parallel configuration port
        bitcount = context._cache.setdefault(key, {})[module.name] = {None: len(cfg_d)}
        return bitcount
    elif 'cfg_i' in module.logical_ports:
        if module.module_class.is_config:       # configuration module without data output
            bitcount = context._cache.setdefault(key, {})[module.name] = {}
            return bitcount
        elif module.is_leaf_module:             # leaf module with embedded configuration bits
            bitcount = context._cache.setdefault(key, {})[module.name] = {None: module.config_bitcount}
            return bitcount
    # may contain zero, one or multiple chain groups
    get_config_widechain_bitmap(context, module, drop_cache)
    return context._cache[key][module.name]

# ----------------------------------------------------------------------------
# -- Get the Configuration Bits Mapping --------------------------------------
# ----------------------------------------------------------------------------
def _traverse_single_widechain(context, tail, bitmap, bitcounts, drop_cache):
    try:
        group = int(tail.name.lstrip('cfg_o_cg'))
    except ValueError:
        group = None
    # 1. check if this is a FIFO-controlled chain
    prev, head = tail.logical_source, None
    if not prev.net_type.is_pin:
        raise PRGAInternalError("{} is not driven by a pin".format(tail))
    elif prev.parent.module_class.is_config and prev.parent.model.widechain_class.is_ctrl:
        tail = prev.parent.logical_pins['cfg_data_tail']
        head = prev.parent.logical_pins['cfg_data_head']
    else:
        head = tail.parent.logical_ports['cfg_i' if group is None else ('cfg_i_cg' + str(group))]
    chain = []
    cur = tail
    # 2. back-trace the chain
    while True:
        prev = cur.logical_source
        if prev is head:    # we reached the head of the chain
            break
        assert prev.direction.is_output and prev.name.startswith('cfg_o') and prev.net_class.is_config
        try:
            subgroup = int(prev.name.lstrip('cfg_o_cg'))
        except ValueError:
            subgroup = None
        chain.append( (prev.parent, subgroup) )
        if subgroup is None:
            cur = prev.parent.logical_pins['cfg_i']
        else:
            cur = prev.parent.logical_pins['cfg_i_cg' + str(subgroup)]
    # 3. process the chain
    config_bitoffset = 0
    for instance, subgroup in reversed(chain):
        bitmap[instance.name, subgroup] = group, config_bitoffset
        config_bitoffset += get_config_widechain_bitcount(context, instance.model, drop_cache).get(subgroup, 0)
    bitcounts[group] = config_bitoffset

def get_config_widechain_bitmap(context, module, drop_cache = False):
    """Get the configuration bit offset mapping of ``module``.

    Args:
        context (`ArchitectureContext`):
        module (`AbstractModule`):
        drop_cache (:obj:`bool`):

    Returns:
        :obj:`Mapping` [:obj:`tuple` [:obj:`str`, :obj:`int` ], :obj:`tuple` [:obj:`int`, :obj:`int` ]]: A mapping
            from \(instance name, sub-chain group ID\) to \(chain group ID, bit offset\)
    """
    cachekey = 'config.bitchain.bitmap'
    key = module.name if not module.module_class.is_mode else '{}.{}'.format(module.parent.name, module.name)
    if not drop_cache:
        cache = context._cache.get(cachekey, {}).get(key)
        if cache is not None:
            return cache
    if module.module_class.is_mode:
        return context._cache.setdefault(cachekey, {}).setdefault(key, module.config_bitmap)
    bitmap = context._cache.setdefault(cachekey, {})[key] = {}
    cfg_d = module.logical_ports.get('cfg_d')
    if cfg_d is not None:   # parallel configuration port. No instances on the "configurer" side
        for instance in itervalues(module.logical_instances):
            sub_cfg_d = instance.logical_pins.get('cfg_d')
            if sub_cfg_d is None:   # no configuration bits
                continue
            assert sub_cfg_d[0].logical_source.bus is cfg_d
            bitmap[instance.name, None] = None, sub_cfg_d[0].logical_source.index
        return bitmap
    bitcounts = {}
    cfg_o = module.logical_ports.get('cfg_o')
    if cfg_o is not None:   # ungrouped serial configuration port
        _traverse_single_widechain(context, cfg_o, bitmap, bitcounts, drop_cache)
    else:                   # find all chain groups
        for port in itervalues(module.logical_ports):
            if port.name.startswith('cfg_o'):
                _traverse_single_widechain(context, port, bitmap, bitcounts, drop_cache)
    context._cache.setdefault('config.widechain.bitcount', {})[module.name] = bitcounts
    return bitmap
