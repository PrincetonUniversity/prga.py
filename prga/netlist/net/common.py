# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...util import Enum, Abstract, Object, uno
from ...exception import PRGAIndexError, PRGATypeError

from abc import abstractproperty, abstractmethod

__all__ = ['NetType', 'BusType', 'PortDirection', 'Const']

# ----------------------------------------------------------------------------
# -- Bus Type ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class BusType(Enum):
    """Enum type for buses."""
    nonref = 0          #: bus (not a reference)

    # references
    slice_ = 1          #: a consecutive subset (slice) of a multi-bit bus
    concat = 2          #: a concatenation of buses and/or subsets

# ----------------------------------------------------------------------------
# -- Net Type ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class NetType(Enum): 
    """Enum type for nets."""
    # constant net types
    const = 0           #: constant value

    # netlist net types
    port = 1            #: port in a module
    pin = 2             #: [hierarchical] pin

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
# -- Abstract Generic Bus ----------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractGenericBus(Abstract, Sequence):
    """Abstract class for all buses."""

    @abstractproperty
    def bus_type(self):
        """`BusType`: Type of this bus."""
        raise NotImplementedError

    @abstractproperty
    def is_source(self):
        """:obj:`bool`: Test if this net can be used as drivers of other nets."""
        raise NotImplementedError

    @abstractproperty
    def is_sink(self):
        """:obj:`bool`: Test if this net can be driven by other nets."""
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
            if index.step not in (None, 1):
                raise PRGAIndexError("'step' must be 1 when indexing a net with a slice")
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
# -- Abstract Generic Net ----------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractGenericNet(AbstractGenericBus):
    """Abstract class for all nets."""

    @abstractproperty
    def net_type(self):
        """`NetType`: Type of this net."""
        raise NotImplementedError

    @abstractproperty
    def node(self):
        """:obj:`Hashable`: A hashable value to index this net in the connection graph."""
        raise NotImplementedError

    @abstractproperty
    def parent(self):
        """`AbstractModule`: Parent module of this net."""
        raise NotImplementedError

    @abstractproperty
    def bus(self):
        """`AbstractGenericNet`: The bus to which this net belongs to."""
        raise NotImplementedError

    @abstractproperty
    def index(self):
        """:obj:`slice`: Index of this net in the bus."""
        raise NotImplementedError

    @abstractproperty
    def is_clock(self):
        """:obj:`bool`: Test if this net is part of a clock network."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def bus_type(self):
        return BusType.nonref

# ----------------------------------------------------------------------------
# -- Abstract Port -----------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractPort(AbstractGenericNet):
    """Abstract class for ports."""

    @abstractproperty
    def direction(self):
        """`PortDirection`: Direction of this port."""
        raise NotImplementedError

    @abstractproperty
    def key(self):
        """:obj:`Hashable`: A hashable key to index this port in its parent module's ports mapping."""
        raise NotImplementedError

    @abstractproperty
    def name(self):
        """:obj:`str`: Name of this port"""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.port

    @property
    def is_source(self):
        return self.direction.is_input

    @property
    def is_sink(self):
        return self.direction.is_output

    @property
    def node(self):
        return (self.key, )

    @property
    def bus(self):
        return self

    @property
    def index(self):
        return slice(0, len(self))

# ----------------------------------------------------------------------------
# -- Abstract Pin ------------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractPin(AbstractGenericNet):
    """Abstract class for [hierarchical] pins."""

    @abstractproperty
    def model(self):
        """`AbstractPort`: Model port of this pin."""
        raise NotImplementedError

    @abstractproperty
    def instance(self):
        """`AbstractInstance`: [Hierarchical] instances down to the pin in bottom-up order.

        For example, assume 1\) module 'clb' has an instance 'alm0' of module 'alm', and 2\) module 'alm' has an
        instance 'lutA' of module 'LUT4', and 3\) module 'LUT4' has an input port 'in'. This net can be referred to by
        a pin, whose model is the port, and the hierarchy is [instance 'lutA', instance 'alm0']."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.pin

    @property
    def is_clock(self):
        return self.model.is_clock

    @property
    def is_source(self):
        return not self.instance.is_hierarchical and self.model.is_sink

    @property
    def is_sink(self):
        return not self.instance.is_hierarchical and self.model.is_source

    @property
    def parent(self):
        return self.instance.parent

    @property
    def node(self):
        return self.model.node + self.instance.node

    @property
    def bus(self):
        return self

    @property
    def index(self):
        return slice(0, len(self))

# ----------------------------------------------------------------------------
# -- Constant Nets -----------------------------------------------------------
# ----------------------------------------------------------------------------
class Const(Object, AbstractGenericNet):
    """A constant net used as a driver of other nets, connecting those nets to constant low/high wires.

    Args:
        value (:obj:`int`): Value of this constant in little-endian. Use ``None`` to represent "unconnected" state
        width (:obj:`int`): Number of bits in this net
    """

    __singletons = {}
    __slots__ = ['_key']

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

        key = (NetType.const, value, width)
        try:
            return cls.__singletons[key]
        except KeyError:
            obj = super(Const, cls).__new__(cls)
            obj._key = key
            return cls.__singletons.setdefault(key, obj)

    def __init__(self, value = None, width = None):
        pass

    def __deepcopy__(self, memo):
        return self

    def __getnewargs__(self):
        return self._key[1:]

    def __repr__(self):
        if self.value is None:
            return "Unconnected({})".format(self.width)
        else:
            return "Const({}'h{:x})".format(self.width, self.value)

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
    def is_clock(self):
        return False

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
    def bus(self):
        return self

    @property
    def index(self):
        return slice(0, len(self))

    @property
    def parent(self):
        raise NotImplementedError

    def __len__(self):
        return self._key[2]

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
class Slice(Object, AbstractGenericNet):
    """Reference to a consecutive subset of a port/pin/logic bus.

    Args:
        bus (`AbstractGenericBus`): The referred bus
        index (:obj:`slice`): Index of the bit(s) in the bus.

    Direct instantiation of this class is not recommended.
    """

    __slots__ = ['bus', 'index']

    # == internal API ========================================================
    def __init__(self, bus, index):
        self.bus = bus
        self.index = index

    def __repr__(self):
        if self.__len__() == 1:
            return 'Bit({}[{}])'.format(self.bus, self.index.start)
        else:
            return 'Slice({}[{}:{}])'.format(self.bus, self.index.stop - 1, self.index.start)

    # == low-level API =======================================================
    @property
    def bus_type(self):
        return BusType.slice_

    @property
    def net_type(self):
        return self.bus.net_type

    @property
    def is_source(self):
        return self.bus.is_source

    @property
    def is_sink(self):
        return self.bus.is_sink

    @property
    def node(self):
        if self.__len__() == 1:
            return self.index.start, self.bus.node
        else:
            raise PRGAInternalError("Cannot create node for multi-bit {}".format(self))

    @property
    def is_clock(self):
        return self.bus.is_clock

    @property
    def parent(self):
        return self.bus.parent

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
class Concat(Object, AbstractGenericBus):
    """A concatenation of slices and/or buses.

    Args:
        items (:obj:`Sequence` [`AbstractGenericNet` ]): Items to be contenated together

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
    def bus_type(self):
        return BusType.concat

    @property
    def is_source(self):
        return all(i.is_source for i in self.items)

    @property
    def is_sink(self):
        return all(i.is_sink for i in self.items)

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
