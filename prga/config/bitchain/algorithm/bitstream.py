# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

__all__ = ['get_config_bit_count', 'get_config_bit_offset']

# ----------------------------------------------------------------------------
# -- Get the Configuration Bits Count ----------------------------------------
# ----------------------------------------------------------------------------
def get_config_bit_count(context, module, drop_cache = False):
    """Get the configuration bit count of ``module``."""
    if not drop_cache:
        cache = context._cache.get('bitchain_config_bit_count', {}).get(module.name)
        if cache is not None:
            return cache
    cfg_d = module.all_ports.get('cfg_d')
    if cfg_d is not None:
        context._cache.setdefault('bitchain_config_bit_count', {})[module.name] = len(cfg_d)
        return len(cfg_d)
    elif 'cfg_i' in module.all_ports:
        if module.is_leaf_module:
            context._cache.setdefault('bitchain_config_bit_count', {})[module.name] = len(module.config_bits)
            return len(module.config_bits)
        else:
            get_config_bit_offset(context, module, drop_cache)
            return context._cache.setdefault('bitchain_config_bit_count', {})[module.name]
    else:
        return 0

# ----------------------------------------------------------------------------
# -- Get the Configuration Bits Offset ---------------------------------------
# ----------------------------------------------------------------------------
def get_config_bit_offset(context, module, drop_cache = False):
    """Get the configuration bit offsets of ``module``."""
    if not drop_cache:
        cache = context._cache.get('bitchain_config_bit_offset', {}).get(module.name)
        if cache is not None:
            return cache
    entry = context._cache.setdefault('bitchain_config_bit_offset', {})[module.name] = {}
    cfg_d = module.all_ports.get('cfg_d')
    if cfg_d is not None:
        #TODO
        pass
    cur = module.all_ports.get('cfg_o')
    if cur is None:
        return {}
    cfg_instances = []
    while True:
        prev = cur.source
        if prev.net_type.is_port:
            assert prev.direction.is_input and prev.name == 'cfg_i' and prev.net_class.is_config
            break
        assert prev.net_type.is_pin and prev.direction.is_output and prev.name == 'cfg_o'
        cfg_instances.append(prev.parent)
        cur = prev.parent.all_pins['cfg_i']
    cfg_bit_offset = 0
    for instance in reversed(cfg_instances):
        entry[instance.name] = cfg_bit_offset
        cfg_bit_offset += get_config_bit_count(context, instance.model, drop_cache)
    context._cache.setdefault('bitchain_config_bit_count', {}).setdefault(module.name, cfg_bit_offset)
    return entry
