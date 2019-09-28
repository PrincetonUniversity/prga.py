# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Orientation, Position
from prga.arch.net.common import NetClass
from prga.arch.net.abc import AbstractPort
from prga.arch.net.port import BaseCustomClockPort, BaseCustomInputPort, BaseCustomOutputPort, BaseGlobalInputPort

__all__ = ['ClusterClockPort', 'ClusterInputPort', 'ClusterOutputPort']

# ----------------------------------------------------------------------------
# -- Cluster Clock Port ------------------------------------------------------
# ----------------------------------------------------------------------------
class ClusterClockPort(BaseCustomClockPort):
    """Cluster's clock port.

    Args:
        parent (`Cluster`): Parent cluster of this port
        name (:obj:`str`): Name of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.cluster

    @property
    def is_user_accessible(self):
        return True

# ----------------------------------------------------------------------------
# -- Cluster Input Port ------------------------------------------------------
# ----------------------------------------------------------------------------
class ClusterInputPort(BaseCustomInputPort):
    """Cluster's input port.

    Args:
        parent (`Cluster`): Parent cluster of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Number of bits in this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.cluster

    @property
    def is_user_accessible(self):
        return True

# ----------------------------------------------------------------------------
# -- Cluster Output Port -----------------------------------------------------
# ----------------------------------------------------------------------------
class ClusterOutputPort(BaseCustomOutputPort):
    """Cluster's output port.

    Args:
        parent (`Cluster`): Parent cluster of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Number of bits in this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.cluster

    @property
    def is_user_accessible(self):
        return True

# ----------------------------------------------------------------------------
# -- Abstract Block Port -----------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractBlockPort(AbstractPort):
    """Abstract base class for block ports."""

    # == low-level API =======================================================
    @property
    def position(self):
        """`Position`: Position of this port in the block."""
        return Position(0, 0)

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.blockport

    @property
    def is_user_accessible(self):
        return True

# ----------------------------------------------------------------------------
# -- IO Block Global Input Port ----------------------------------------------
# ----------------------------------------------------------------------------
class IOBlockGlobalInputPort(BaseGlobalInputPort, AbstractBlockPort):
    """IO block global input port.

    Args:
        parent (`IOBlock`): Parent block of this port
        global_ (`Global`): The global wire this port is connected to 
        orientation (`Orientation`): Orientation of this port
        name (:obj:`str`): Name of this port
    """

    __slots__ = ['_orientation']
    def __init__(self, parent, global_, orientation = Orientation.auto, name = None):
        super(IOBlockGlobalInputPort, self).__init__(parent, global_, name)
        self._orientation = orientation

    # == low-level API =======================================================
    @property
    def orientation(self):
        """`Orientation`: Orientation of this port."""
        return self._orientation

# ----------------------------------------------------------------------------
# -- IO Block Input Port -----------------------------------------------------
# ----------------------------------------------------------------------------
class IOBlockInputPort(BaseCustomInputPort, AbstractBlockPort):
    """IO block non-global input port.

    Args:
        parent (`IOBlock`): Parent block of this port
        name (:obj:`str`): Name of this port
        width (:obj:`str`): Number of bits int this port
        orientation (`Orientation`): Orientation of this port
    """

    __slots__ = ['_orientation']
    def __init__(self, parent, name, width, orientation = Orientation.auto):
        super(IOBlockInputPort, self).__init__(parent, name, width)
        self._orientation = orientation

    # == low-level API =======================================================
    @property
    def orientation(self):
        """`Orientation`: Orientation of this port."""
        return self._orientation

# ----------------------------------------------------------------------------
# -- IO Block Output Port ----------------------------------------------------
# ----------------------------------------------------------------------------
class IOBlockOutputPort(BaseCustomOutputPort, AbstractBlockPort):
    """IO block non-global input port.

    Args:
        parent (`IOBlock`): Parent block of this port
        name (:obj:`str`): Name of this port
        width (:obj:`str`): Number of bits int this port
        orientation (`Orientation`): Orientation of this port
    """

    __slots__ = ['_orientation']
    def __init__(self, parent, name, width, orientation = Orientation.auto):
        super(IOBlockOutputPort, self).__init__(parent, name, width)
        self._orientation = orientation

    # == low-level API =======================================================
    @property
    def orientation(self):
        """`Orientation`: Orientation of this port."""
        return self._orientation

# ----------------------------------------------------------------------------
# -- IO Block External Input Port --------------------------------------------
# ----------------------------------------------------------------------------
class IOBlockExternalInputPort(BaseCustomInputPort):
    """IO block external input port.

    Args:
        parent (`IOBlock`): Parent block of this port
        name (:obj:`str`): Name of this port
        width (:obj:`str`): Number of bits int this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.io

    @property
    def is_user_accessible(self):
        return False

