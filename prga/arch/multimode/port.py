# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import NetClass
from prga.arch.net.bus import BaseInputPort, BaseOutputPort
from prga.arch.net.port import BaseCustomClockPort, BaseLeafInputPort, BaseLeafOutputPort

__all__ = ['MultimodeClockPort', 'MultimodeInputPort', 'MultimodeOutputPort',
        'ModeInputPort', 'ModeOutputPort']

# ----------------------------------------------------------------------------
# -- Multimode Clock Port ----------------------------------------------------
# ----------------------------------------------------------------------------
class MultimodeClockPort(BaseCustomClockPort):
    """Multimode module's clock port.

    Args:
        parent (`Multimode`): Parent module of this port
        name (:obj:`str`): Name of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.multimode

    @property
    def is_user_accessible(self):
        return True

# ----------------------------------------------------------------------------
# -- Multimode Input Port ----------------------------------------------------
# ----------------------------------------------------------------------------
class MultimodeInputPort(BaseLeafInputPort):
    """Multimode module's input port.

    Args:
        parent (`Multimode`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.multimode

    @property
    def is_user_accessible(self):
        return True

# ----------------------------------------------------------------------------
# -- Multimode Output Port ---------------------------------------------------
# ----------------------------------------------------------------------------
class MultimodeOutputPort(BaseLeafOutputPort):
    """Multimode module's output port.

    Args:
        parent (`Multimode`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
        combinational_sources (:obj:`Iterable` [:obj:`str` ]): Input ports in the parent primitive from which
            combinational paths exist to this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.multimode

    @property
    def is_user_accessible(self):
        return True

# ----------------------------------------------------------------------------
# -- Mode Input Port ---------------------------------------------------------
# ----------------------------------------------------------------------------
class ModeInputPort(BaseInputPort):
    """Multimode module's input port mapped into a mode.

    Args:
        parent (`Mode`): Parent mode of this port
        model (`MultimodeClockPort` or `MultimodeInputPort`): The port in the multimode module that is mapped to this
            port
    """

    __slots__ = ['_model']
    def __init__(self, parent, model):
        super(ModeInputPort, self).__init__(parent)
        self._model = model
        self.physical_cp = model

    # == low-level API =======================================================
    @property
    def model(self):
        """`MultimodeClockPort` or `MultimodeInputPort`: The port in the multimode module that is mapped to this
        port."""
        return self._model

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def net_class(self):
        return NetClass.mode

    @property
    def is_clock(self):
        return self._model.is_clock

    @property
    def is_user_accessible(self):
        return True

    @property
    def name(self):
        return self._model.name

    @property
    def key(self):
        return self._model.key

    @property
    def width(self):
        return self._model.width

# ----------------------------------------------------------------------------
# -- Mode Output Port --------------------------------------------------------
# ----------------------------------------------------------------------------
class ModeOutputPort(BaseOutputPort):
    """Multimode module's output port mapped into a mode.

    Args:
        parent (`Mode`): Parent mode of this port
        model (`MultimodeClockPort` or `MultimodeInputPort`): The port in the multimode module that is mapped to this
            port
    """

    __slots__ = ['_model']
    def __init__(self, parent, model):
        super(ModeOutputPort, self).__init__(parent)
        self._model = model
        self.physical_cp = model

    # == low-level API =======================================================
    @property
    def model(self):
        """`MultimodeClockPort` or `MultimodeInputPort`: The port in the multimode module that is mapped to this
        port."""
        return self._model

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def net_class(self):
        return NetClass.mode

    @property
    def is_user_accessible(self):
        return True

    @property
    def name(self):
        return self._model.name

    @property
    def key(self):
        return self._model.key

    @property
    def width(self):
        return self._model.width
