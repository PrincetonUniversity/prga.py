# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position
from prga.arch.net.common import PortDirection, NetClass
from prga.arch.module.module import AbstractModule
from prga.arch.module.instance import BaseInstance
from prga.arch.routing.common import AbstractRoutingNodeID
from prga.arch.routing.net import (RoutingNodeInputPort, RoutingNodeOutputPort, RoutingNodeInputPin,
        RoutingNodeOutputPin)
from prga.util import ReadonlyMappingProxy, Object
from prga.exception import PRGAInternalError

from abc import abstractmethod, abstractproperty
from copy import copy

__all__ = ['AbstractRoutingModule']

# ----------------------------------------------------------------------------
# -- Routing Node Ports Proxy ------------------------------------------------
# ----------------------------------------------------------------------------
class _RoutingNodePortsProxy(Object, Mapping):
    """Helper class for `AbstractRoutingModule.all_nodes` and `RoutingInstance.all_nodes` property."""

    __slots__ = ['nets']
    def __init__(self, nets):
        super(_RoutingNodePortsProxy, self).__init__()
        self.nets = nets

    def __getitem__(self, key):
        if not isinstance(key, AbstractRoutingNodeID):
            raise KeyError(key)
        try:
            if key.node_type.is_blockport_bridge:
                return self.nets[key]
            else:
                try:
                    return self.nets[key]
                except KeyError:
                    # search backward
                    node = copy(key)
                    for _ in range(key.section):
                        node -= 1
                        try:
                            return self.nets[node]
                        except KeyError:
                            pass
                    # search forward
                    node = copy(key)
                    for _ in range(key.prototype.length - key.section - 1):
                        node += 1
                        try:
                            return self.nets[node]
                        except KeyError:
                            pass
                    raise KeyError(key)
        except KeyError:
            raise KeyError(key)

    def __iter__(self):
        return filter(lambda key: isinstance(key, AbstractRoutingNodeID), self.nets)

    def __len__(self):
        return sum(1 for key in self.nets if isinstance(key, AbstractRoutingNodeID))

# ----------------------------------------------------------------------------
# -- Abstract Routing Module -------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractRoutingModule(AbstractModule):
    """Abstract base class for connection/switch boxes, tiles and arrays."""

    # == internal API ========================================================
    # -- properties/methods to be overriden by subclasses --------------------
    @abstractmethod
    def _validate_node(self, node, direction = None):
        """Internal method to validate if ``node`` is valid in this routing box.
        
        Args:
            node (`AbstractRoutingNodeID`):
            direction (`PortDirection`):

        Returns:
            direction (`PortDirection`):
        """
        raise NotImplementedError

    # == low-level API =======================================================
    def get_or_create_node(self, node, direction = None):
        """Get or create a routing node port for ``node``.

        Args:
            node (`AbstractRoutingNodeID`):
            direction (`PortDirection`): Hint for the direction of the port. Required when ``node`` does not hint the
                direction of the port
        """
        try:
            port = self.all_nodes[node]
            if direction not in (None, port.direction):
                raise PRGAInternalError("Direction hint '{}' conflicts with the direction of existing node '{}'"
                        .format(direction.name, node))
            return port
        except KeyError:
            direction = self._validate_node(node, direction)
            port = direction.case(RoutingNodeInputPort, RoutingNodeOutputPort)(self, node)
            return self._add_port(port)

    # -- properties/methods to be overriden by subclasses --------------------
    @property
    def all_nodes(self):
        """:obj:`Mapping` [`AbstractRoutingNodeID`, `AbstractRoutingNodePort` ]: A mapping from routing node IDs to
        routing node ports. Note that this property handles the equivalent routing node IDs well."""
        return _RoutingNodePortsProxy(self.all_ports)

# ----------------------------------------------------------------------------
# -- Base Class for Instances of Routing Module -----------------------------
# ----------------------------------------------------------------------------
class BaseRoutingInstance(BaseInstance):
    """Base class for instances of routing modules.

    Args:
        parent (`AbstractArrayElement`): Parent module of this instance
        model (`AbstractRoutingModule`): Model of this instance
        position (`Position`): Position of this instance in the parent module
    """

    __slots__ = ['_position']
    def __init__(self, parent, model, position):
        super(BaseRoutingInstance, self).__init__(parent, model)
        self._position = Position(*position)

    # == internal API ========================================================
    # -- implementing properties/methods required by superclass --------------
    def _create_pin(self, port):
        if port.net_class.is_node or port.net_class.is_io:
            return port.direction.case(RoutingNodeInputPin, RoutingNodeOutputPin)(self, port)
        else:
            return super(BaseRoutingInstance, self)._create_pin(port)

    # == low-level API =======================================================
    @property
    def position(self):
        """`Position`: Position of this instance in the parent module."""
        return self._position

    @property
    def all_nodes(self):
        """:obj:`Mapping` [`AbstractRoutingNodeID`, `AbstractRoutingNodePort` ]: A mapping from routing node IDs to
        routing node ports. Note that this property handles the equivalent routing node IDs well."""
        return _RoutingNodePortsProxy(self.all_pins)
