# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import NetClass
from prga.arch.net.abc import AbstractPort
from prga.arch.net.bus import BaseInputPort, BaseOutputPort, InputPin, OutputPin
from prga.arch.routing.common import SegmentBridgeType, SegmentID, SegmentBridgeID, BlockPortID

from abc import abstractproperty
from copy import copy

__all__ = ['RoutingNodeInputPort', 'RoutingNodeOutputPort',
        'RoutingNodeInputPin', 'RoutingNodeOutputPin']

# ----------------------------------------------------------------------------
# -- Abstract Routing Node Port ----------------------------------------------
# ----------------------------------------------------------------------------
class AbstractRoutingNodePort(AbstractPort):
    """Abstract routing node port."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def node_id(self):
        """`AbstractRoutingNodeID`: Node ID of this port."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.node

    @property
    def name(self):
        if self.node_id.node_type.is_blockport_bridge:
            return 'blkp_{}_{}{}{}{}_{}{}'.format(
                self.node_id.prototype.parent.name,
                'x' if self.node_id.position.x >= 0 else 'u', abs(self.node_id.position.x),
                'y' if self.node_id.position.y >= 0 else 'v', abs(self.node_id.position.y),
                ('{}_'.format(self.node_id.subblock) if self.node_id.prototype.parent.capacity > 1 else ''),
                self.node_id.prototype.name)
        else:
            prefix = ('sgmt' if self.node_id.node_type.is_segment else
                    self.node_id.bridge_type.switch(
                        sboxin_regular = 'sbir',
                        sboxin_cboxout = 'sbic',
                        sboxin_cboxout2 = 'sbid',
                        cboxin = 'cbi',
                        cboxout = 'cbo',
                        array_regular = 'arr',
                        array_cboxout = 'arc',
                        array_cboxout2 = 'ard'))
            return '{}_{}_{}{}{}{}{}{}'.format(
                    prefix,
                    self.node_id.prototype.name,
                    'x' if self.node_id.position.x >= 0 else 'u', abs(self.node_id.position.x),
                    'y' if self.node_id.position.y >= 0 else 'v', abs(self.node_id.position.y),
                    self.node_id.orientation.name[0],
                    ('_{}'.format(self.node_id.section) if self.node_id.prototype.length > 1 else ''))

    @property
    def width(self):
        return self.node_id.prototype.width

    @property
    def key(self):
        return self.node_id

    @property
    def is_user_accessible(self):
        return (self.node_id.node_type.is_segment or self.node_id.node_type.is_blockport_bridge or
                (self.node_id.node_type.is_segment_bridge and self.node_id.bridge_type in
                    (SegmentBridgeType.sboxin_regular, SegmentBridgeType.cboxin, SegmentBridgeType.cboxout)))

# ----------------------------------------------------------------------------
# -- Routing Node Input Port -------------------------------------------------
# ----------------------------------------------------------------------------
class RoutingNodeInputPort(BaseInputPort, AbstractRoutingNodePort):
    """Input port as a routing node.

    Args:
        parent (`AbstractRoutingModule`): Parent connection box, switch box, tile or array of this port
        node_id (`AbstractRoutingNodeID`): Node ID of this port
    """

    __slots__ = ['_node_id']
    def __init__(self, parent, node_id):
        super(RoutingNodeInputPort, self).__init__(parent)
        self._node_id = node_id

    # == low-level API =======================================================
    @property
    def node_id(self):
        """`AbstractRoutingNodeID`: Node ID of this port."""
        return self._node_id

# ----------------------------------------------------------------------------
# -- Routing Node Output Port ------------------------------------------------
# ----------------------------------------------------------------------------
class RoutingNodeOutputPort(BaseOutputPort, AbstractRoutingNodePort):
    """Output port as a routing node.

    Args:
        parent (`AbstractRoutingModule`): Parent connection box, switch box, tile or array of this port
        node_id (`AbstractRoutingNodeID`): Node ID of this port
    """

    __slots__ = ['_node_id']
    def __init__(self, parent, node_id):
        super(RoutingNodeOutputPort, self).__init__(parent)
        self._node_id = node_id

    # == low-level API =======================================================
    @property
    def node_id(self):
        """`AbstractRoutingNodeID`: Node ID of this port."""
        return self._node_id

# ----------------------------------------------------------------------------
# -- Routing Node Input Pin --------------------------------------------------
# ----------------------------------------------------------------------------
class RoutingNodeInputPin(InputPin):
    """Routing node input pin.

    Args:
        parent (`RoutingInstance`): parent instance of this port
        model (`RoutingNodeInputPort`): model of this pin
    """

    # == low-level API =======================================================
    @property
    def node_id(self):
        """`AbstractRoutingNodeID`: Node ID of this pin."""
        return self.model.node_id.move(self.parent.position)

# ----------------------------------------------------------------------------
# -- Routing Node Output Pin -------------------------------------------------
# ----------------------------------------------------------------------------
class RoutingNodeOutputPin(OutputPin):
    """Routing node output pin.

    Args:
        parent (`RoutingInstance`): parent instance of this port
        model (`RoutingNodeOutputPort`): model of this pin
    """

    # == low-level API =======================================================
    @property
    def node_id(self):
        """`AbstractRoutingNodeID`: Node ID of this pin."""
        return self.model.node_id.move(self.parent.position)
