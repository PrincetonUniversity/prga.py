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
        cache = context._cache.get('config.widechain.bit_count', {}).get(module.name)
        if cache is not None:
            return cache
    cfg_d = module.logical_ports.get('cfg_d')
    if cfg_d is not None:               # parallel configuration port
        context._cache.setdefault('config.widechain.bit_count', {})[module.name] = len(cfg_d)
        return len(cfg_d)
    elif 'cfg_i' in module.logical_ports:   # serial configuration port
        if module.is_leaf_module:
            context._cache.setdefault('config.widechain.bit_count', {})[module.name] = module.config_bit_count
            return module.config_bit_count
        else:
            get_config_bit_offset(context, module, drop_cache)
            return context._cache['config.widechain.bit_count'][module.name]
    else:
        return 0

# ----------------------------------------------------------------------------
# -- Get the Configuration Bits Offset ---------------------------------------
# ----------------------------------------------------------------------------
def get_config_bit_offset(context, module, drop_cache = False):
    """Get the configuration bit offsets of ``module``."""
    key = module.name if not module.module_class.is_mode else '{}.{}'.format(module.parent.name, module.name)
    if not drop_cache:
        cache = context._cache.get('config.widechain.bit_offset', {}).get(key)
        if cache is not None:
            return cache
    if module.module_class.is_mode:
        return context._cache.setdefault('config.widechain.bit_offset', {}).setdefault(key, module.config_bit_offset)
    entry = context._cache.setdefault('config.widechain.bit_offset', {})[key] = {}
    cfg_d = module.logical_ports.get('cfg_d')
    if cfg_d is not None:               # parallel configuration port. No sub-instances on the "configuration" side
        for instance in itervalues(module.logical_instances):
            sub_cfg_d = instance.logical_pins.get('cfg_d')
            if sub_cfg_d is None:       # no configuration bits
                continue
            assert sub_cfg_d[0].logical_source.bus is cfg_d
            entry[instance.name] = sub_cfg_d[0].logical_source.index    # XXX: assume configuration bits are continuous
        return entry
    cfg_o = module.logical_ports.get('cfg_o')
    if cfg_o is None:                   # no configuration port
        if not module.module_class.is_mode:
            context._cache.setdefault('config.widechain.bit_count', {})[module.name] = 0
        return entry
    chain = []
    cur = cfg_o
    while True:
        prev = cur.logical_source
        if prev.net_type.is_port:       # we reached the beginning of the chain
            assert prev.direction.is_input and prev.name == 'cfg_i' and prev.net_class.is_config
            break
        assert prev.net_type.is_pin and prev.direction.is_output and prev.name == 'cfg_o'
        chain.append(prev.parent)
        cur = prev.parent.logical_pins['cfg_i']
    cfg_bit_offset = 0
    for instance in reversed(chain):
        entry[instance.name] = cfg_bit_offset
        cfg_bit_offset += get_config_bit_count(context, instance.model, drop_cache)
    if not module.module_class.is_mode:
        context._cache.setdefault('config.bitchain.bit_count', {})[module.name] = cfg_bit_offset
    # done with "configuration side". check out "configured" side
    for instance in itervalues(module.logical_instances):
        sub_cfg_d = instance.logical_pins.get('cfg_d')
        if sub_cfg_d is None or sub_cfg_d.direction.is_output:
            # no configuration bits, or on the "configuration" side
            continue
        base = entry[sub_cfg_d.logical_source.parent.name]
        offset = sub_cfg_d[0].logical_source.index
        entry[instance.name] = base + offset
    return entry
