# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Dimension
from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import RegularInstance
from prga.config.widechain.algorithm.bitstream import get_config_bit_count
from prga.util import Abstract
from prga.exception import PRGAInternalError

from abc import abstractproperty, abstractmethod
from itertools import chain

__all__ = ['ConfigWidechainLibraryDelegate', 'WidechainInjectionHelper',
        'inject_wide_chain', 'order_tile_instances']

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

    @abstractmethod
    def get_or_create_fifo(self, depth):
        """Get a configuration FIFO module.

        Args:
            depth (:obj:`int`):
        """
        raise NotImplementedError

    @abstractmethod
    def get_or_create_egen(self):
        """Get a configuration enable generator module."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Injection Helper --------------------------------------------------------
# ----------------------------------------------------------------------------
class WidechainInjectionHelper(Abstract):
    """A helper class to help `inject_wide_chain` work better."""

    @abstractmethod
    def inject_fifo(self, module):
        """:obj:`int`: Stage of the FIFO to be injected for ``module``. If a value larger than 0 is returned for
        ``module``, FIFO and padding bits will be injected into ``module``."""
        raise NotImplementedError

    @abstractmethod
    def inject_chain(self, module):
        """:obj:`bool`: If configuration chain should be injected into ``module``. This is overwritten by
        ``inject_fifo``, and forced if ``module`` has instances that require serial configuration ports."""
        raise NotImplementedError

    @abstractmethod
    def iterate_instances(self, module):
        """:obj:`Iterable` [:obj:`AbstractInstance` ]: Iterate ``module`` in a preferred order for config chain
        injection. Return ``None`` for the default behavior."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Algorithms for Injecting Config Circuitry into Modules ------------------
# ----------------------------------------------------------------------------
def inject_wide_chain(context, lib, module, helper = None):
    """Inject configuration widechain into ``module`` and its sub-modules.
    
    Args:
        context (`ArchitectureContext`):
        lib (`ConfigWidechainLibraryDelegate`):
        module (`AbstractModule`): The module in which configuration circuitry is to be injected
        helper (`WidechainInjectionHelper`):
    """
    # Injection: Submodules have cfg_i (serial configuration input port) exclusive-or cfg_d (parallel
    # configuration input port)
    instances_requiring_serial_config_port = []
    parallel_config_sinks = []
    try:
        instance_iterator = helper.iterate_instances(module)
        inject_fifo = helper.inject_fifo(module)
        inject_chain = helper.inject_chain(module)
    except :
        instance_iterator = None
        inject_fifo = 0
        inject_chain = False
    if instance_iterator is None:
        instance_iterator = itervalues(module.logical_instances)
    for instance in instance_iterator:
        if instance.module_class is ModuleClass.config:
            continue    # no configuration circuitry for config and extension module types
        if 'cfg_i' not in instance.logical_pins and 'cfg_d' not in instance.logical_pins:
            if instance.module_class not in (ModuleClass.primitive, ModuleClass.switch):
                inject_wide_chain(context, lib, instance.model, helper)
            else:
                continue
        if 'cfg_i' in instance.logical_pins:                    # check for serial ports
            # flush pending parallel ports
            for sink in parallel_config_sinks:
                widechain = module._add_instance(RegularInstance(module,
                    lib.get_or_create_widechain(len(sink)), 'cfg_chain_{}'.format(sink.parent.name)))
                sink.logical_source = widechain.logical_pins['cfg_d']
                instances_requiring_serial_config_port.append( (widechain, len(sink)) )
            parallel_config_sinks = []
            instances_requiring_serial_config_port.append(
                    (instance, get_config_bit_count(context, instance.model)) )
        elif 'cfg_d' in instance.logical_pins:                  # check for parallel ports
            parallel_config_sinks.append(instance.logical_pins['cfg_d'])
    if instances_requiring_serial_config_port or inject_fifo > 0 or inject_chain:
        # flush pending parallel ports
        for sink in parallel_config_sinks:
            widechain = module._add_instance(RegularInstance(module,
                lib.get_or_create_widechain(len(sink)), 'cfg_chain_{}'.format(sink.parent.name)))
            sink.logical_source = widechain.logical_pins['cfg_d']
            instances_requiring_serial_config_port.append( (widechain, len(sink)) )
        if not instances_requiring_serial_config_port:
            return
        cfg_clk = module._add_port(ConfigClockPort(module, 'cfg_clk'))
        cfg_i = module._add_port(ConfigInputPort(module, 'cfg_i', lib.cfg_width))
        cfg_o = module._add_port(ConfigOutputPort(module, 'cfg_o', lib.cfg_width))
        cfg_we = None
        cfg_bits = 0
        if inject_fifo > 1:
            egen = module._add_instance(RegularInstance(module,
                lib.get_or_create_egen(), 'cfg_egen_inst'))
            fifo = module._add_instance(RegularInstance(module,
                lib.get_or_create_fifo(inject_fifo), 'cfg_fifo_inst'))
            egen.logical_pins['cfg_empty'].logical_source = module._add_port(
                    ConfigInputPort(module, 'cfg_empty_prev', 1))
            egen.logical_pins['cfg_full'].logical_source = fifo.logical_pins['cfg_full']
            cfg_we = egen.logical_pins['cfg_e']
            module._add_port(ConfigOutputPort(module, 'cfg_rd_prev', 1)).logical_source = cfg_we
            fifo.logical_pins['cfg_clk'].logical_source = cfg_clk
            fifo.logical_pins['cfg_rst'].logical_source = module._add_port(ConfigInputPort(module, 'cfg_rst', 1))
            fifo.logical_pins['cfg_rd'].logical_source = module._add_port(ConfigInputPort(module, 'cfg_rd', 1))
            module._add_port(ConfigOutputPort(module, 'cfg_empty', 1)).logical_source = fifo.logical_pins['cfg_empty']
            cfg_o.logical_source = fifo.logical_pins['cfg_o']
            fifo.logical_pins['cfg_wr'].logical_source = cfg_we
            cfg_o = fifo.logical_pins['cfg_i']
        else:
            cfg_we = module._add_port(ConfigInputPort(module, 'cfg_we', 1))
        for instance, bits in instances_requiring_serial_config_port:
            instance.logical_pins['cfg_clk'].logical_source = cfg_clk
            instance.logical_pins['cfg_we'].logical_source = cfg_we
            instance.logical_pins['cfg_i'].logical_source = cfg_i
            cfg_i = instance.logical_pins['cfg_o']
            cfg_bits += bits
        padding = cfg_bits % lib.cfg_width
        if inject_fifo > 0 and padding > 0:
            padding = lib.cfg_width - padding
            padding_inst = module._add_instance(RegularInstance(module,
                lib.get_or_create_widechain(padding), 'cfg_chain_padding_'))
            padding_inst.logical_pins['cfg_clk'].logical_source = cfg_clk
            padding_inst.logical_pins['cfg_we'].logical_source = cfg_we
            padding_inst.logical_pins['cfg_i'].logical_source = cfg_i
            cfg_i = padding_inst.logical_pins['cfg_o']
        cfg_o.logical_source = cfg_i
    elif parallel_config_sinks:
        cfg_pins = [bit for sink in parallel_config_sinks for bit in sink]
        cfg_d = module._add_port(ConfigInputPort(module, 'cfg_d', len(cfg_pins)))
        for source, sink in zip(cfg_d, cfg_pins):
            sink.logical_source = source

