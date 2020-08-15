# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Common enums and abstract base class for nets."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...util import Enum, Abstract, uno
from ...exception import PRGAIndexError, PRGATypeError

from abc import abstractproperty, abstractmethod

__all__ = ["NetType", "PortDirection", "Const"]

# ----------------------------------------------------------------------------
# -- Net Type ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class NetType(Enum):
    """Enum type for nets and net references."""

    # persistent net types
    const = 0           #: constant-value nets
    port = 1            #: port (input/output of a module) buses
    pin = 2             #: pin (input/output of an instance in a module) buses
    bit = 3             #: one single bit in a bus

    # references
    hierarchical = 4    #: hierarchical pin buses
    slice_ = 5          #: consecutive subsets (slices) of a bus
    concat = 6          #: concatenations of buses and/or subsets

    @property
    def is_reference(self):
        """:obj:`bool`: Test if this type is a reference."""
        return self in (NetType.hierarchical, NetType.slice_, NetType.concat)

# ----------------------------------------------------------------------------
# -- Port Direction ----------------------------------------------------------
# ----------------------------------------------------------------------------
class PortDirection(Enum):
    """Enum type for port/pin directions."""
    input_ = 0  #: input direction
    output = 1  #: output direction

    @property
    def opposite(self):
        """The opposite of the this direction.

        Returns:
            `PortDirection`: the enum value of the opposite direction.
        """
        return self.case(PortDirection.output, PortDirection.input_)

# ----------------------------------------------------------------------------
# -- Abstract Net ------------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractNet(Abstract, Sequence):
    """Abstract class for all nets and net references."""

    @abstractproperty
    def net_type(self):
        """`NetType`: Type of the net."""
        raise NotImplementedError

    def _auto_index(self, index):
        l = len(self)
        if isinstance(index, int):
            if index < -l or index >= l:
                raise PRGAIndexError("Index out of range. {} is {}-bit wide".format(self, l))
            elif index < 0:
                return slice(l + index, l + index + 1)
            else:
                return slice(index, index + 1)
        elif isinstance(index, slice):
            if index.step is not None:
                raise PRGAIndexError("'step' must be ``None`` when indexing a net with a slice")
            elif index.stop is not None and index.start is not None and index.stop <= index.start:
                if not 0 <= index.stop <= index.start < l:
                    raise PRGAIndexError("Index out of range. {} is {}-bit wide".format(self, l))
                # Verilog style slicing
                return slice(index.stop, index.start + 1)
            else:
                # Python-style slicing
                start, stop = map(lambda v: max(0, min(l, l + v if v < 0 else v)),
                        (uno(index.start, 0), uno(index.stop, l)))
                return slice(start, stop)
        else:
            raise PRGATypeError("index", "int or slice")

