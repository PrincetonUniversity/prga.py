# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import NetType, ConstNetType
from prga.arch.net.abc import AbstractSourceBit
from prga.util import Object

__all__ = ['ConstBit', 'UNCONNECTED', 'ZERO', 'ONE']

# ----------------------------------------------------------------------------
# -- Const Net Bit -----------------------------------------------------------
# ----------------------------------------------------------------------------
class ConstBit(Object, AbstractSourceBit):
    """Constant net bits.
    
    Args:
        type_ (`ConstNetType`): The type of this constant net
    """

    __singletons = {}
    __slots__ = ['_type']

    # == internal API ========================================================
    def __new__(cls, type_):
        return cls.__singletons.setdefault(type_, super(ConstBit, cls).__new__(cls))

    def __init__(self, type_):
        self._type = type_

    def __deepcopy__(self, memo):
        return self

    def __getnewargs__(self):
        return (self._type, )

    def __str__(self):
        return self._type.name

    # -- implementing properties/methods required by superclass --------------
    @property
    def _is_static(self):
        return True

    @property
    def _static_cp(self):
        return self

    def _get_or_create_static_cp(self):
        return self

    # == low-level API =======================================================
    @property
    def const_net_type(self):
        """`ConstNetType`: Sub-type of this constant net."""
        return self._type

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return True

    @property
    def is_user_accessible(self):
        return False

    @property
    def physical_cp(self):
        return self

    @property
    def net_type(self):
        return NetType.const

UNCONNECTED = ConstBit.unconnected = ConstBit(ConstNetType.unconnected)
ZERO = ConstBit.zero = ConstBit(ConstNetType.zero)
ONE = ConstBit.one = ConstBit(ConstNetType.one)
