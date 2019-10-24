# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import PortDirection
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import BaseModule
from prga.arch.routing.common import AbstractRoutingNodeID, SegmentBridgeType
from prga.arch.routing.module import AbstractRoutingModule
from prga.exception import PRGAInternalError

from collections import OrderedDict
from itertools import product

try:
    from itertools import izip_longest as zip_longest
except ImportError:
    from itertools import zip_longest

import logging
_logger = logging.getLogger(__name__)
import traceback as tb

__all__ = ['ConnectionBox', 'SwitchBox']

# ----------------------------------------------------------------------------
# -- Routing Box Nodes Proxy --------------------------------------------------
# ----------------------------------------------------------------------------
class _RoutingBoxNodesProxy(Mapping):
    """A helper class for `AbstractRoutingBox.input_nodes`, `AbstractRoutingBox.output_nodes` properties."""

    __slots__ = ['box', 'direction']
    def __init__(self, box, direction):
        super(_RoutingBoxNodesProxy, self).__init__()
        self.box = box
        self.direction = direction

    def __filter(self, kv):
        return (isinstance(kv[0], AbstractRoutingNodeID) and
                kv[1].in_user_domain and kv[1].direction is self.direction)

    def __len__(self):
        return sum(1 for _ in filter(self.__filter, iteritems(self.box.all_nodes)))

    def __getitem__(self, key):
        if not isinstance(key, AbstractRoutingNodeID):
            raise KeyError(key)
        try:
            if key.node_type.is_block_bridge and self.box.module_class.is_connection_box:
                return self.box.all_nodes[key]
            elif key.node_type.is_segment_driver:
                if self.box.module_class.is_switch_box:
                    if self.direction is PortDirection.output:
                        return self.box.all_nodes[key]
                    else:
                        return self.box.all_nodes[key.to_bridge_id(bridge_type = SegmentBridgeType.sboxin_regular)]
                else:
                    if self.direction is PortDirection.output:
                        return self.box.all_nodes[key.to_bridge_id(bridge_type = SegmentBridgeType.cboxout)]
                    else:
                        return self.box.all_nodes[key.to_bridge_id(bridge_type = SegmentBridgeType.cboxin)]
            raise KeyError(key)
        except KeyError:
            raise KeyError(key)

    def __iter__(self):
        for key, _ in filter(self.__filter, iteritems(self.box.all_nodes)):
            if key.node_type.is_segment_bridge:
                yield key.to_driver_id()
            else:
                yield key

# ----------------------------------------------------------------------------
# -- Abstract Routing Box ----------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractRoutingBox(AbstractRoutingModule):
    """Abstract base class for routing boxes."""

    # == internal API ========================================================
    def _connect(self, source, sink):
        if not (source.parent is self and not source.is_sink and source.net_class.is_node and
                (source.in_user_domain or (source.bus.node.node_type.is_segment_bridge and
                    (source.bus.node.bridge_type.is_sboxin_cboxout or
                        source.bus.node.bridge_type.is_sboxin_cboxout2)))):
            raise PRGAInternalError("'{}' is not a user-accessible sink node in routing box '{}'"
                    .format(source, self))
        if not (sink.parent is self and sink.is_sink and sink.net_class.is_node and sink.in_user_domain):
            raise PRGAInternalError("'{}' is not a user-accessible source node in routing box '{}'"
                    .format(sink, self))
        sink.add_user_sources( (source, ) )

    # == high-level API ======================================================
    @property
    def input_nodes(self):
        """:obj:`Mapping` [`AbstractRoutingNodeID`, `AbstractRoutingNodePort` ]: A mapping from routing node ID to
        input routing node ports."""
        return _RoutingBoxNodesProxy(self, PortDirection.input_)

    @property
    def output_nodes(self):
        """:obj:`Mapping` [`AbstractRoutingNodeID`, `AbstractRoutingNodePort` ]: A mapping from routing node iD to
        output routing node ports."""
        return _RoutingBoxNodesProxy(self, PortDirection.output)

    def connect(self, sources, sinks, fully_connected = False):
        """Connect a sequence of source net bits to a sequence of sink net bits.

        Args:
            sources (:obj:`Sequence` [`AbstractSourceBit` ]):
            sinks (:obj:`Sequence` [`AbstractSinkBit` ]):
            fully_connected (:obj:`bool`): Connections are created bit-wise by default. If ``fully_connected`` is set,
                connections are created in an all-to-all manner
        """
        sources = sources if isinstance(sources, Iterable) else (sources, )
        sinks = sinks if isinstance(sinks, Iterable) else (sinks, )
        if fully_connected:
            for source, sink in product(iter(sources), iter(sinks)):
                self._connect(source, sink)
        else:
            for source, sink in zip_longest(iter(sources), iter(sinks)):
                if source is None or sink is None:
                    _logger.warning("Number of sources and number of sinks don't match")
                    _logger.warning("\n" + "".join(tb.format_stack()))
                    return
                self._connect(source, sink)

