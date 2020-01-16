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
import logging

_logger = logging.getLogger(__name__)

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
    def iter_positions_same_corner(cls, array, corner, majordim = None):
        # Route path (take ``corner == Corner.southwest`` as an example):
        #   +---+---+---+---+
        #   | v | < | v | < |
        #   +---+---+---+---+
        #   | v | ^ | v | ^ |
        #   +---+---+---+---+
        #   | v | ^ | < | ^ |
        #   +---+---+---+---+
        # < | > | > | > | > |
        #   +---+---+---+---+
        #     ^
        xdir, ydir = map(corner.dotx, Dimension)
        # determine the major dimension
        if majordim is None:
            majordim = Dimension.x
            if array.width % 2 == 1:
                if array.height % 2 == 1 or array.width == 1:
                    _logger.warning(
                            ("Array '{}' is not in a good shape for injecting configuration chain from {} to {}\n"
                                "\tGood shape requires the size to be even in at least one dimension and larger "
                                "than 1 in the other dimension")
                            .format(array, corner, corner))
                else:
                    majordim = Dimension.y
        elif majordim.case(array.width, array.height) % 2 == 1 or majordim.case(array.height, array.width) == 1:
            _logger.warning(
                    ("Array '{}' is not in a good shape for injecting configuration chain from {} to {} "
                        "with {} as the major dimension\n"
                        "\tGood shape requires the size to be even in the major dimension and larger "
                        "than 1 in the other dimension")
                    .format(array, corner, corner, majordim.name))
        # traverse positions
        if majordim.is_x:
            itx, ity = range(array.width), ydir.case(range(array.height - 1), range(1, array.height))
            for x in xdir.case(reversed(itx), itx):
                yield x, ydir.case(array.height - 1, 0)
            reversed_ = ydir.is_inc
            for x in xdir.case(itx, reversed(itx)):
                for y in reversed(ity) if reversed_ else ity:
                    yield x, y
                reversed_ = not reversed_
        else:
            itx, ity = xdir.case(range(array.width - 1), range(1, array.width)), range(array.height)
            for y in ydir.case(reversed(ity), ity):
                yield xdir.case(array.width - 1, 0), y
            reversed_ = xdir.is_inc
            for y in ydir.case(ity, reversed(ity)):
                for x in reversed(itx) if reversed_ else itx:
                    yield x, y
                reversed_ = not reversed_

    @classmethod
    def iter_positions_opposite_corner(cls, array, corner, majordim = None):
        # Route path (take ``corner == Corner.southwest`` as an example):
        #                 ^
        #   +---+---+---+---+
        #   | > | > | > | > |
        #   +---+---+---+---+
        #   | ^ | < | < | < |
        #   +---+---+---+---+
        #   | > | > | > | ^ |
        #   +---+---+---+---+
        #     ^
        # corner: entering corner
        xdir, ydir = map(corner.dotx, Dimension)
        # determine the major dimension
        if majordim is None:
            majordim = Dimension.x
            if array.width % 2 == 0:
                if array.height % 2 == 0:
                    _logger.warning(
                            ("Array '{}' is not in a good shape for injecting configuration chain from {} to {}\n"
                                "\tGood shape requires the size to be odd in at least one dimension")
                            .format(array, corner, corner.opposite))
                else:
                    majordim = Dimension.y
        elif majordim.case(array.width, array.height) % 2 == 0:
            _logger.warning(
                    ("Array '{}' is not in a good shape for injecting configuration chain from {} to {} "
                        "with {} as the major dimension\n"
                        "\tGood shape requires the size to be odd in the major dimension")
                    .format(array, corner, corner.opposite, majordim))
        # traverse positions
        itx, ity = range(array.width), range(array.height)
        if majordim.is_x:
            reversed_ = ydir.is_inc
            for x in xdir.case(reversed(itx), itx):
                for y in reversed(ity) if reversed_ else ity:
                    yield x, y
                reversed_ = not reversed_
        else:
            reversed_ = xdir.is_inc
            for y in ydir.case(reversed(ity), ity):
                for x in reversed(itx) if reversed_ else itx:
                    yield x, y
                reversed_ = not reversed_

    @classmethod
    def iter_positions_adjacent_corner(cls, array, entering_corner, exiting_corner, with_extra_zigzag = None):
        # Route path (take ``entering_corner == Corner.southwest, exiting_corner == Corner.southeast`` as an example):
        #   +---+---+---+---+
        #   | > | v | > | v |
        #   +---+---+---+---+
        #   | ^ | v | ^ | v |
        #   +---+---+---+---+
        #   | ^ | v | ^ | v |
        #   +---+---+---+---+
        #   | ^ | > | ^ | v |
        #   +---+---+---+---+
        #     ^           v
        # with_extra_zigzag:
        #   +---+---+---+---+---+
        #   | > | > | > | > | v |
        #   +---+---+---+---+---+
        #   | ^ | < | < | < | v |
        #   +---+---+---+---+---+
        #   | > | > | > | ^ | v |
        #   +---+---+---+---+---+
        #     ^               v
        xdir, ydir = map(entering_corner.dotx, Dimension)
        # determine the major dimension
        majordim = Dimension.y if exiting_corner.dotx(Dimension.x) is xdir else Dimension.x
        # we couldn't change the major dim, but let's see if we need to add an extra zigzag
        if with_extra_zigzag is None:
            with_extra_zigzag = False
            if majordim.case(array.width, array.height) % 2 == 1:
                if majordim.case(array.width, array.height) == 1 or majordim.case(array.height, array.width) % 2 == 0:
                    _logger.warning(
                            ("Array '{}' is not in a good shape for injecting configuration chain from {} to {}\n"
                                "\tGood shape requires either the size be even in the {} dimension, "
                                "or larger than 2 in the {} dimension and odd in the {} dimension")
                            .format(array, entering_corner, exiting_corner,
                                majordim.name, majordim.name, majordim.opposite.name))
                else:
                    with_extra_zigzag = True
        elif with_extra_zigzag and not (majordim.case(array.width, array.height) > 1
                and array.width % 2 == 1 and array.height % 2 == 1):
            _logger.warning(
                    ("Array '{}' is not in a good shape for injecting configuration chain from {} to {} "
                        "with extra zigzag"
                        "\tGood shape requires the size be odd in both dimensions and larger than 1 "
                        "in the {} dimension")
                    .format(array, entering_corner, exiting_corner, majordim.name))
        elif not with_extra_zigzag and majordim.case(array.width, array.height) % 2 == 1:
            _logger.warning(
                    ("Array '{}' is not in a good shape for injecting configuration chain from {} to {} "
                        "without extra zigzag"
                        "\tGood shape requires the size be even in the {} dimension")
                    .format(array, entering_corner, exiting_corner, majordim.name))
        # traverse positions
        if majordim.is_x:
            if with_extra_zigzag:
                itx, ity = xdir.case(range(1, array.width), range(array.width - 1)), range(array.height)
                reversed_ = xdir.is_inc
                for y in ydir.case(reversed(ity), ity):
                    for x in reversed(itx) if reversed_ else itx:
                        yield x, y
                    reversed_ = not reversed_
                for y in ydir.case(ity, reversed(ity)):
                    yield xdir.case(0, array.width - 1), y
            else:
                itx, ity = range(array.width), range(array.height)
                reversed_ = ydir.is_inc
                for x in xdir.case(reversed(itx), itx):
                    for y in reversed(ity) if reversed_ else ity:
                        yield x, y
                    reversed_ = not reversed_
        else:
            if with_extra_zigzag:
                itx, ity = range(array.width), ydir.case(range(1, array.height), range(array.height - 1))
                reversed_ = ydir.is_inc
                for x in xdir.case(reversed(itx), itx):
                    for y in reversed(ity) if reversed_ else ity:
                        yield x, y
                    reversed_ = not reversed_
                for x in xdir.case(itx, reversed(itx)):
                    yield x, ydir.case(0, array.height - 1)
            else:
                itx, ity = range(array.width), range(array.height)
                reversed_ = xdir.is_inc
                for y in ydir.case(reversed(ity), ity):
                    for x in reversed(itx) if reversed_ else itx:
                        yield x, y
                    reversed_ = not reversed_

    @classmethod
    def inject_config_chain(cls, lib, module, func_iter_instances = None, top = True):
        """Inject the actual configuration chain.

        Args:
            lib (`ConfigPacketizedChainLibraryDelegate`):
            module (`AbstractModule`):
            func_iter_instances (:obj:`Function` [:obj:`AbstractModule` ] -> :obj:`Iterable` [:obj:`AbstractInstance` ]): 
            top (:obj:`bool`):
        """
        # Injection: Submodules have cfg_i (serial configuration input port) exclusive-or cfg_d (parallel
        # configuration input port)
        parallel = []   # parallel configuration ports (cfg_d)
        serial = []     # (instance with serial port, if the instance should be added to ``module`` first)
        for instance in uno(func_iter_instances, lambda m: itervalues(m.logical_instances))(module):
            if instance.module_class is ModuleClass.config:
                continue    # skip configuration modules
            if 'cfg_i' not in instance.logical_pins and 'cfg_d' not in instance.logical_pins:
                if instance.module_class not in (ModuleClass.primitive, ModuleClass.switch):
                    cls.inject_config_chain(lib, instance.model, func_iter_instances, top = False)
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
    def inject_config_ctrl(cls, context, lib, module, func_iter_instances = None):
        """Inject the ctrl (router) module into ``module``.

        Args:
            context (`ArchitectureContext`):
            lib (`ConfigPacketizedChainLibraryDelegate`):
            module (`AbstractModule`):
            func_iter_instances (:obj:`Function` [:obj:`AbstractModule` ] -> :obj:`Iterable` [:obj:`AbstractInstance` ]): 
        """
        if not module.module_class.is_array:
            raise PRGAInternalError("'{}' is not an array. Configuration controller can only be injected into arrays"
                    .format(module.name))
        serial = []
        for instance in uno(func_iter_instances, lambda m: itervalues(m.logical_instances))(module):
            if 'cfg_i' in instance.logical_pins:
                serial.append( instance )
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
    def connect_config_chain(cls, lib, array, func_iter_instances = None):
        """Connect the sub-chains in ``array`` together. Each sub-chain is expected to have its own router/controller
        in it.

        Args:
            lib (`ConfigPacketizedChainLibraryDelegate`):
            array (`Array`):
            func_iter_instances (:obj:`Function` [:obj:`AbstractModule` ] -> :obj:`Iterable` [:obj:`AbstractInstance` ]): 
        """
        serial = []
        for instance in uno(func_iter_instances, lambda m: itervalues(m.logical_instances))(array):
            serial.append( instance )
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
