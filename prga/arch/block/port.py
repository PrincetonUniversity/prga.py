# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Orientation
from prga.arch.net.common import NetClass
from prga.arch.net.port import BaseCustomClockPort, BaseCustomInputPort, BaseCustomOutputPort

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

