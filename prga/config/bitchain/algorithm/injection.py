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

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
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
    # Injection: Intermediate-level modules have cfg_i (serial configuration input port) exclusive-or cfg_d (parallel
    # configuration input port
    instances_requiring_serial_config_port = []
    instances_requiring_parallel_config_port = []
    for instance in itervalues(module.all_instances):
        if instance.module_class in (ModuleClass.config, ModuleClass.extension):
            continue    # no configuration circuitry for config and extension module types
        if 'cfg_i' not in instance.all_pins and 'cfg_d' not in instance.all_pins:
            if instance.module_class not in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.extension):
                inject_config_chain(lib, instance.model, False)
            else:
                continue
        if 'cfg_i' in instance.all_pins:                    # check for serial ports
            # flush pending parallel ports
            for cfg_inst in instances_requiring_parallel_config_port:
                sink = cfg_inst.all_pins['cfg_d']
                bitchain = module._add_instance(RegularInstance(module,
                    lib.get_or_create_bitchain(len(sink)), 'cfg_chain_{}'.format(cfg_inst.name)))
                sink.source = bitchain.all_pins['cfg_d']
                instances_requiring_serial_config_port.append(bitchain)
            instances_requiring_parallel_config_port = []
            instances_requiring_serial_config_port.append(instance)
        elif 'cfg_d' in instance.all_pins:                  # check for parallel ports
            instances_requiring_parallel_config_port.append(instance)
    if instances_requiring_serial_config_port or top:
        # flush pending parallel ports
        for cfg_inst in instances_requiring_parallel_config_port:
            sink = cfg_inst.all_pins['cfg_d']
            bitchain = module._add_instance(RegularInstance(module,
                lib.get_or_create_bitchain(len(sink)), 'cfg_chain_{}'.format(cfg_inst.name)))
            sink.source = bitchain.all_pins['cfg_d']
            instances_requiring_serial_config_port.append(bitchain)
        if not instances_requiring_serial_config_port:
            return
        cfg_clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
        cfg_e = module._add_port(ConfigInputPort(module, 'cfg_e', 1))
        cfg_we = module._add_port(ConfigInputPort(module, 'cfg_we', 1))
        cfg_i = module._add_port(ConfigInputPort(module, 'cfg_i', 1))
        for instance in instances_requiring_serial_config_port:
            instance.all_pins['cfg_clk'].source = cfg_clk
            instance.all_pins['cfg_e'].source = cfg_e
            instance.all_pins['cfg_we'].source = cfg_we
            instance.all_pins['cfg_i'].source = cfg_i
            cfg_i = instance.all_pins['cfg_o']
        module._add_port(ConfigOutputPort(module, 'cfg_o', 1)).source = cfg_i
    elif instances_requiring_parallel_config_port:
        cfg_pins = [bit for instance in instances_requiring_parallel_config_port
                for bit in instance.all_pins['cfg_d']]
        cfg_d = module._add_port(ConfigInputPort(module, 'cfg_d', len(cfg_pins)))
        for source, sink in zip(cfg_d, cfg_pins):
            sink.source = source