# ----------------------------------------------------------------------------
# -- IO Block External Output Port -------------------------------------------
# ----------------------------------------------------------------------------
class IOBlockExternalOutputPort(BaseCustomOutputPort):
    """IO block external output port.

    Args:
        parent (`IOBlock`): Parent block of this port
        name (:obj:`str`): Name of this port
        width (:obj:`str`): Number of bits int this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.io

    @property
    def is_user_accessible(self):
        return False

# ----------------------------------------------------------------------------
# -- Logic Block Global Input Port -------------------------------------------
# ----------------------------------------------------------------------------
class LogicBlockGlobalInputPort(BaseGlobalInputPort, AbstractBlockPort):
    """Logic block global input port.

    Args:
        parent (`LogicBlock`): Parent block of this port
        global_ (`Global`): The global wire this port is connected to 
        orientation (`Orientation`): Orientation of this port
        name (:obj:`str`): Name of this port
        position (`Position`): Position of this port in the block
    """

    __slots__ = ['_orientation', '_position']
    def __init__(self, parent, global_, orientation, name = None, position = Position(0, 0)):
        super(LogicBlockGlobalInputPort, self).__init__(parent, global_, name)
        self._orientation = orientation
        self._position = position

    # == low-level API =======================================================
    @property
    def orientation(self):
        """`Orientation`: Orientation of this port."""
        return self._orientation

    @property
    def position(self):
        """`Position`: Position of this port in the block."""
        return self._position

# ----------------------------------------------------------------------------
# -- Logic Block Input Port --------------------------------------------------
# ----------------------------------------------------------------------------
class LogicBlockInputPort(BaseCustomInputPort, AbstractBlockPort):
    """Logic block non-global input port.

    Args:
        parent (`LogicBlock`): Parent block of this port
        name (:obj:`str`): Name of this port
        width (:obj:`str`): Number of bits int this port
        orientation (`Orientation`): Orientation of this port
        position (`Position`): Position of this port in the block
    """

    __slots__ = ['_orientation', '_position']
    def __init__(self, parent, name, width, orientation, position = Position(0, 0)):
        super(LogicBlockInputPort, self).__init__(parent, name, width)
        self._orientation = orientation
        self._position = position

    # == low-level API =======================================================
    @property
    def orientation(self):
        """`Orientation`: Orientation of this port."""
        return self._orientation

    @property
    def position(self):
        """`Position`: Position of this port in the block."""
        return self._position

# ----------------------------------------------------------------------------
# -- Logic Block Output Port -------------------------------------------------
# ----------------------------------------------------------------------------
class LogicBlockOutputPort(BaseCustomOutputPort, AbstractBlockPort):
    """Logic block non-global input port.

    Args:
        parent (`LogicBlock`): Parent block of this port
        name (:obj:`str`): Name of this port
        width (:obj:`str`): Number of bits int this port
        orientation (`Orientation`): Orientation of this port
        position (`Position`): Position of this port in the block
    """

    __slots__ = ['_orientation', '_position']
    def __init__(self, parent, name, width, orientation, position = Position(0, 0)):
        super(LogicBlockOutputPort, self).__init__(parent, name, width)
        self._orientation = orientation
        self._position = position

    # == low-level API =======================================================
    @property
    def orientation(self):
        """`Orientation`: Orientation of this port."""
        return self._orientation

    @property
    def position(self):
        """`Position`: Position of this port in the block."""
        return self._position
