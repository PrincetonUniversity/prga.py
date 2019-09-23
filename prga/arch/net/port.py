# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import NetClass
from prga.arch.net.bus import BaseClockPort, BaseInputPort, BaseOutputPort

__all__ = ['BaseCustomClockPort', 'BaseCustomInputPort', 'BaseCustomOutputPort',
        'BaseLeafInputPort', 'BaseLeafOutputPort',
        'ConfigClockPort', 'ConfigInputPort', 'ConfigOutputPort']

# ----------------------------------------------------------------------------
# -- Base Class for Clock Ports whose Name Is Customized ---------------------
# ----------------------------------------------------------------------------
class BaseCustomClockPort(BaseClockPort):
    """Base class for clock ports whose name is customized.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
    """

    __slots__ = ['_name']
    def __init__(self, parent, name):
        super(BaseCustomClockPort, self).__init__(parent)
        self._name = name

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

# ----------------------------------------------------------------------------
# -- Base Class for Input Ports whose Name and Width Are Customized ----------
# ----------------------------------------------------------------------------
class BaseCustomInputPort(BaseInputPort):
    """Base class for input ports whose name and width are customized.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
    """

    __slots__ = ['_name', '_width']
    def __init__(self, parent, name, width):
        super(BaseCustomInputPort, self).__init__(parent)
        self._name = name
        self._width = width

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

    @property
    def width(self):
        return self._width

# ----------------------------------------------------------------------------
# -- Base Class for Output Ports whose Name and Width Are Customized ---------
# ----------------------------------------------------------------------------
class BaseCustomOutputPort(BaseOutputPort):
    """Base class for output ports whose name and width are customized.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
    """

    __slots__ = ['_name', '_width']
    def __init__(self, parent, name, width):
        super(BaseCustomOutputPort, self).__init__(parent)
        self._name = name
        self._width = width

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

    @property
    def width(self):
        return self._width

# ----------------------------------------------------------------------------
# -- Base Class for Input Ports of Leaf Modules ------------------------------
# ----------------------------------------------------------------------------
class BaseLeafInputPort(BaseCustomInputPort):
    """Base class for input ports of leaf modules.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
    """

    __slots__ = ['_name', '_width', '_clock']
    def __init__(self, parent, name, width, clock = None):
        super(BaseLeafInputPort, self).__init__(parent, name, width)
        self._clock = clock

    # == low-level API =======================================================
    @property
    def clock(self):
        return self._clock

# ----------------------------------------------------------------------------
# -- Base Class for Output Ports of Leaf Modules -----------------------------
# ----------------------------------------------------------------------------
class BaseLeafOutputPort(BaseCustomOutputPort):
    """Base class for output ports of leaf modules.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
        combinational_sources (:obj:`Iterable` [:obj:`str` ]): Input ports in the parent module from which
            combinational paths exist to this port
    """

    __slots__ = ['_name', '_width', '_clock', '_combinational_sources']
    def __init__(self, parent, name, width, clock = None, combinational_sources = tuple()):
        super(BaseLeafOutputPort, self).__init__(parent, name, width)
        self._clock = clock
        self._combinational_sources = tuple(iter(combinational_sources))

    # == low-level API =======================================================
    @property
    def clock(self):
        return self._clock

    @property
    def combinational_sources(self):
        return self._combinational_sources

# ----------------------------------------------------------------------------
# -- Config Clock Port -------------------------------------------------------
# ----------------------------------------------------------------------------
class ConfigClockPort(BaseCustomClockPort):
    """Configuration module's clock port.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.config

    @property
    def is_user_accessible(self):
        return False

# ----------------------------------------------------------------------------
# -- Config Input Port -------------------------------------------------------
# ----------------------------------------------------------------------------
class ConfigInputPort(BaseLeafInputPort):
    """Configuration module's input port.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.config

    @property
    def is_user_accessible(self):
        return False

# ----------------------------------------------------------------------------
# -- Config Output Port ------------------------------------------------------
# ----------------------------------------------------------------------------
class ConfigOutputPort(BaseLeafOutputPort):
    """Configuration module's output port.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
        combinational_sources (:obj:`Iterable` [:obj:`str` ]): Input ports in the parent module from which
            combinational paths exist to this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.config

    @property
    def is_user_accessible(self):
        return False
