# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.flow.flow import AbstractPass
from prga.flow.delegate import ConfigCircuitryDelegate, BuiltinPrimitiveLibrary
from prga.flow.util import get_switch_path
from prga.config.bitchain.design.primitive import (CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH, ConfigBitchain,
        FracturableLUT6, FracturableLUT6FF)
from prga.config.bitchain.algorithm.injection import ConfigBitchainLibraryDelegate, inject_config_chain
from prga.config.bitchain.algorithm.bitstream import get_config_bit_count, get_config_bit_offset
from prga.exception import PRGAInternalError
from prga.util import Object

__all__ = ['BitchainConfigCircuitryDelegate', 'InjectBitchainConfigCircuitry']

# ----------------------------------------------------------------------------
# -- Primitive Library for Bitchain-based configuration ----------------------
# ----------------------------------------------------------------------------
class BitchainPrimitiveLibrary(BuiltinPrimitiveLibrary):
    """Primitive library for bitchain-based configuration circuitry."""

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    def get_or_create_primitive(self, name, logical_only = False):
        module = self.context._modules.get(name)
        if module is not None:
            if not module.module_class.is_primitive:
                raise PRGAInternalError("Existing module named '{}' is not a primitive"
                        .format(name))
            return module
        if name == 'fraclut6':
            return self.context._modules.setdefault(name, FracturableLUT6(
                self.get_or_create_primitive('lut5', True),
                self.get_or_create_primitive('lut6', True)))
        elif name == 'fraclut6ff':
            return self.context._modules.setdefault(name, FracturableLUT6FF(
                self.get_or_create_primitive('lut5', True),
                self.get_or_create_primitive('lut6', True),
                self.get_or_create_primitive('flipflop', True),
                self.context.switch_library.get_or_create_switch(2, None, False)
                ))
        else:
            return super(BitchainPrimitiveLibrary, self).get_or_create_primitive(name, logical_only)

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Delegate for Bitchain-based configuration -------
# ----------------------------------------------------------------------------
class BitchainConfigCircuitryDelegate(ConfigBitchainLibraryDelegate, ConfigCircuitryDelegate):

    __slots__ = ['_bitchains', '_total_config_bits']
    def __init__(self, context):
        super(BitchainConfigCircuitryDelegate, self).__init__(context)
        self._bitchains = {}

    def __config_bit_offset_instance(self, hierarchy):
        total = 0
        for instance in hierarchy:
            config_bit_offsets = get_config_bit_offset(self.context, instance.parent)
            config_bit_offset = config_bit_offsets.get(instance.name)
            if config_bit_offset is None:
                return None
            total += config_bit_offset
        return total

    # == low-level API =======================================================
    @property
    def total_config_bits(self):
        """:obj:`int`: Total number of configuration bits."""
        try:
            return self._total_config_bits
        except AttributeError:
            raise PRGAInternalError("Total number of configuration bits not set yet.""")

    # -- implementing properties/methods required by superclass --------------
    @property
    def additional_template_search_paths(self):
        return (CONFIG_BITCHAIN_TEMPLATE_SEARCH_PATH, )

    def get_primitive_library(self, context):
        return BitchainPrimitiveLibrary(context)

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
        config_bit_base = self.__config_bit_offset_instance(hierarchical_instance)
        if config_bit_base is None:
            return tuple()
        primitive = hierarchical_instance[-1].model
        if primitive.primitive_class.is_iopad:
            if mode == 'outpad':
                return ('b' + str(config_bit_base), )
            else:
                return tuple()
        elif primitive.primitive_class.is_multimode:
            return tuple('b' + str(config_bit_base + bit) for bit in primitive.modes[mode].mode_enabling_bits)
        else:
            raise NotImplementedError

    def fasm_lut(self, hierarchical_instance):
        config_bit_base = self.__config_bit_offset_instance(hierarchical_instance)
        if config_bit_base is None:
            return ''
        return 'b{}[{}:0]'.format(str(config_bit_base),
                len(hierarchical_instance[-1].logical_pins['cfg_d']) - 1)

    def fasm_mux_for_intrablock_switch(self, source, sink, hierarchy):
        module = source.parent if source.net_type.is_port else source.parent.parent
        config_bit_base = 0 if not hierarchy else self.__config_bit_offset_instance(hierarchy)
        config_bit_offsets = get_config_bit_offset(self.context, module)
        path = get_switch_path(self.context, source, sink)
        retval = []
        for bit in path:
            config_bits = bit.index
            config_bit_offset = config_bit_offsets.get(bit.parent.name, None)
            if config_bit_offset is None:
                raise PRGAInternalError("No configuration circuitry for switch '{}'"
                        .format(bit.parent))
            config_bit_offset += config_bit_base
            while config_bits:
                if config_bits % 2 == 1:
                    retval.append('b' + str(config_bit_offset))
                config_bits = config_bits // 2
                config_bit_offset += 1
        return retval

    def fasm_features_for_routing_switch(self, hierarchical_switch_input):
        hierarchy, input_port = hierarchical_switch_input
        switch_instance = hierarchy[-1]
        hierarchy = hierarchy[:-1]
        module = hierarchy[-1].model
        config_bit_base = self.__config_bit_offset_instance(hierarchy)
        config_bit_offset = get_config_bit_offset(self.context, module).get(switch_instance.name)
        if config_bit_offset is None:
            raise PRGAInternalError("No configuration circuitry for switch '{}'"
                    .format(switch_instance))
        config_bits = input_port.index
        retval = []
        while config_bits:
            if config_bits % 2 == 1:
                retval.append('b' + str(config_bit_base + config_bit_offset))
            config_bits = config_bits // 2
            config_bit_offset += 1
        return tuple(iter(retval))

# ----------------------------------------------------------------------------
# -- Configuration Circuitry Injection Pass ----------------------------------
# ----------------------------------------------------------------------------
class InjectBitchainConfigCircuitry(Object, AbstractPass):
    """Inject bitchain configuration circuitry."""

    @property
    def key(self):
        return "config.injection"

    @property
    def passes_before_self(self):
        return ("completion", )

    @property
    def passes_after_self(self):
        return ("physical", "rtl", "vpr", "asicflow")

    def run(self, context):
        inject_config_chain(context.config_circuitry_delegate, context.top)
        context.config_circuitry_delegate._total_config_bits = get_config_bit_count(context, context.top)
        # clear out hierarchy cache
        del context._cache['util.hierarchy']
