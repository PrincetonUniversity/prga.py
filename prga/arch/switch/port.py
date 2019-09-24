# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import NetClass
from prga.arch.net.port import BaseLeafInputPort, BaseLeafOutputPort

__all__ = ['SwitchInputPort', 'SwitchOutputPort']

# ----------------------------------------------------------------------------
# -- Switch Input Port -------------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchInputPort(BaseLeafInputPort):
    """Commonly-used switch input port.

    Args:
        parent (`AbstractSwitch`): Parent switch of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.switch

# ----------------------------------------------------------------------------
# -- Switch Output Port ------------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchOutputPort(BaseLeafOutputPort):
    """Commonly-used switch output port.

    Args:
        parent (`AbstractSwitch`): Parent switch of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.switch
