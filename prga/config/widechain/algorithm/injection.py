# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import RegularInstance
from prga.config.widechain.algorithm.stats import get_config_widechain_bitcount
from prga.util import Abstract, uno

from abc import abstractproperty, abstractmethod

__all__ = ['ConfigWidechainLibraryDelegate', 'inject_widechain']

# ----------------------------------------------------------------------------
# -- Configuration Widechain Library Delegate --------------------------------
# ----------------------------------------------------------------------------
class ConfigWidechainLibraryDelegate(Abstract):
    """Configuration widechain library supplying configuration widechain modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def config_width(self):
        """:obj:`int`: Width of the config chain."""
        raise NotImplementedError

    @abstractmethod
    def get_or_create_widechain(self, width):
        """Get a configuration widechain module.

        Args:
            width (:obj:`int`):
        """
        raise NotImplementedError

    @abstractmethod
    def get_or_create_ctrl(self, depth = 2):
        """Get a configuration ctrl module.
        
        Args:
            depth (:obj:`int`): The depth of the internal FIFO of this ctrl module.
        """
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Guide for Connecting Config Chains and Injecting Ctrl Modules -----------
# ----------------------------------------------------------------------------
class ConfigWidechainInjectionGuide(Abstract):
    """Helper class to guide ``inject_widechain`` where to inject ctrl modules, how to group config chains and the
    order of instances."""

    @abstractmethod
    def chain_groups(self, module):
        """Groups of instances with chains in ``module``.

        Args:
            module (`AbstractModule`):

        Returns:
            :obj:`Iterable` [:obj:`tuple` [:obj:`int`, :obj:`Iterable` [:obj:`tuple` [:obj:`int`, `AbstractInstance`
                ]]]]: An iterable of \(group ID, chain group\), each group is an iterable of \(subgroup ID, instance\)
        """
        raise NotImplementedError

    @abstractmethod
    def injection_level(self, module):
        """Determine the level of injection in ``module``.

        Args:
            module `AbstractModule`):
        
        Returns:
            :obj:`int`: ``2`` - connect FIFO-separated segments; ``1`` - connect and inject ctrl\(FIFO\) module; ``0``
                - inject and connect chains
        """
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Algorithms for Injecting Config Circuitry into Modules ------------------
# ----------------------------------------------------------------------------
def _flush_parallel_sinks(lib, module, parallel, serial):
    for sink in parallel:
        widechain = RegularInstance(module, lib.get_or_create_widechain(len(sink)),
                'cfgwc_inst_{}'.format(sink.parent.name))
        sink.logical_source = widechain.logical_pins['cfg_d']
        serial.append( (widechain, True) )
    del parallel[:]

def _groupname(name, group):
    return name if group is None else ('{}_cg{}'.format(name, group))

def _inject_widechain_level0(lib, module, top = True):
    """Inject configuration widechain into ``module`` and its sub-modules.
    
    Args:
        lib (`ConfigWidechainLibraryDelegate`):
        module (`AbstractModule`): The module in which configuration circuitry is to be injected
        top (:obj:`bool`): If set, config chain is always injected and serial config input/output port are not created
    """
    # Injection: Submodules have cfg_i (serial configuration input port) exclusive-or cfg_d (parallel
    # configuration input port)
    parallel_config_sinks = []
    instances_requiring_serial_config_port = []
    for instance in itervalues(module.logical_instances):
        if instance.module_class is ModuleClass.config:
            continue    # no configuration circuitry for config and extension module types
        if 'cfg_i' not in instance.logical_pins and 'cfg_d' not in instance.logical_pins:
            if instance.module_class not in (ModuleClass.primitive, ModuleClass.switch):
                _inject_widechain_level0(lib, instance.model, False)
            else:
                continue
        if 'cfg_i' in instance.logical_pins:                    # check for serial ports
            # flush pending parallel ports
            _flush_parallel_sinks(lib, module, parallel_config_sinks, instances_requiring_serial_config_port)
            instances_requiring_serial_config_port.append( (instance, False) )
        elif 'cfg_d' in instance.logical_pins:                  # check for parallel ports
            parallel_config_sinks.append(instance.logical_pins['cfg_d'])
    if parallel_config_sinks:
        if instances_requiring_serial_config_port or top:
            _flush_parallel_sinks(lib, module, parallel_config_sinks, instances_requiring_serial_config_port)
        else:
            cfg_pins = [bit for sink in parallel_config_sinks for bit in sink]
            cfg_d = module._add_port(ConfigInputPort(module, 'cfg_d', len(cfg_pins)))
            for source, sink in zip(cfg_d, cfg_pins):
                sink.logical_source = source
            return
    if not instances_requiring_serial_config_port:
        return
    cfg_clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
    cfg_e = module._add_port(ConfigInputPort(module, 'cfg_e', 1))
    cfg_we = module._add_port(ConfigInputPort(module, 'cfg_we', 1))
    cfg_i = module._add_port(ConfigInputPort(module, 'cfg_i', lib.config_width))
    for instance, inject in instances_requiring_serial_config_port:
        if inject:
            module._add_instance(instance)
        instance.logical_pins['cfg_clk'].logical_source = cfg_clk
        instance.logical_pins['cfg_e'].logical_source = cfg_e
        instance.logical_pins['cfg_we'].logical_source = cfg_we
        instance.logical_pins['cfg_i'].logical_source = cfg_i
        cfg_i = instance.logical_pins['cfg_o']
    cfg_o = module._add_port(ConfigOutputPort(module, 'cfg_o', lib.config_width))
    cfg_o.logical_source = cfg_i

def _inject_widechain_level1(context, lib, module, chain_head_iterator, group):
    cfg_clk = module.logical_ports.get('cfg_clk')
    cfg_e = module.logical_ports.get('cfg_e')
    cfg_we, cfg_data_head, cfg_data_tail = (None,) * 3
    chain_length = 0
    for cfg_i in chain_head_iterator:
        assert cfg_i.name.startswith('cfg_i')
        if cfg_we is None:       # head of chain, inject ctrl module
            if cfg_clk is None:
                cfg_clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
            if cfg_e is None:
                cfg_e = module._add_port(ConfigInputPort(module, 'cfg_e', 1))
            ctrl = module._add_instance(RegularInstance(module, lib.get_or_create_ctrl(),
                _groupname('cfg_ctrlinst', group)))
            ctrl.logical_pins['cfg_clk'].logical_source = cfg_clk
            ctrl.logical_pins['cfg_e'].logical_source = cfg_e
            for pin_name in ('cfg_wr', 'cfg_i', 'cfg_full_next'):
                pin = ctrl.logical_pins[pin_name]
                port = module._add_port(ConfigInputPort(module, _groupname(pin_name, group), pin.width))
                pin.logical_source = port
            for pin_name in ('cfg_full', 'cfg_o', 'cfg_wr_next'):
                pin = ctrl.logical_pins[pin_name]
                port = module._add_port(ConfigOutputPort(module, _groupname(pin_name, group), pin.width))
                port.logical_source = pin
            cfg_we = ctrl.logical_pins['cfg_data_we']
            cfg_data_head = ctrl.logical_pins['cfg_data_head']
            cfg_data_tail = ctrl.logical_pins['cfg_data_tail']
        instance = cfg_i.parent
        cfg_i.logical_source = cfg_data_head
        instance.logical_pins['cfg_clk'].logical_source = cfg_clk
        instance.logical_pins['cfg_e'].logical_source = cfg_e
        instance.logical_pins['cfg_we'].logical_source = cfg_we
        cfg_data_head = instance.logical_pins['cfg_o']
        chain_length += get_config_widechain_bitcount(context, instance.model).get(None, 0)
    if cfg_data_tail is None:
        return
    remainder = chain_length % lib.config_width
    if remainder != 0:  # inject padding
        instance = module._add_instance(RegularInstance(module,
            lib.get_or_create_widechain(lib.config_width - remainder),
            _groupname('cfgwc_padding', group)))
        instance.logical_pins['cfg_clk'].logical_source = cfg_clk
        instance.logical_pins['cfg_e'].logical_source = cfg_e
        instance.logical_pins['cfg_we'].logical_source = cfg_we
        instance.logical_pins['cfg_i'].logical_source = cfg_data_head
        cfg_data_head = instance.logical_pins['cfg_o']
    cfg_data_tail.logical_source = cfg_data_head

def _inject_widechain_level2(lib, module, chain_iterator, group, instance_proc):
    print( "Injecting for {} group.{}:".format(module, group))
    cfg_clk = module.logical_ports.get('cfg_clk')
    cfg_e = module.logical_ports.get('cfg_e')
    # FIFO interface or chain interface
    fifo_intf, chain_intf = False, False
    cfg_i = None
    # FIFO
    cfg_full, cfg_wr = None, None
    # chain
    cfg_we = None
    for subgroup, instance in chain_iterator:
        instance_proc(instance)
        cfg_i_cur = instance.logical_pins.get(_groupname('cfg_i', subgroup))
        if cfg_i_cur is None:
            continue
        print( "\tInstance {} sub-group.{}".format(instance, subgroup) )
        if cfg_clk is None:
            cfg_clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
        instance.logical_pins["cfg_clk"].logical_source = cfg_clk
        if cfg_e is None:
            cfg_e = module._add_port(ConfigInputPort(module, 'cfg_e', 1))
        instance.logical_pins["cfg_e"].logical_source = cfg_e
        # is it FIFO interface?
        cfg_full_cur = instance.logical_pins.get(_groupname('cfg_full', subgroup))
        if cfg_full_cur is not None:
            if chain_intf:
                raise PRGAInternalError("FIFO and chain interface co-exist in module '{}'".format(module))
            fifo_intf = True
            if cfg_i is None:
                cfg_i = module._add_port(ConfigInputPort(module, _groupname('cfg_i', group), lib.config_width + 1))
            if cfg_full is None:
                cfg_full = module._add_port(ConfigOutputPort(module, _groupname('cfg_full', group), 1))
            if cfg_wr is None:
                cfg_wr = module._add_port(ConfigInputPort(module, _groupname('cfg_wr', group), 1))
            cfg_full.logical_source = cfg_full_cur
            cfg_i_cur.logical_source = cfg_i
            instance.logical_pins[_groupname('cfg_wr', subgroup)].logical_source = cfg_wr
            cfg_full = instance.logical_pins[_groupname('cfg_full_next', subgroup)]
            cfg_i = instance.logical_pins[_groupname('cfg_o', subgroup)]
            cfg_wr = instance.logical_pins[_groupname('cfg_wr_next', subgroup)]
            continue
        # is it chain interface?
        cfg_we_cur = instance.logical_pins.get('cfg_we')
        if cfg_we_cur is None:
            raise PRGAInternalError(
                    "Serial input found but no supplementary interface found in instance '{}' in module '{}'"
                    .format(instance, module))
        elif fifo_intf:
            raise PRGAInternalError("FIFO and chain interface co-exist in module '{}'".format(module))
        elif subgroup is not None:
            raise PRGAInternalError("Chain interface found in instance '{}' in module '{}'. Sub-group not supported"
                    .format(instance, module))
        chain_intf = True
        if cfg_i is None:
            cfg_i = module._add_port(ConfigInputPort(module, 'cfg_i', lib.config_width))
        if cfg_we is None:
            cfg_we = module._add_port(ConfigInputPort(module, 'cfg_we', 1))
        cfg_we_cur.logical_source = cfg_we
        cfg_i_cur.logical_source = cfg_i
        cfg_i = instance.logical_pins['cfg_o']
    if fifo_intf:
        print( "... with FIFO interface" )
        cfg_full.logical_source = module._add_port(ConfigInputPort(module, _groupname('cfg_full_next', group), 1))
        cfg_o = module._add_port(ConfigOutputPort(module, _groupname('cfg_o', group), lib.config_width + 1))
        cfg_wr_next = module._add_port(ConfigOutputPort(module, _groupname('cfg_wr_next', group), 1))
        cfg_o.logical_source = cfg_i
        cfg_wr_next.logical_source = cfg_wr
    elif chain_intf:
        print( "... with chain interface" )
        cfg_o = module._add_port(ConfigOutputPort(module, _groupname('cfg_o', group), lib.config_width))
        cfg_o.logical_source = cfg_i

def inject_widechain(context, lib, module, guide, _visited = None):
    """Connect wide chains in ``module`` and inject FIFO/ctrl modules under the guidance of ``guide``.

    Args:
        context (`ArchitectureContext`):
        lib (`ConfigWidechainLibraryDelegate`):
        module (`AbstractModule`): The module in which sub-chains are to be connected
        guide (`ConfigWidechainInjectionGuide`):
        _visited (:obj:`set` [:obj:`str` ]):
    """
    _visited = uno(_visited, set())
    level = guide.injection_level(module)
    print( " x inject_widechain: {}, {}".format(module, level) )
    if level == 0:
        _inject_widechain_level0(lib, module, True)
    elif level == 1:
        for group, chain_iterator in iter(guide.chain_groups(module)):
            chain_heads = []
            for subgroup, instance in chain_iterator:
                if instance.model.name not in _visited:
                    inject_widechain(context, lib, instance.model, guide, _visited)
                cfg_i = instance.logical_pins.get(_groupname('cfg_i', subgroup))
                if cfg_i is not None:
                    chain_heads.append(cfg_i)
            _inject_widechain_level1(context, lib, module, chain_heads, group)
    else:
        for group, chain_iterator in iter(guide.chain_groups(module)):
            _inject_widechain_level2(lib, module, chain_iterator, group,
                    lambda x: inject_widechain(context, lib, x.model, guide, _visited) if x.model.name not in _visited
                    else None)
    _visited.add(module.name)
