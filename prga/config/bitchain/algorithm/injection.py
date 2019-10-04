# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import RegularInstance
from prga.config.bitchain.design.primitive import ConfigBitchain
from prga.util import Abstract

from abc import abstractmethod

__all__ = ['ConfigBitchainLibraryDelegate', 'inject_config_chain']

# ----------------------------------------------------------------------------
# -- Configuration Bitchain Library Delegate ---------------------------------
# ----------------------------------------------------------------------------
class ConfigBitchainLibraryDelegate(Abstract):
    """Configuration bitchain library supplying configuration bitchain modules for instantiation."""

    @abstractmethod
    def get_or_create_bitchain(self, width):
        """Get a configuration bitchain module.

        Args:
            width (:obj:`int`):
        """
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Algorithms for Injecting Config Circuitry into Modules ------------------
# ----------------------------------------------------------------------------
def inject_config_chain(lib, module, top = True):
    """Inject configuration bitchain into ``module`` and its sub-modules.
    
    Args:
        lib (`ConfigBitchainLibraryDelegate`):
        module (`AbstractModule`): The module in which configuration circuitry is to be injected
        top (:obj:`bool`): If set, bitchain is instantiated and connected to other instances; otherwise, configuration
            ports are created and left to the module up in the hierarchy to connect
    """
    sinks = []
    instances_with_chains = []
    for instance in itervalues(module.all_instances):
        if instance.module_class in (ModuleClass.mode, ModuleClass.config, ModuleClass.extension):
            continue    # no configuration circuitry for mode, config, and extension module types
        cfg_d = instance.all_pins.get('cfg_d', None)
        if cfg_d is None and instance.module_class not in (ModuleClass.primitive, ModuleClass.switch):
            inject_config_chain(lib, instance.model, False)
            cfg_d = instance.all_pins.get('cfg_d', None)
        if cfg_d is not None:
            sinks.extend(cfg_d)
        if instance.all_pins.get('cfg_i', None) is not None:
            instances_with_chains.append(instance)
    if len(sinks) > 0:
        sources = tuple()
        if top:
            instance = module._add_instance(RegularInstance(module, lib.get_or_create_bitchain(len(sinks)), 'cfg_bitchain_inst'))
            sources = instance.all_pins['cfg_d']
            instances_with_chains.insert(0, instance)
        else:
            sources = module._add_port(ConfigInputPort(module, 'cfg_d', len(sinks)))
        for source, sink in zip(sources, sinks):
            sink.source = source
    if len(instances_with_chains) > 0:
        cfg_clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
        cfg_e = module._add_port(ConfigInputPort(module, 'cfg_e', 1))
        cfg_we = module._add_port(ConfigInputPort(module, 'cfg_we', 1))
        cfg_i = module._add_port(ConfigInputPort(module, 'cfg_i', 1))
        for instance in instances_with_chains:
            instance.all_pins['cfg_clk'].source = cfg_clk
            instance.all_pins['cfg_e'].source = cfg_e
            instance.all_pins['cfg_we'].source = cfg_we
            instance.all_pins['cfg_i'].source = cfg_i
            cfg_i = instance.all_pins['cfg_o']
        module._add_port(ConfigOutputPort(module, 'cfg_o', 1)).source = cfg_i
