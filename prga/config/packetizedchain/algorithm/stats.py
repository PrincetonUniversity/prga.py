# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.exception import PRGAInternalError

__all__ = ['ConfigPacketizedChainStatsAlgorithms']

# ----------------------------------------------------------------------------
# -- A Holder Class For Algorithms -------------------------------------------
# ----------------------------------------------------------------------------
class ConfigPacketizedChainStatsAlgorithms(object):
    """A holder class (not meant to be instantiated) for stats algorithms for packetized chain."""

    @classmethod
    def get_config_hopcount(cls, context, module, drop_cache = False):
        """Get the total number of hops in ``module``.

        Args:
            context (`ArchitectureContext`):
            module (`AbstractModule`):
            drop_cache (:obj:`bool`):

        Returns:
            :obj:`int`: Number of configuration hops in ``module``. ``1`` for leaf hop, and ``None`` for modules below
                the leaf hop
        """
        key = 'config.packetizedchain.hopcount'
        if not drop_cache:
            cache = context._cache.get(key, {}).get(module.name)
            if cache is not None:
                return cache
        # look for port cfg_pkt_data_o
        port = module.logical_ports.get("cfg_pkt_data_o")
        if port is None:
            # no config ctrl module down the hierarchy
            return None
        cur = port.logical_source
        if cur.parent.module_class.is_config:   # this is the leaf hop
            context._cache.setdefault(key, {})[module.name] = 1
            return 1
        # construct chain
        cls.get_config_hopmap(context, module, drop_cache)
        return context._cache.setdefault(key, {}).get(module.name)

    @classmethod
    def get_config_hopmap(cls, context, module, drop_cache = False):
        """Get the configuration hopcount map for ``module``.

        Args:
            context (`ArchitectureContext`):
            module (`AbstractModule`):
            drop_cache (:obj:`bool`):

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`int`]: A mapping from instance name to hop count. ``None`` for leaf hop
                and below
        """
        key = 'config.packetizedchain.hopmap'
        if not drop_cache:
            cache = context._cache.get(key, {}).get(module.name)
            if cache is not None:
                return cache
        # look for port cfg_pkt_data_o
        port = module.logical_ports.get("cfg_pkt_data_o")
        if port is None:
            # no config ctrl module down the hierarchy
            return None
        cur = port.logical_source
        if cur.parent.module_class.is_config:
            # leaf ctrl
            return None
        # construct chain
        hopmap = context._cache.setdefault(key, {}).setdefault(module.name, {})
        chain = []
        while cur.net_type.is_pin:
            chain.append( cur.parent )
            cur = cur.parent.logical_pins["cfg_pkt_data_i"].logical_source
        assert chain
        hopcount = 0
        for instance in reversed(chain):
            hopmap[instance.name] = hopcount
            hopcount += cls.get_config_hopcount(context, instance.model, drop_cache)
        context._cache.setdefault('config.packetizedchain.hopcount', {})[module.name] = hopcount
        return hopmap

    @classmethod
    def get_config_bitcount(cls, context, module, drop_cache = False):
        """Get the configuration bit count of ``module``.

        Args:
            context (`ArchitectureContext`):
            module (`AbstractModule`):
            drop_cache (:obj:`bool`):

        Returns:
            :obj:`int`: Number of configuration bits in ``module``
        """
        key = 'config.packetizedchain.bitcount'
        if not drop_cache:
            cache = context._cache.get(key, {}).get(module.name)
            if cache is not None:
                return cache
        # scenario 1: parallel configuration ports
        cfg_d = module.logical_ports.get("cfg_d")
        if cfg_d is not None:
            bitcount = context._cache.setdefault(key, {})[module.name] = len(cfg_d)
            return bitcount
        # scenario 2: serial configuration ports
        if 'cfg_i' in module.logical_ports and module.is_leaf_module:
            bitcount = context._cache.setdefault(key, {})[module.name] = module.config_bitcount
            return bitcount
        # scenario 3: packetized configuration ports
        cls.get_config_bitmap(context, module, drop_cache)
        return context._cache[key][module.name]

    @classmethod
    def __traverse_chain(cls, context, tail, bitmap, drop_cache = False):
        chain = []
        cur = tail
        # back-trace the chain
        while True:
            chain.append(cur.parent)
            cur = cur.parent.logical_pins[cur.name[:-1] + 'i'].logical_source
            if cur.name != tail.name:
                break
        # process the chain
        bitcount = 0
        for instance in reversed(chain):
            bitmap[instance.name] = bitcount
            bitcount += cls.get_config_bitcount(context, instance.model, drop_cache)
        return bitcount

    @classmethod
    def __build_configured_side_bitmap(cls, context, module, bitmap):
        for instance in itervalues(module.logical_instances):
            sub_cfg_d = instance.logical_pins.get('cfg_d')
            if sub_cfg_d is None or sub_cfg_d.direction.is_output:
                continue
            base = bitmap[sub_cfg_d[0].logical_source.parent.name]
            offset = sub_cfg_d[0].logical_source.index
            bitmap[instance.name] = base + offset

    @classmethod
    def get_config_bitmap(cls, context, module, drop_cache = False):
        """Get the configuration bit mapping for ``module``.

        Args:
            context (`ArchitectureContext`):
            module (`AbstractModule`):
            drop_cache (:obj:`bool`):

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`int`]: A mapping from instance name to configuration bit offset
        """
        cachekey = 'config.packetizedchain.bitmap'
        key = module.name if not module.module_class.is_mode else '{}.{}'.format(module.parent.name, module.name)
        if not drop_cache:
            cache = context._cache.get(cachekey, {}).get(key)
            if cache is not None:
                return cache
        if module.module_class.is_mode:
            return context._cache.setdefault(cachekey, {}).setdefault(key, module.config_bitmap)
        bitmap = context._cache.setdefault(cachekey, {})[key] = {}
        # scenario 1: parallel configuration ports
        cfg_d = module.logical_ports.get('cfg_d')
        if cfg_d is not None:
            for instance in itervalues(module.logical_instances):
                sub_cfg_d = instance.logical_pins.get('cfg_d')
                if sub_cfg_d is None:
                    continue
                assert sub_cfg_d[0].logical_source.bus is cfg_d
                bitmap[instance.name] = sub_cfg_d[0].logical_source.index
            return bitmap
        # scenario 2: serial configuration ports
        cfg_o = module.logical_ports.get('cfg_o')
        if cfg_o is not None:
            bitcount = cls.__traverse_chain(context, cfg_o.logical_source, bitmap, drop_cache)
            context._cache.setdefault('config.packetizedchain.bitcount', {})[module.name] = bitcount
            cls.__build_configured_side_bitmap(context, module, bitmap)
            return bitmap
        # scenario 3: packetized configuration ports
        cfg_pkt_data_o = module.logical_ports.get('cfg_pkt_data_o')
        if cfg_pkt_data_o is None:
            return bitmap
        tail = cfg_pkt_data_o.logical_source
        if tail[0].parent.module_class.is_config:
            # scenario 3.1: packetized chain (controllers inside the current module)
            tail = tail[0].parent.logical_pins['cfg_din'].logical_source
        else:
            # scenario 3.2: packetized chain (controllers are inside the instances on the chain)
            pass
        bitcount = cls.__traverse_chain(context, tail, bitmap, drop_cache)
        context._cache.setdefault('config.packetizedchain.bitcount', {})[module.name] = bitcount
        return bitmap
