# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import NetClass
from prga.arch.net.port import BaseCustomClockPort, BaseLeafInputPort, BaseLeafOutputPort

__all__ = ['PrimitiveClockPort', 'PrimitiveInputPort', 'PrimitiveOutputPort']

# ----------------------------------------------------------------------------
# -- Primitive Clock Port ----------------------------------------------------
# ----------------------------------------------------------------------------
class PrimitiveClockPort(BaseCustomClockPort):
    """Primitive module's clock port.

    Args:
        parent (`AbstractPrimitive`): Parent primitive of this port
        name (:obj:`str`): Name of this port
        port_class (`PrimitivePortClass`): ``port_class`` attribute of this port in VPR's architecture description
    """

    __slots__ = ['_port_class']
    def __init__(self, parent, name, port_class = None):
        super(PrimitiveClockPort, self).__init__(parent, name)
        self._port_class = port_class

    # == low-level API =======================================================
    @property
    def port_class(self):
        return self._port_class

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.primitive

# ----------------------------------------------------------------------------
# -- Primitive Input Port ----------------------------------------------------
# ----------------------------------------------------------------------------
class PrimitiveInputPort(BaseLeafInputPort):
    """Primitive module's input port.

    Args:
        parent (`AbstractPrimitive`): Parent primitive of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
        port_class (`PrimitivePortClass`): ``port_class`` attribute of this port in VPR's architecture description
    """

    __slots__ = ['_port_class']
    def __init__(self, parent, name, width, clock = None, port_class = None):
        super(PrimitiveInputPort, self).__init__(parent, name, width, clock)
        self._port_class = port_class

    # == low-level API =======================================================
    @property
    def port_class(self):
        return self._port_class

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.primitive

# ----------------------------------------------------------------------------
# -- Primitive Output Port ---------------------------------------------------
# ----------------------------------------------------------------------------
class PrimitiveOutputPort(BaseLeafOutputPort):
    """Primitive module's output port.

    Args:
        parent (`AbstractPrimitive`): Parent primitive of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        clock (:obj:`str`): Clock of this port
        combinational_sources (:obj:`Iterable` [:obj:`str` ]): Input ports in the parent primitive from which
            combinational paths exist to this port
        port_class (`PrimitivePortClass`): ``port_class`` attribute of this port in VPR's architecture description
    """

    __slots__ = ['_port_class']
    def __init__(self, parent, name, width, clock = None, combinational_sources = tuple(), port_class = None):
        super(PrimitiveOutputPort, self).__init__(parent, name, width, clock, combinational_sources)
        self._port_class = port_class

    # == low-level API =======================================================
    @property
    def port_class(self):
        return self._port_class

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_class(self):
        return NetClass.primitive
