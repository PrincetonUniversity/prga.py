# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import NetType, BusType, AbstractGenericNet, AbstractGenericBus
from ...util import Object
from ...exception import PRGATypeError, PRGAIndexError, PRGAInternalError

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
    __slots__ = ['_key']

    # == internal API ========================================================
    def __new__(cls, width = 1):
        if not isinstance(width, int) or width < 0:
            raise PRGATypeError("width", "non-negative int")
        key = (NetType.unconnected, width)
        try:
            return cls.__singletons[key]
        except KeyError:
            obj = super(Unconnected, cls).__new__(cls)
            obj._key = key
            return cls.__singletons.setdefault(key, obj)

    def __init__(self, width = 1):
        pass

    def __deepcopy__(self, memo):
        return self

    def __getnewargs__(self):
        return (len(self), )

    def __str__(self):
        return "Unconnected({})".format(len(self))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.unconnected

    @property
    def node(self):
        return self._key

    @property
    def parent(self):
        raise NotImplementedError

    @property
    def is_source(self):
        return True

    @property
    def is_sink(self):
        return False

    @property
    def name(self):
        return "{}'bx".format(len(self))

    def __len__(self):
        return self._key[1]

    def __getitem__(self, index):
        if isinstance(index, int):
            if index < 0 or index >= len(self):
                raise PRGAIndexError("Index out of range. Bus '{}' is {}-bit wide"
                        .format(self, len(self)))
            return type(self)()
        elif isinstance(index, slice):
            if index.step not in (None, 1):
                raise PRGAIndexError("'step' must be 1 when indexing a bus with a slice")
            stop = len(self) if index.stop is None else min(index.stop, len(self))
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
    __slots__ = ['_key']

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

        key = (NetType.const, value, width)
        try:
            return cls.__singletons[key]
        except KeyError:
            obj = super(Const, cls).__new__(cls)
            obj._key = key
            return cls.__singletons.setdefault(key, obj)

    def __init__(self, value, width = None):
        pass

    def __deepcopy__(self, memo):
        return self

    def __getnewargs__(self):
        return self._key[1:]

    def __str__(self):
        return "Const({})".format(self.name)

    # == low-level API =======================================================
    @property
    def value(self):
        """:obj:`int`: Value of this const net in little-endian."""
        return self._key[1]

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.const

    @property
    def node(self):
        return self._key

    @property
    def is_source(self):
        return True

    @property
    def is_sink(self):
        return False

    @property
    def name(self):
        f = "{}'h{{:0>{}x}}".format(len(self), len(self) // 4 + (0 if (len(self) % 4 == 0) else 1))
        return f.format(self.value)

    def __len__(self):
        return self._key[2]

    def __getitem__(self, index):
        if isinstance(index, int):
            if index < 0 or index >= len(self):
                raise PRGAIndexError("Index out of range. Bus '{}' is {}-bit wide"
                        .format(self, len(self)))
            return type(self)(1 if self.value & (1 << index) else 0)
        elif isinstance(index, slice):
            if index.step not in (None, 1):
                raise PRGAIndexError("'step' must be 1 when indexing a bus with a slice")
            stop = len(self) if index.stop is None else min(index.stop, len(self))
            start = 0 if index.start is None else max(index.start, 0)
            return type(self)(self.value >> start, stop - start)
        else:
            raise PRGATypeError("index", "int or slice")
