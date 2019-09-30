# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Dimension
from prga.arch.routing.common import SegmentBridgeType
from prga.arch.routing.module import AbstractRoutingModule
from prga.arch.array.common import ChannelCoverage
from prga.arch.array.port import ArrayGlobalInputPort
from prga.exception import PRGAInternalError
from prga.util import uno

from abc import abstractproperty

__all__ = ['AbstractArrayElement']

# ----------------------------------------------------------------------------
# -- Abstract Array Element --------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractArrayElement(AbstractRoutingModule):
    """Abstract base class for tiles and arrays."""

    # == internal API ========================================================
    # -- implementing properties/methods required by superclass --------------
    def _validate_node(self, node, direction = None):
        if node.node_type.is_blockport_bridge:
            if direction is None:
                raise PRGAInternalError("Unable to determine port direction for node '{}' in array element '{}'"
                        .format(node, self))
            return direction
        elif node.node_type.is_segment_bridge:
            if node.bridge_type in (SegmentBridgeType.array_regular, SegmentBridgeType.array_cboxout,
                    SegmentBridgeType.array_cboxout2):
                if direction is None:
                    raise PRGAInternalError("Unable to determine port direction for node '{}' in array element '{}'"
                            .format(node, self))
                return direction
        raise PRGAInternalError("Invalid node '{}' in array element '{}'"
                .format(node, self))

    # == low-level API =======================================================
    def covers_tile(self, position):
        """Test if ``position`` is covered by this array element.
        
        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
        """
        x, y = position
        return x >= 0 and x < self.width and y >= 0 and y < self.height

    def covers_channel(self, position, dimension):
        """Test if the ``dimension`` routing channel in ``position`` is covered by this array element.

        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
            dimension (`Dimension`):
        """
        x, y = position
        if dimension.is_x and x >= 0 and x < self.width:
            if y >= 0 and y < self.height - 1:
                return True
            elif y == -1:
                return self.channel_coverage.south
            elif y == self.height - 1:
                return self.channel_coverage.north
        elif dimension.is_y and y >= 0 and y < self.height:
            if x >= 0 and x < self.width - 1:
                return True
            elif x == -1:
                return self.channel_coverage.west
            elif x == self.width - 1:
                return self.channel_coverage.east
        return False

    def covers_sbox(self, position):
        """Test if the switch box at ``position`` is covered by this array element.

        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
        """
        return self.covers_channel(position, Dimension.x) and self.covers_channel(position, Dimension.y)

    def get_or_create_global_input(self, global_, name = None):
        """Get or create a global input port.

        Args:
            global_ (`Global`):
            name (:obj:`str`):
        """
        name = uno(name, global_.name)
        try:
            return self.all_ports[name]
        except KeyError:
            return self._add_port(ArrayGlobalInputPort(self, global_, name))

    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def width(self):
        """:obj:`int`: Width of this array element."""
        raise NotImplementedError

    @abstractproperty
    def height(self):
        """:obj:`int`: Height of this array element."""
        raise NotImplementedError

    @abstractproperty
    def channel_coverage(self):
        """`ChannelCoverage`: Which routing channels are covered by this array element."""
        raise NotImplementedError
