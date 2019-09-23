# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import RegularInstance
from prga.arch.module.module import AbstractModule
from prga.arch.block.port import ClusterClockPort, ClusterInputPort, ClusterOutputPort
from prga.exception import PRGAInternalError
from prga.util import Object, ReadonlySequenceProxy

from collections import OrderedDict
from itertools import product

try:
    from itertools import izip_longest as zip_longest
except ImportError:
    from itertools import zip_longest

import logging
_logger = logging.getLogger(__name__)
import traceback as tb

__all__ = ['Cluster']

# ----------------------------------------------------------------------------
# -- Cluster -----------------------------------------------------------------
# ----------------------------------------------------------------------------
class Cluster(Object, AbstractModule):
    """Intermediate-level module in a block.

    Args:
        name (:obj:`str`): Name of this cluster
    """

    __slots__ = ['_name', '_ports', '_instances', '_verilog_source', '_pack_patterns']
    def __init__(self, name):
        super(Cluster, self).__init__()
        self._name = name
        self._ports = OrderedDict()
        self._instances = OrderedDict()
        self._pack_patterns = []

    # == internal API ========================================================
    def __connect(self, source, sink, pack_pattern):
        if ((source.net_type.is_port and source.parent is not self) or
                (source.net_type.is_pin and source.parent.parent is not self)):
            raise PRGAInternalError("'{}' is not a net in module '{}'"
                    .format(source, self))
        if ((sink.net_type.is_port and sink.parent is not self) or
                (sink.net_type.is_pin and sink.parent.parent is not self)):
            raise PRGAInternalError("'{}' is not a net in module '{}'"
                    .format(sink, self))
        sink.add_user_sources( (source, ) )
        if pack_pattern and (source, sink) not in self._pack_patterns:
            self._pack_patterns.append( (source, sink) )

    # == low-level API =======================================================
    @property
    def pack_patterns(self):
        """:obj:`Sequence` [:obj:`tuple` [`AbstractSourceBit`, `AbstractSinkBit` ]]): A sequence of pack-pattern
        connections."""
        return ReadonlySequenceProxy(self._pack_patterns)

    # -- implementing properties/methods required by superclass --------------
    @property
    def all_ports(self):
        return self._ports

    @property
    def all_instances(self):
        return self._instances

    @property
    def name(self):
        return self._name

    @property
    def module_class(self):
        return ModuleClass.cluster

    @property
    def verilog_template(self):
        return 'module.tmpl.v'

    @property
    def verilog_source(self):
        try:
            return self._verilog_source
        except AttributeError:
            raise PRGAInternalError("Verilog source file not generated for module '{}' yet."
                    .format(self))

    @verilog_source.setter
    def verilog_source(self, source):
        self._verilog_source = source

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

    def instantiate(self, model, name):
        """Instantiate an instance of ``model`` and add to this module.

        Args:
            model (:obj:`AbstractModule`): A user-accessible module
            name (:obj:`str`): Name of the instance
        """
        if model.module_class not in (ModuleClass.primitive, ModuleClass.cluster):
            raise PRGAInternalError("Only primitives or clusters may be instantiated in a custer/block.")
        instance = RegularInstance(self, model, name)
        return self._add_instance(instance)

    def connect(self, sources, sinks, fully_connected = False, pack_pattern = False):
        """Connect a sequence of source net bits to a sequence of sink net bits.

        Args:
            sources (:obj:`Sequence` [`AbstractSourceBit` ]):
            sinks (:obj:`Sequence` [`AbstractSinkBit` ]):
            fully_connected (:obj:`bool`): Connections are created bit-wise by default. If ``fully_connected`` is set,
                connections are created in an all-to-all manner
            pack_pattern (:obj:`bool`): An advanced feature in VPR
        """
        sources = sources if isinstance(sources, Iterable) else (sources, )
        sinks = sinks if isinstance(sinks, Iterable) else (sinks, )
        if fully_connected:
            for source, sink in product(iter(sources), iter(sinks)):
                self.__connect(source, sink, pack_pattern)
        else:
            for source, sink in zip_longest(iter(sources), iter(sinks)):
                if source is None or sink is None:
                    _logger.warning("Number of sources and number of sinks don't match")
                    _logger.warning("\n" + "".join(tb.format_stack()))
                    return
                self.__connect(source, sink, pack_pattern)
