# -*- encoding: ascii -*-
"""Common enums and abstract base class for nets."""

from ...util import Enum, Object, uno
from ...exception import PRGAIndexError, PRGATypeError, PRGAInternalError

from abc import abstractproperty, abstractmethod
from collections.abc import Sequence

__all__ = ["NetType", "PortDirection", "TimingArcType", "Const"]

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
# -- Timing Arc Type ---------------------------------------------------------
# ----------------------------------------------------------------------------
class TimingArcType(Enum):
    """Timing arc types."""

    comb_bitwise = 0        #: combinational propagation delay of a bitwise timing arc
    comb_matrix = 1         #: combinational propagation delay of an all-to-all timing arc
    seq_start = 2           #: clock -> sequential startpoint(s), i.e., clk2q
    seq_end = 3             #: clock -> sequential endpoint(s), i.e., setup & hold

# ----------------------------------------------------------------------------
# -- Abstract Net ------------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractNet(Object, Sequence):
    """Abstract class for all nets and net references."""

    @abstractproperty
    def net_type(self):
        """`NetType`: Type of the net."""
        raise NotImplementedError

    @abstractproperty
    def is_clock(self):
        """:obj:`bool`: Test if this net is part of a clock network."""
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

    def __iter__(self):
        if self.value is None:
            for _ in range(len(self)):
                yield type(self)(self.value, 1)
        else:
            for i in range(len(self)):
                yield type(self)(self.value >> i, 1)

    def __reversed__(self):
        if self.value is None:
            for _ in range(len(self)):
                yield type(self)(self.value, 1)
        else:
            for i in reversed(range(len(self))):
                yield type(self)(self.value >> i, 1)

# ----------------------------------------------------------------------------
# -- Slice Reference of a Bus ------------------------------------------------
# ----------------------------------------------------------------------------
class Slice(AbstractNet):
    """Reference to a consecutive subset of a bus.

    Args:
        bus (`AbstractNet`): The referenced bus
        range_ (:obj:`slice`): Range of the bit(s) in the bus.

    Do not directly instantiate this class. Index into the bus instead, e.g. ``module.ports[0:4]``
    """

    __slots__ = ['bus', 'range_']

    # == internal API ========================================================
    def __init__(self, bus, range_):
        self.bus = bus
        self.range_ = range_

    def __repr__(self):
        if self.__len__() == 1:
            return 'BitRef({}[{}])'.format(self.bus, self.index)
        else:
            return 'Slice({}[{}:{}])'.format(self.bus, self.range_.stop - 1, self.range_.start)

    def __len__(self):
        return self.range_.stop - self.range_.start

    def __getitem__(self, index):
        index = self._auto_index(index)
        return self.bus[self.range_.start + index.start:self.range_.start + index.stop]

    def __iter__(self):
        for i in range(self.range_.start, self.range_.stop):
            yield self.bus[i]

    def __reversed__(self):
        for i in reversed(range(self.range_.start, self.range_.stop)):
            yield self.bus[i]

    # == low-level API =======================================================
    @property
    def net_type(self):
        return NetType.slice_

    @property
    def parent(self):
        """`Module`: Parent module of this net."""
        return self.bus.parent

    @property
    def is_clock(self):
        return self.bus.is_clock

    @property
    def index(self):
        """:obj:`int`: Index of the bit in the bus. Only valid when this object is a bit reference, i.e. length equals
        to 1."""
        if self.__len__() != 1:
            raise PRGAInternalError("{} is not a bit reference. len({}) == {}"
                    .format(self, self, self.__len__()))
        return self.range_.start

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

    @property
    def is_clock(self):
        return False

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

    def __iter__(self):
        for i in self.items:
            for ii in i:
                yield ii

    def __reversed__(self):
        for i in reversed(self.items):
            for ii in reversed(i):
                yield ii
