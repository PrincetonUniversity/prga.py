# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Corner, Orientation, Dimension
from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import RegularInstance
from prga.config.packetizedchain.algorithm.stats import ConfigPacketizedChainStatsAlgorithms
from prga.util import Abstract, uno

from abc import abstractproperty, abstractmethod

__all__ = ['ConfigPacketizedChainLibraryDelegate', 'ConfigPacketizedChainInjectionAlgorithms']

# ----------------------------------------------------------------------------
# -- Packetized Chain Library Delegate ---------------------------------------
# ----------------------------------------------------------------------------
class ConfigPacketizedChainLibraryDelegate(Abstract):
    """Packetized chain library supplying configuration modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def config_width(self):
        """:obj:`int`: Width of the config chain."""
        raise NotImplementedError

    @abstractmethod
    def get_or_create_chain(self, width):
        """Get a configuration chain module.

        Args:
            width (:obj:`int`):
        """
        raise NotImplementedError

    @abstractmethod
    def get_or_create_ctrl(self):
        """Get the configuration ctrl module."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- A Holder Class For Algorithms -------------------------------------------
# ----------------------------------------------------------------------------
class ConfigPacketizedChainInjectionAlgorithms(object):
    """A holder class (not meant to be instantiated) for injection algorithms for packetized chain."""

    @classmethod
    def __flush_parallel_sinks(cls, lib, module, parallel, serial):
        for sink in parallel:
            chain = RegularInstance(module, lib.get_or_create_chain(len(sink)),
                    'cfgwc_inst_{}'.format(sink.parent.name))
            sink.logical_source = chain.logical_pins['cfg_d']
            serial.append( (chain, True) )
        del parallel[:]

    @classmethod
    def inject_config_chain(cls, lib, module, top = True):
        """Inject the actual configuration chain.

        Args:
            lib (`ConfigPacketizedChainLibraryDelegate`):
            module (`AbstractModule`):
        """
        # Injection: Submodules have cfg_i (serial configuration input port) exclusive-or cfg_d (parallel
        # configuration input port)
        parallel = []   # parallel configuration ports (cfg_d)
        serial = []     # (instance with serial port, if the instance should be added to ``module`` first)
        for instance in itervalues(module.logical_instances):
            if instance.module_class is ModuleClass.config:
                continue    # skip configuration modules
            if 'cfg_i' not in instance.logical_pins and 'cfg_d' not in instance.logical_pins:
                if instance.module_class not in (ModuleClass.primitive, ModuleClass.switch):
                    cls.inject_config_chain(lib, instance.model, False)
                else:
                    continue
            if 'cfg_i' in instance.logical_pins:                    # check for serial ports
                # flush pending parallel ports
                cls.__flush_parallel_sinks(lib, module, parallel, serial)
                serial.append( (instance, False) )
            elif 'cfg_d' in instance.logical_pins:                  # check for parallel ports
                parallel.append(instance.logical_pins['cfg_d'])
        if parallel:
            if serial or top:
                cls.__flush_parallel_sinks(lib, module, parallel, serial)
            else:
                cfg_pins = [bit for sink in parallel for bit in sink]
                cfg_d = module._add_port(ConfigInputPort(module, 'cfg_d', len(cfg_pins)))
                for source, sink in zip(cfg_d, cfg_pins):
                    sink.logical_source = source
                return
        if not serial:
            return
        cfg_clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
        cfg_e = module._add_port(ConfigInputPort(module, 'cfg_e', 1))
        cfg_we = module._add_port(ConfigInputPort(module, 'cfg_we', 1))
        cfg_i = module._add_port(ConfigInputPort(module, 'cfg_i', lib.config_width))
        for instance, inject in serial:
            if inject:
                module._add_instance(instance)
            instance.logical_pins['cfg_clk'].logical_source = cfg_clk
            instance.logical_pins['cfg_e'].logical_source = cfg_e
            instance.logical_pins['cfg_we'].logical_source = cfg_we
            instance.logical_pins['cfg_i'].logical_source = cfg_i
            cfg_i = instance.logical_pins['cfg_o']
        cfg_o = module._add_port(ConfigOutputPort(module, 'cfg_o', lib.config_width))
        cfg_o.logical_source = cfg_i

    @classmethod
    def __iter_cboxes_in_tile(cls, tile, serial, dim, fixed_x, moving_x):
        for x in moving_x:
            cbox = tile.cbox_instances.get( (dim.case( (x, fixed_x), (fixed_x, x) ), dim) )
            if cbox is not None and 'cfg_i' in cbox.logical_pins:
                serial.append( cbox )

    @classmethod
    def inject_config_ctrl(cls, context, lib, module, corner = Corner.southwest):
        """Inject the ctrl (router) module into ``module``.

        Args:
            context (`ArchitectureContext`):
            lib (`ConfigPacketizedChainLibraryDelegate`):
            module (`AbstractModule`):
            corner (`Corner`): The corner of ``module`` the configuration router is connected to
        """
        serial = []
        if module.module_class.is_array:    # ordering matters for array
            vori, hori = corner.decompose()
            for x in hori.case(east = reversed(range(-1, module.width)), west = range(-1, module.width)):
                for y in vori.case(north = reversed(range(-1, module.height)), south = range(-1, module.height)):
                    sbox = module.sbox_instances.get( (x, y) )
                    elem = module.element_instances.get( (x, y) )
                    for inst in hori.case(east = (sbox, elem), west = (elem, sbox)):
                        if inst is not None and 'cfg_i' in inst.logical_pins:
                            serial.append( inst )
        elif module.module_class.is_tile:   # ordering matters for tile, too
            south = Dimension.x, -1, range(module.width)
            east = Dimension.y, module.width - 1, range(module.height)
            north = Dimension.x, module.height - 1, reversed(range(module.width))
            west = Dimension.y, -1, reversed(range(module.height))
            for args in corner.case( (north, west, south, east),
                                     (west, south, east, north),
                                     (east, north, west, south),
                                     (south, east, north, west) ):
                cls.__iter_cboxes_in_tile(module, serial, *args)
            for inst in itervalues(module.block_instances):
                if inst is not None and 'cfg_i' in inst.logical_pins:
                    serial.append( inst )
        else:                               # ordering does not matter
            for inst in itervalues(module.logical_instances):
                if 'cfg_i' in inst.logical_pins:
                    serial.append( inst )
        if not serial:
            return
        total_bits = sum(ConfigPacketizedChainStatsAlgorithms.get_config_bitcount(context, inst.model)
                for inst in serial)
        remainder = total_bits % lib.config_width
        if remainder > 0:
            padding = module._add_instance(RegularInstance(module,
                lib.get_or_create_chain(lib.config_width - remainder), 'cfgwc_padding'))
            serial.append( padding )
        ctrl = module._add_instance(RegularInstance(module,
            lib.get_or_create_ctrl(), 'cfgwc_ctrlinst'))
        for port_name in ('cfg_pkt_val_i', 'cfg_pkt_data_i'): 
            port = ctrl.logical_pins[port_name]
            port.logical_source = module._add_port(ConfigInputPort(module, port_name, port.width))
        for port_name in ('cfg_pkt_val_o', 'cfg_pkt_data_o'):
            port = ctrl.logical_pins[port_name]
            module._add_port(ConfigOutputPort(module, port_name, port.width)).logical_source = port
        clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
        ctrl.logical_pins['cfg_clk'].logical_source = clk
        en = module._add_port(ConfigInputPort(module, 'cfg_e', 1))
        ctrl.logical_pins['cfg_e'].logical_source = clk
        we = ctrl.logical_pins['cfg_we']
        prev = ctrl.logical_pins['cfg_dout']
        for inst in serial:
            inst.logical_pins['cfg_clk'].logical_source = clk
            inst.logical_pins['cfg_e'].logical_source = en
            inst.logical_pins['cfg_we'].logical_source = we
            inst.logical_pins['cfg_i'].logical_source = prev
            prev = inst.logical_pins['cfg_o']
        ctrl.logical_pins['cfg_din'].logical_source = prev

    @classmethod
    def connect_config_chain(cls, lib, array, corner = Corner.southwest):
        """Connect the sub-chains in ``array`` together. Each sub-chain is expected to have its own router/controller
        in it.

        Args:
            lib (`ConfigPacketizedChainLibraryDelegate`):
            array (`Array`):
            corner (`Corner`):
        """
        serial = []
        vori, hori = corner.decompose()
        for x in hori.case(east = reversed(range(-1, array.width)), west = range(-1, array.width)):
            for y in vori.case(north = reversed(range(-1, array.height)), south = range(-1, array.height)):
                sbox = array.sbox_instances.get( (x, y) )
                elem = array.element_instances.get( (x, y) )
                for inst in hori.case(east = (sbox, elem), west = (elem, sbox)):
                    if inst is not None and 'cfg_pkt_val_i' in inst.logical_pins:
                        serial.append( inst )
        if not serial:
            return
        clk = array._add_port(ConfigClockPort(array, 'cfg_clk'))
        en = array._add_port(ConfigInputPort(array, 'cfg_e', 1))
        val_i = array._add_port(ConfigInputPort(array, 'cfg_pkt_val_i', 1))
        data_i = array._add_port(ConfigInputPort(array, 'cfg_pkt_data_i', lib.config_width))
        for inst in serial:
            inst.logical_pins["cfg_clk"].logical_source = clk
            inst.logical_pins["cfg_e"].logical_source = en
            inst.logical_pins["cfg_pkt_val_i"].logical_source = val_i
            inst.logical_pins["cfg_pkt_data_i"].logical_source = data_i
            val_i = inst.logical_pins["cfg_pkt_val_o"]
            data_i = inst.logical_pins["cfg_pkt_data_o"]
        array._add_port(ConfigOutputPort(array, 'cfg_pkt_val_o', 1)).logical_source = val_i
        array._add_port(ConfigOutputPort(array, 'cfg_pkt_data_o', lib.config_width)).logical_source = data_i