# ----------------------------------------------------------------------------
# -- Algorithms for Determining the Order of Instances for Injection ---------
# ----------------------------------------------------------------------------
def _iterate_cboxes(tile, orientation, direction):
    """Iterate a column/row of connection boxes in ``tile``."""
    if orientation.dimension.is_y:
        y = orientation.direction.case(tile.height - 1, 0)
        for x in direction.case(range(tile.width), reversed(range(tile.width))):
            instance = tile.cbox_instances.get( ((x, y), Dimension.x) )
            if instance is not None:
                return instance
    else:
        x = orientation.direction.case(tile.width - 1, 0)
        for y in direction.case(range(tile.height), reversed(range(tile.height))):
            instance = tile.cbox_instances.get( ((x, y), Dimension.y) )
            if instance is not None:
                return instance

def order_tile_instances(tile, input_corner, output_corner):
    """Iterate instances in ``tile`` in an optimized order so the configuration chain flows from the
    ``input_corner`` to the ``output_corner`` without minimal long wires.

    Args:
        tile (`Tile`):
        input_corner (`Corner`):
        output_corner (`Corner`):
    """
    if input_corner is output_corner:               # same corner
        ori_y, ori_x = input_corner.decompose()
        return chain(_iterate_cboxes(tile, ori_y, ori_x.direction.opposite),
                _iterate_cboxes(tile, ori_x.opposite, ori_y.direction.opposite),
                itervalues(tile.block_instances),
                _iterate_cboxes(tile, ori_y.opposite, ori_x.direction),
                _iterate_cboxes(tile, ori_x, ori_y.direction))
    elif input_corner is output_corner.opposite:    # opposite corner
        ori_y, ori_x = input_corner.decompose()
        return chain(_iterate_cboxes(tile, ori_y, ori_x.direction.opposite),
                _iterate_cboxes(tile, ori_x.opposite, ori_y.direction.opposite),
                itervalues(tile.block_instances),
                _iterate_cboxes(tile, ori_x, ori_y.direction.opposite),
                _iterate_cboxes(tile, ori_y.opposite, ori_x.direction.opposite))
    else:                                           # adjacent corner
        ori_iy, ori_ix = input_corner.decompose()
        ori_oy, ori_ox = output_corner.decompose()
        if ori_iy is ori_oy:    # same y-dimensional orientation
            return chain(_iterate_cboxes(tile, ori_ix, ori_iy.direction.opposite),
                    _iterate_cboxes(tile, ori_iy.opposite, ori_ox.direction),
                    _iterate_cboxes(tile, ori_ox, ori_iy.direction),
                    itervalues(tile.block_instances),
                    _iterate_cboxes(tile, ori_iy, ori_ox.direction))
        else:                   # same x-dimensional orientation
            return chain(_iterate_cboxes(tile, ori_iy, ori_ix.direction.opposite),
                    _iterate_cboxes(tile, ori_ix.opposite, ori_oy.direction),
                    _iterate_cboxes(tile, ori_oy, ori_ix.direction),
                    itervalues(tile.block_instances),
                    _iterate_cboxes(tile, ori_ix, ori_oy.direction))