# ----------------------------------------------------------------------------
# -- Abstract Non-Reference Net ----------------------------------------------
# ----------------------------------------------------------------------------
class AbstractNonReferenceNet(AbstractNet):
    """Abstract class for all non-reference nets."""

    @abstractproperty
    def is_source(self):
        """:obj:`bool`: Test if this net can be used as drivers of other nets."""
        raise NotImplementedError

    @abstractproperty
    def is_sink(self):
        """:obj:`bool`: Test if this net can be driven by other nets."""
        raise NotImplementedError

    @abstractproperty
    def is_clock(self):
        """:obj:`bool`: Test if this net is part of a clock network."""
        raise NotImplementedError

    @abstractproperty
    def parent(self):
        """`Module`: Parent module of this net."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Constant Nets -----------------------------------------------------------
# ----------------------------------------------------------------------------
class Const(AbstractNonReferenceNet):
    """Constant-value nets used as tie-high/low or unconnected status marker for sinks.

    Args:
        value (:obj:`int`): Value of this constant. Use ``None`` to represent "unconnected"
        width (:obj:`int`): Number of bits in this net
    """

    __singletons = {}
    __slots__ = ['_value', '_width']

    # == internal API ========================================================
    def __new__(cls, value = None, width = None):
        if not (value is None or (isinstance(value, int) and value >= 0)):
            raise PRGATypeError("value", "non-negative int")
        elif width is not None and not (isinstance(width, int) and width >= 0):
            raise PRGATypeError("width", "non-negative int")

        if width is None:
            if value is None:
                width = 0
            else:
                width = max(1, value.bit_length())
        elif value is not None:
            value = value & ((1 << width) - 1)

        try:
            return cls.__singletons[value, width]
        except KeyError:
            obj = super(Const, cls).__new__(cls)
            obj._value = value
            obj._width = width
            return cls.__singletons.setdefault( (value, width), obj )

    def __init__(self, value = None, width = None):
        pass

    def __deepcopy__(self, memo):
        return self

    def __getnewargs__(self):
        return (self._value, self._width)

    def __repr__(self):
        if self.value is None:
            return "Unconnected({})".format(len(self))
        else:
            return "Const({}'h{:x})".format(len(self), self.value)

    # == low-level API =======================================================
    @property
    def value(self):
        """:obj:`int`: Value of this constant net."""
        return self._value

    # -- implementing properties/methods required by superclass --------------
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
    def is_clock(self):
        return False

    @property
    def parent(self):
        raise None

    def __len__(self):
        return self._width

    def __getitem__(self, index):
        index = self._auto_index(index)
        if index.stop <= index.start:
            return type(self)()
        elif self.value is None:
            return type(self)(width = index.stop - index.start)
        else:
            return type(self)(self.value >> index.start, index.stop - index.start)

# ----------------------------------------------------------------------------
# -- Slice Reference of a Bus ------------------------------------------------
# ----------------------------------------------------------------------------
class Slice(AbstractNet):
    """Reference to a consecutive subset of a bus.

    Args:
        bus (`AbstractNet`): The referenced bus
        index (:obj:`slice`): Index of the bit(s) in the bus.

    Do not directly instantiate this class. Index into the bus instead, e.g. ``module.ports[0:4]``
    """

    __slots__ = ['bus', 'index']

    # == internal API ========================================================
    def __init__(self, bus, index):
        self.bus = bus
        self.index = index

    def __repr__(self):
        if self.__len__() == 1:
            return 'BitRef({}[{}])'.format(self.bus, self.index.start)
        else:
            return 'Slice({}[{}:{}])'.format(self.bus, self.index.stop - 1, self.index.start)

    # == low-level API =======================================================
    @property
    def net_type(self):
        return NetType.slice_

    def __len__(self):
        return self.index.stop - self.index.start

    def __getitem__(self, index):
        index = self._auto_index(index)
        if index.stop <= index.start:
            return Const()
        else:
            return type(self)(self.bus, slice(self.index.start + index.start, self.index.start + index.stop))

# ----------------------------------------------------------------------------
# -- A Concatenation of Slices and/or buses ----------------------------------
# ----------------------------------------------------------------------------
class Concat(AbstractNet):
    """A concatenation of slices and/or buses.

    Args:
        items (:obj:`Sequence` [`AbstractNet` ]): Items to be contenated together

    Direct instantiation of this class is not recommended. Use `NetUtils.concat` instead.
    """

    __slots__ = ['items']

    # == internal API ========================================================
    def __init__(self, items):
        self.items = items

    def __repr__(self):
        return 'Concat({})'.format(", ".join(repr(i) for i in reversed(self.items)))

    # == low-level API =======================================================
    @property
    def net_type(self):
        return NetType.concat

    def __len__(self):
        return sum(len(i) for i in self.items)

    def __getitem__(self, index):
        index = self._auto_index(index)
        if index.stop <= index.start:
            return Const()
        start, range_, items = index.start, index.stop - index.start, []
        for i in self.items:
            l = len(i)
            if start >= l:
                start -= l
            else:
                s = i[start : start + range_]
                start, range_ = 0, range_ - len(s)
                items.append( s ) 
                if range_ == 0:
                    break
        if len(items) == 0:
            return Const()
        elif len(items) == 1:
            return items[0]
        else:
            return type(self)(items)
