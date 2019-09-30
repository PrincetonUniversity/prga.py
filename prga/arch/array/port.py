# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position
from prga.arch.net.common import NetClass
from prga.arch.net.abc import AbstractPort
from prga.arch.net.bus import BaseInputPort, BaseOutputPort
from prga.arch.net.port import BaseGlobalInputPort
from prga.arch.routing.common import BlockPortID

from abc import abstractproperty

__all__ = ['ArrayExternalInputPort', 'ArrayExternalOutputPort', 'ArrayGlobalInputPort']

# ----------------------------------------------------------------------------
# -- Abstract Array External Port --------------------------------------------
# ----------------------------------------------------------------------------
class _AbstractArrayExternalPort(AbstractPort):
    """Abstract array external ports."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def node(self):
        """`BlockPortID`: ID of the block pin driven by this external input port."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.io

    @property
    def is_user_accessible(self):
        return False

    @property
    def name(self):
        if self.node.prototype.parent.capacity > 1:
            return 'ext_{}_x{}y{}_{}_{}'.format(self.node.prototype.parent.name,
                    self.node.position.x, self.node.position.y,
                    self.node.subblock, self.node.prototype.name)
        else:
            return 'ext_{}_x{}y{}_{}'.format(self.node.prototype.parent.name,
                    self.node.position.x, self.node.position.y,
                    self.node.prototype.name)

    @property
    def width(self):
        return self.node.prototype.width

    @property
    def key(self):
        return self.node

# ----------------------------------------------------------------------------
# -- Array External Input Port -----------------------------------------------
# ----------------------------------------------------------------------------
class ArrayExternalInputPort(BaseInputPort, _AbstractArrayExternalPort):
    """Array external input port.

    Args:
        parent (`AbstractArrayElement`): Parent module of this port
        node (`BlockPortID`): ID of the block pin driven by this external input port
    """

    __slots__ = ['_node']
    def __init__(self, parent, node):
        super(ArrayExternalInputPort, self).__init__(parent)
        self._node = node

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def node(self):
        """`BlockPortID`: ID of the block pin driven by this external input port."""
        return self._node

# ----------------------------------------------------------------------------
# -- Array External Output Port ----------------------------------------------
# ----------------------------------------------------------------------------
class ArrayExternalOutputPort(BaseOutputPort, _AbstractArrayExternalPort):
    """Array external output port.

    Args:
        parent (`AbstractArrayElement`): Parent module of this port
        node (`BlockPortID`): ID of the block pin driving this external output port
    """

    __slots__ = ['_node']
    def __init__(self, parent, node):
        super(ArrayExternalOutputPort, self).__init__(parent)
        self._node = node

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def node(self):
        """`BlockPortID`: ID of the block pin driven by this external input port."""
        return self._node

# ----------------------------------------------------------------------------
# -- Array Global Input Port -------------------------------------------------
# ----------------------------------------------------------------------------
class ArrayGlobalInputPort(BaseGlobalInputPort):
    """Global input port of an array.

    Args:
        parent (`AbstractArrayElement`): Parent module of this port
        global_ (`Global`): The global wire that this port is connected to
        name (:obj:`str`): Name of this port
    """
    pass
