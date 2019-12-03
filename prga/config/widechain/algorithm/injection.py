# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import RegularInstance
from prga.config.widechain.design.primitive import ConfigWidechain
from prga.util import Abstract

from abc import abstractproperty, abstractmethod

__all__ = ['ConfigWidechainLibraryDelegate',
        'inject_config_chain']

# ----------------------------------------------------------------------------
# -- Configuration Widechain Library Delegate --------------------------------
# ----------------------------------------------------------------------------
class ConfigWidechainLibraryDelegate(Abstract):
    """Configuration widechain library supplying configuration widechain modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def cfg_width(self):
        """:obj:`int`: Width of the config chain."""
        raise NotImplementedError

    @abstractmethod
    def get_or_create_widechain(self, width):
        """Get a configuration widechain module.

        Args:
            width (:obj:`int`):
        """
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Algorithms for Injecting Config Circuitry into Modules ------------------
# ----------------------------------------------------------------------------
def inject_config_chain(lib, module, top = True):
    """Inject configuration widechain into ``module`` and its sub-modules.
    
    Args:
        lib (`ConfigWidechainLibraryDelegate`):
        module (`AbstractModule`): The module in which configuration circuitry is to be injected
        top (:obj:`bool`): If set, widechain is instantiated and connected to other instances; otherwise,
            configuration ports are created and left to the module up in the hierarchy to connect
    """
    # Injection: Submodules have cfg_i (serial configuration input port) exclusive-or cfg_d (parallel
    # configuration input port)
    instances_requiring_serial_config_port = []
    parallel_config_sinks = []
    for instance in itervalues(module.logical_instances):
        if instance.module_class is ModuleClass.config:
            continue    # no configuration circuitry for config and extension module types
        if 'cfg_i' not in instance.logical_pins and 'cfg_d' not in instance.logical_pins:
            if instance.module_class not in (ModuleClass.primitive, ModuleClass.switch):
                inject_config_chain(lib, instance.model, False)
            else:
                continue
        if 'cfg_i' in instance.logical_pins:                    # check for serial ports
            # flush pending parallel ports
            for sink in parallel_config_sinks:
                widechain = module._add_instance(RegularInstance(module,
                    lib.get_or_create_widechain(len(sink)), 'cfg_chain_{}'.format(sink.parent.name)))
                sink.logical_source = widechain.logical_pins['cfg_d']
                instances_requiring_serial_config_port.append(widechain)
            parallel_config_sinks = []
            instances_requiring_serial_config_port.append(instance)
        elif 'cfg_d' in instance.logical_pins:                  # check for parallel ports
            parallel_config_sinks.append(instance.logical_pins['cfg_d'])
    if instances_requiring_serial_config_port or top:
        # flush pending parallel ports
        for sink in parallel_config_sinks:
            widechain = module._add_instance(RegularInstance(module,
                lib.get_or_create_widechain(len(sink)), 'cfg_chain_{}'.format(sink.parent.name)))
            sink.logical_source = widechain.logical_pins['cfg_d']
            instances_requiring_serial_config_port.append(widechain)
        if not instances_requiring_serial_config_port:
            return
        cfg_clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
        cfg_e = module._add_port(ConfigInputPort(module, 'cfg_e', 1))
        cfg_we = module._add_port(ConfigInputPort(module, 'cfg_we', 1))
        cfg_i = module._add_port(ConfigInputPort(module, 'cfg_i', lib.cfg_width))
        for instance in instances_requiring_serial_config_port:
            instance.logical_pins['cfg_clk'].logical_source = cfg_clk
            instance.logical_pins['cfg_e'].logical_source = cfg_e
            instance.logical_pins['cfg_we'].logical_source = cfg_we
            instance.logical_pins['cfg_i'].logical_source = cfg_i
            cfg_i = instance.logical_pins['cfg_o']
        module._add_port(ConfigOutputPort(module, 'cfg_o', lib.cfg_width)).logical_source = cfg_i
    elif parallel_config_sinks:
        cfg_pins = [bit for sink in parallel_config_sinks for bit in sink]
        cfg_d = module._add_port(ConfigInputPort(module, 'cfg_d', len(cfg_pins)))
        for source, sink in zip(cfg_d, cfg_pins):
            sink.logical_source = source
