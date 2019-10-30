# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import RegularInstance
from prga.arch.module.module import BaseModule
from prga.arch.block.port import ClusterClockPort, ClusterInputPort, ClusterOutputPort
from prga.exception import PRGAInternalError
from prga.util import ReadonlySequenceProxy, uno

from itertools import product
from collections import OrderedDict

try:
    from itertools import izip_longest as zip_longest
except ImportError:
    from itertools import zip_longest

import logging
_logger = logging.getLogger(__name__)
import traceback as tb

__all__ = ['Cluster']

# ----------------------------------------------------------------------------
# -- Cluster-like Module -----------------------------------------------------
# ----------------------------------------------------------------------------
class ClusterLike(BaseModule):
    """Base class for modules like a cluster.

    Args:
        name (:obj:`str`): Name of this cluster
    """

    __slots__ = ['_pack_patterns']
    def __init__(self, name):
        super(ClusterLike, self).__init__(name)
        self._pack_patterns = {}

    def __net_id(self, bit):
        return (None if bit.net_type.is_port else bit.parent.key, bit.bus.key, bit.index)

    # == internal API ========================================================
    def _validate_model(self, model):
        """Validate if ``model`` can be instantiate in this module."""
        if model.module_class not in (ModuleClass.primitive, ModuleClass.cluster):
            raise PRGAInternalError("Only primitives or clusters may be instantiated in a custer/block.")

    def _connect(self, source, sink, pack_pattern = None):
        if ((source.net_type.is_port and source.parent is not self) or
                (source.net_type.is_pin and source.parent.parent is not self) or
                source.is_sink or not source.in_user_domain):
            raise PRGAInternalError("'{}' is not a source in the user domain in module '{}'"
                    .format(source, self))
        if ((sink.net_type.is_port and sink.parent is not self) or
                (sink.net_type.is_pin and sink.parent.parent is not self) or
                not sink.is_sink or not sink.in_user_domain):
            raise PRGAInternalError("'{}' is not a sink in the user domain in module '{}'"
                    .format(sink, self))
        sink.add_user_sources( (source, ) )
        if pack_pattern is not None:
            self._pack_patterns.setdefault((self.__net_id(source), self.__net_id(sink)), set()).add(pack_pattern)

    # == low-level API =======================================================
    def get_pack_patterns(self, source, sink):
        """Get the pack patterns in which the connection from ``source`` to ``sink`` is part of.

        Args:
            source (`AbstractSourceBit`):
            sink (`AbstractSinkBit`):

        Returns:
            :obj:`Sequence` [:obj:`str` ]:
        """
        pack_patterns = self._pack_patterns.get((self.__net_id(source), self.__net_id(sink)))
        if pack_patterns:
            return tuple(iter(pack_patterns))
        else:
            return tuple()

    def auto_connect(self, instance, skip_pins = None, quiet = False):
        """Auto connect all pins of ``instance`` to ports with the same key of this module.
        
        Args:
            instance (`AbstractInstance`):
            skip_pins (:obj:`Container`): A set of pin keys which should be skipped
            quiet (:obj:`bool`): If set, skip if no matching port is found for a pin. Otherwise, error is raised
        """
        skip_pins = uno(skip_pins, set())
        if instance.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent module of instance '{}'"
                    .format(self, instance))
        for key, pin in iteritems(instance.pins):
            if key in skip_pins:
                continue
            port = self.ports.get(key)
            if port is None:
                if not quiet:
                    raise PRGAInternalError("No matching port is found in module '{}' for pin '{}'"
                            .format(self, pin))
                continue
            elif port.direction is not pin.direction:
                if not quiet:
                    raise PRGAInternalError(("Match found for pin '{}' in module '{}', "
                        "but the matched port '{}' is an {} (the pin is an {})")
                        .format(pin, self, port, port.direction.case('input', 'output'),
                            pin.direction.case('input', 'output')))
                continue
            elif port.width != pin.width:
                if not quiet:
                    raise PRGAInternalError(("Match found for pin '{}' in module '{}', "
                        "but the matched port '{}' is {}-bit wide (the pin is {}-bit wide)")
                        .format(pin, self, port, port.width, pin.width))
                continue
            elif port.direction.is_input:
                self.connect(port, pin)
            else:
                self.connect(pin, port)

    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return 'module.tmpl.v'

    # == high-level API ======================================================
    def instantiate(self, model, name):
        """Instantiate an instance of ``model`` and add to this module.

        Args:
            model (:obj:`AbstractModule`): A user-accessible module
            name (:obj:`str`): Name of the instance
        """
        self._validate_model(model)
        instance = RegularInstance(self, model, name)
        return self._add_instance(instance)

    def connect(self, sources, sinks, fully_connected = False, pack_pattern = None):
        """Connect a sequence of source net bits to a sequence of sink net bits.

        Args:
            sources (:obj:`Sequence` [`AbstractSourceBit` ]):
            sinks (:obj:`Sequence` [`AbstractSinkBit` ]):
            fully_connected (:obj:`bool`): Connections are created bit-wise by default. If ``fully_connected`` is set,
                connections are created in an all-to-all manner
            pack_pattern (:obj:`str`): An advanced feature in VPR. This is the name of the pack pattern
        """
        sources = sources if isinstance(sources, Iterable) else (sources, )
        sinks = sinks if isinstance(sinks, Iterable) else (sinks, )
        if fully_connected:
            for source, sink in product(iter(sources), iter(sinks)):
                self._connect(source, sink, pack_pattern)
        else:
            for source, sink in zip_longest(iter(sources), iter(sinks)):
                if source is None or sink is None:
                    _logger.warning("Number of sources and number of sinks don't match")
                    _logger.warning("\n" + "".join(tb.format_stack()))
                    return
                self._connect(source, sink, pack_pattern)

# ----------------------------------------------------------------------------
# -- Cluster -----------------------------------------------------------------
# ----------------------------------------------------------------------------
class Cluster(ClusterLike):
    """Intermediate-level module in a block.

    Args:
        name (:obj:`str`): Name of this cluster
    """

    __slots__ = ['_ports', '_instances']
    def __init__(self, name):
        super(Cluster, self).__init__(name)
        self._ports = OrderedDict()
        self._instances = OrderedDict()

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.cluster

    # == high-level API ======================================================
    def create_clock(self, name):
        """Create and add a clock input port to this cluster.

        Args:
            name (:obj:`str`): Name of this clock
        """
        return self._add_port(ClusterClockPort(self, name))

    def create_input(self, name, width):
        """Create and add an input port to this cluster.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in this port
        """
        return self._add_port(ClusterInputPort(self, name, width))

    def create_output(self, name, width):
        """Create and add an output port to this cluster.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in this port
        """
        return self._add_port(ClusterOutputPort(self, name, width))
