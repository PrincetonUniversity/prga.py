# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import NetType, BusType, AbstractGenericNet
from prga.util import Object
from prga.exception import PRGATypeError, PRGAIndexError

__all__ = ['Unconnected', 'Const']

# ----------------------------------------------------------------------------
# -- Constant Nets -----------------------------------------------------------
# ----------------------------------------------------------------------------
class Unconnected(Object, AbstractGenericNet):
    """A constant net used as a driver of other nets, marking those nets as unconnected.
    
    Args:
        width (:obj:`int`): Number of bits in this bus
    """

    __singletons = {}
    __slots__ = ['_width']

    # == internal API ========================================================
    def __new__(cls, width = 1):
        if not isinstance(width, int) or width < 0:
            raise PRGATypeError("width", "non-negative int")
        obj = cls.__singletons.setdefault(width, super(Unconnected, cls).__new__(cls))
        obj._width = width
        return obj

    def __init__(self, width = 1):
        pass

    def __deepcopy__(self, memo):
        return self

    def __getnewargs__(self):
        return (self._width, )

    def __str__(self):
        return "Unconnected({})".format(self._width)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def bus_type(self):
        return BusType.nonref

    @property
    def net_type(self):
        return NetType.unconnected

    @property
    def is_source(self):
        return True

    @property
    def is_sink(self):
        return False

    @property
    def name(self):
        return "{}'bx".format(self._width)

    def __len__(self):
        return self._width

    def __getitem__(self, index):
        if isinstance(index, int):
            if index < 0 or index >= self._width:
                raise PRGAIndexError("Index out of range. Bus '{}' is {}-bit wide"
                        .format(self, len(self)))
            return type(self)()
        elif isinstance(index, slice):
            if index.step not in (None, 1):
                raise PRGAIndexError("'step' must be 1 when indexing a bus with a slice")
            stop = self._width if index.stop is None else min(index.stop, self._width)
            start = 0 if index.start is None else max(index.start, 0)
            return type(self)(max(stop - start, 0))
        else:
            raise PRGATypeError("index", "int or slice")

class Const(Object, AbstractGenericNet):
    """A constant net used as a driver of other nets, connecting those nets to constant low/high wires.

    Args:
        value (:obj:`int`): Value of this constant in little-endian
        width (:obj:`int`): Number of bits in this net
    """

    __singletons = {}
    __slots__ = ['_value', '_width']

    # == internal API ========================================================
    def __new__(cls, value, width = None):
        if not isinstance(value, int) or value < 0:
            raise PRGATypeError("value", "non-negative int")
        elif width is not None and not (isinstance(width, int) and width > 0):
            raise PRGATypeError("width", "positive int")

        if width is None:
            width = max(1, value.bit_length())
        else:
            value = value & ((1 << width) - 1)

        obj = cls.__singletons.setdefault((value, width), super(Const, cls).__new__(cls))
        obj._value = value
        obj._width = width
        return obj

    def __init__(self, value, width = None):
        pass

    def __deepcopy__(self, memo):
        return self

    def __getnewargs__(self):
        return (self._value, self._width)

    def __str__(self):
        return "Const({})".format(self.name)

    # == low-level API =======================================================
    @property
    def value(self):
        """:obj:`int`: Value of this const net in little-endian."""
        return self._value

    # -- implementing properties/methods required by superclass --------------
    @property
    def bus_type(self):
        return BusType.nonref

    @property
    def net_type(self):
        return NetType.const

    @property
    def is_source(self):
        return True

    @property
    def is_sink(self):
        return False

    @property
    def name(self):
        f = "{}'h{{:0>{}x}}".format(self._width, self._width // 4 + (0 if (self._width % 4 == 0) else 1))
        return f.format(self._value)

    def __len__(self):
        return self._width

    def __getitem__(self, index):
        if isinstance(index, int):
            if index < 0 or index >= self._width:
                raise PRGAIndexError("Index out of range. Bus '{}' is {}-bit wide"
                        .format(self, len(self)))
            return type(self)(1 if self._value & (1 << index) else 0)
        elif isinstance(index, slice):
            if index.step not in (None, 1):
                raise PRGAIndexError("'step' must be 1 when indexing a bus with a slice")
            stop = self._width if index.stop is None else min(index.stop, self._width)
            start = 0 if index.start is None else max(index.start, 0)
            return type(self)(self._value >> start, stop - start)
        else:
            raise PRGATypeError("index", "int or slice")