# ----------------------------------------------------------------------------
# -- Connection Box ----------------------------------------------------------
# ----------------------------------------------------------------------------
class ConnectionBox(BaseModule, AbstractRoutingBox):
    """Connection box.

    Args:
        name (:obj:`str`): Name of this module
        dimension (`Dimension`): Dimension of this module
    """

    __slots__ = ['_ports', '_instances', '_dimension']
    def __init__(self, name, dimension):
        super(ConnectionBox, self).__init__(name)
        self._ports = OrderedDict()
        self._instances = OrderedDict()
        self._dimension = dimension

    # == internal API ========================================================
    # -- implementing properties/methods required by superclass --------------
    def _validate_node(self, node, direction = None):
        if node.node_type.is_blockport_bridge:
            if direction is node.prototype.direction:
                raise PRGAInternalError("Invalid port direction '{}' for node '{}' in connection box '{}'"
                        .format(direction.name, node, self))
            return node.prototype.direction.opposite
        elif node.node_type.is_segment_bridge:
            if node.bridge_type.is_cboxin:
                if direction is PortDirection.output:
                    raise PRGAInternalError("Invalid port direction '{}' for node '{}' in connection box '{}'"
                            .format(direction.name, node, self))
                return PortDirection.input_
            elif node.bridge_type.is_cboxout:
                if direction is PortDirection.input_:
                    raise PRGAInternalError("Invalid port direction '{}' for node '{}' in connection box '{}'"
                            .format(direction.name, node, self))
                return PortDirection.output
        raise PRGAInternalError("Invalid node '{}' in connection box '{}'"
                .format(node, self))

    # == low-level API =======================================================
    @property
    def dimension(self):
        """`Dimension`: Dimension of this module."""
        return self._dimension

    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.connection_box

# ----------------------------------------------------------------------------
# -- Switch Box --------------------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchBox(BaseModule, AbstractRoutingBox):
    """Switch box.

    Args:
        name (:obj:`str`): Name of this module
    """

    __slots__ = ['_ports', '_instances']
    def __init__(self, name):
        super(SwitchBox, self).__init__(name)
        self._ports = OrderedDict()
        self._instances = OrderedDict()

    # == internal API ========================================================
    # -- implementing properties/methods required by superclass --------------
    def _validate_node(self, node, direction = None):
        if node.node_type.is_segment_driver:
            if direction is PortDirection.input_:
                raise PRGAInternalError("Invalid port direction '{}' for node '{}' in switch box '{}'"
                        .format(direction.name, node, self))
            return PortDirection.output
        elif node.node_type.is_segment_bridge:
            if node.bridge_type in (SegmentBridgeType.sboxin_regular, SegmentBridgeType.sboxin_cboxout,
                    SegmentBridgeType.sboxin_cboxout2):
                if direction is PortDirection.output:
                    raise PRGAInternalError("Invalid port direction '{}' for node '{}' in switch box '{}'"
                            .format(direction.name, node, self))
                return PortDirection.input_
        raise PRGAInternalError("Invalid node '{}' in switch box '{}'"
                .format(node, self))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.switch_box

    def get_or_create_node(self, node, direction = None):
        port = super(SwitchBox, self).get_or_create_node(node, direction)
        if node.node_type.is_segment_bridge and node.bridge_type in (SegmentBridgeType.sboxin_cboxout,
                SegmentBridgeType.sboxin_cboxout2):
            out = super(SwitchBox, self).get_or_create_node(node.to_driver_id())
            self.connect(port, out)
        return port
