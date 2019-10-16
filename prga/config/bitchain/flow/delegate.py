# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.flow.delegate import ConfigCircuitryDelegate
from prga.flow.util import get_switch_path
from prga.config.bitchain.design.primitive import CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH, ConfigBitchain
from prga.config.bitchain.algorithm.injection import ConfigBitchainLibraryDelegate, inject_config_chain
from prga.config.bitchain.algorithm.bitstream import get_config_bit_count, get_config_bit_offset
from prga.exception import PRGAInternalError

__all__ = ['BitchainConfigCircuitryDelegate']

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Delegate for Bitchain-based configuration -------
# ----------------------------------------------------------------------------
class BitchainConfigCircuitryDelegate(ConfigBitchainLibraryDelegate, ConfigCircuitryDelegate):

    __slots__ = ['_bitchains']
    def __init__(self, context):
        super(BitchainConfigCircuitryDelegate, self).__init__(context)
        self._bitchains = {}

    def __config_bit_offset_for_intrablock_instance(self, hierarchy):
        total = 0
        for instance in hierarchy:
            config_bit_offsets = get_config_bit_offset(self.context, instance.parent)
            config_bit_offset = config_bit_offsets.get(instance.name)
            if config_bit_offset is None:
                return None
            total += config_bit_offset
        return total

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def additional_template_search_paths(self):
        return (CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH, )

    def get_or_create_bitchain(self, width):
        try:
            return self._bitchains[width]
        except KeyError:
            module = ConfigBitchain(width)
            self._bitchains[width] = self._context._modules[module.name] = module
            return module

    def fasm_prefix_for_tile(self, hierarchical_instance):
        config_bit_base = 0
        for instance in hierarchical_instance:
            config_bit_offsets = get_config_bit_offset(self.context, instance.parent)
            if instance.name not in config_bit_offsets:     # no configuration bits down the path
                return tuple()
            config_bit_base += config_bit_offsets[instance.name]
        config_bit_offsets = get_config_bit_offset(self.context, hierarchical_instance[-1].model)
        prefix = []
        for subblock in range(hierarchical_instance[-1].model.capacity):
            blk_inst = hierarchical_instance[-1].model.block_instances[subblock]
            if blk_inst.name not in config_bit_offsets:
                return tuple()
            prefix.append('b' + str(config_bit_base + config_bit_offsets[blk_inst.name]))
        return tuple(iter(prefix))

    def fasm_mode(self, hierarchical_instance, mode):
        config_bit_base = self.__config_bit_offset_for_intrablock_instance(hierarchical_instance)
        if config_bit_base is None:
            return tuple()
        if hierarchical_instance[-1].model.primitive_class.is_iopad:
            if mode == 'outpad':
                return ('b' + str(config_bit_base), )
            else:
                return tuple()
        else:
            raise NotImplementedError

    def fasm_lut(self, hierarchical_instance):
        config_bit_base = self.__config_bit_offset_for_intrablock_instance(hierarchical_instance)
        if config_bit_base is None:
            return ''
        return 'b{}[{}:0]'.format(str(config_bit_base),
                len(hierarchical_instance[-1].all_pins['cfg_d']) - 1)

    def fasm_mux_for_intrablock_switch(self, source, sink, hierarchy):
        module = source.parent if source.net_type.is_port else source.parent.parent
        config_bit_base = 0 if not hierarchy else self.__config_bit_offset_for_intrablock_instance(hierarchy)
        config_bit_offsets = get_config_bit_offset(self.context, module)
        path = get_switch_path(self.context, source, sink)
        retval = []
        for bit in path:
            config_bits = bit.index
            config_bit_offset = config_bit_offsets.get(bit.parent.name, None)
            if config_bit_offset is None:
                raise PRGAInternalError("No configuration circuitry for switch '{}'"
                        .format(bit.parent))
            while config_bits:
                if config_bits % 2 == 1:
                    retval.append('b' + str(config_bit_base + config_bit_offset))
                config_bits /= 2
                config_bit_offset += 1
        return retval

    def fasm_features_for_routing_switch(self, hierarchical_switch_input):
        hierarchy, input_port = hierarchical_switch_input
        switch_instance = hierarchy[-1]
        hierarchy = hierarchy[:-1]
        module = hierarchy[-1].model
        config_bit_base = self.__config_bit_offset_for_intrablock_instance(hierarchy)
        config_bit_offset = get_config_bit_offset(self.context, module).get(switch_instance.name)
        config_bits = input_port.index
        if config_bit_offset is None:
            raise PRGAInternalError("No configuration circuitry for switch '{}'"
                    .format(switch_instance))
        retval = []
        while config_bits:
            if config_bits % 2 == 1:
                retval.append('b' + str(config_bit_base + config_bit_offset))
            config_bits /= 2
            config_bit_offset += 1
        return tuple(iter(retval))
