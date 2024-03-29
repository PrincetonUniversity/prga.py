# -*- encoding: ascii -*-
"""Port & Pin classes."""

from .common import NetType, PortDirection, AbstractNet, AbstractNonReferenceNet, Const, Slice
from .util import NetUtils
from ...util import uno
from ...exception import PRGAInternalError

__all__ = ["Port", "Pin", "HierarchicalPin"]

# ----------------------------------------------------------------------------
# -- Bit ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class _Bit(AbstractNonReferenceNet):
    """A single, persistent bit in a bus.

    Args:
        bus (`AbstractNonReferenceNet`): The bus that this bit belongs to
        index (:obj:`int`): The index of this bit in the bus

    Keyword Args:
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes
    """

    __slots__ = ["_bus", "_index", "_connections", "__dict__"]
    def __init__(self, bus, index, **kwargs):
        self._bus = bus
        self._index = index
        self._connections = {}

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return 'Bit({}[{}])'.format(self.bus, self.index)

    def __len__(self):
        return 1

    def __getitem__(self, index):
        index = self._auto_index(index)
        if index.stop - index.start == 1:
            return self
        else:
            return Const()

    def __iter__(self):
        yield self

    def __reversed__(self):
        yield self

    # == low-level API =======================================================
    @property
    def bus(self):
        """`AbstractNonReferenceNet`: The bus that this bit belongs to."""
        return self._bus

    @property
    def index(self):
        """:obj:`int`: The index of this bit in the bus."""
        return self._index

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.bit

    @property
    def is_source(self):
        return self._bus.is_source

    @property
    def is_sink(self):
        return self._bus.is_sink

    @property
    def is_clock(self):
        return self._bus.is_clock 

    @property
    def parent(self):
        return self._bus.parent

# ----------------------------------------------------------------------------
# -- Bus ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class _Bus(AbstractNonReferenceNet):
    """Base class for `Port` and `Pin`."""

    __slots__ = ["_connections", "_bits", "__dict__"]

    def __init__(self, **kwargs):

        if self.parent.allow_multisource and len(self) > 1:
            self._bits = tuple( _Bit(self, i) for i in range(len(self)) )
        else:
            self._connections = {}

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __getitem__(self, index):
        index = self._auto_index(index)
        if index.stop - index.start == 1:
            try:
                return self._bits[index.start]
            except AttributeError:
                pass
        return NetUtils._slice(self, index)

    def __iter__(self):
        if len(self) == 1:
            yield self

        else:
            try:
                for i in self._bits:
                    yield i

            except AttributeError:
                for i in range(len(self)):
                    yield Slice(self, slice(i, i + 1))

    def __reversed__(self):
        if len(self) == 1:
            yield self

        else:
            try:
                for i in reversed(self._bits):
                    yield i

            except AttributeError:
                for i in reversed(range(self._width)):
                    yield Slice(self, slice(i, i + 1))

    @property
    def _coalesce_connections(self):
        return hasattr(self, "_connections")

    def _break_bits(self):
        """Break bus coalescence into bits. This method should only be used in `NetUtils._break_bits`.
        Beware that this method doesn't update the connections in the ``_connections`` mapping.

        Returns:
            :obj:`dict`: The current ``_connections`` value.

        Raises:
            :obj:`AttributeError`: If ``_connections`` is undefined, i.e. the bus is already broken into bits.
        """
        assert not (self.parent.coalesce_connections or len(self) == 1)

        try:
            connections = self._connections
        except AttributeError as e:
            raise e

        del self._connections
        self._bits = tuple( _Bit(self, i) for i in range(len(self)) )

        return connections

# ----------------------------------------------------------------------------
# -- Port --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Port(_Bus):
    """Ports of modules.

    Args:
        parent (`Module`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Width of this port
        direction (`PortDirection` or :obj:`str`): Direction of the port

    Keyword Args:
        is_clock (:obj:`bool`): Set if this port is a clock
        key (:obj:`Hashable`): A hashable key used to index this port in the ports mapping in the parent module.
            If not set \(default argument: ``None``\), ``name`` is used by default
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes
    """

    __slots__ = ['_parent', '_name', '_width', '_direction', '_is_clock', '_key']

    def __init__(self, parent, name, width, direction, *, is_clock = False, key = None, **kwargs):
        self._parent = parent
        self._name = name
        self._width = width
        self._direction = PortDirection.construct(direction)
        self._is_clock = is_clock
        self._key = uno(key, name)

        super().__init__(**kwargs)

    def __repr__(self):
        return "{}{}({}/{})".format(self._direction.case("In", "Out"),
                "Clock" if self._is_clock else "Port", self._parent, self._name)

    def __len__(self):
        return self._width

    # == low-level API =======================================================
    @property
    def direction(self):
        """`PortDirection`: Direction of this port."""
        return self._direction

    @property
    def key(self):
        """:obj:`Hashable`: A hashable key to index this port in its parent module's ports mapping."""
        return self._key

    @property
    def name(self):
        """:obj:`str`: Name of this port"""
        return self._name

    # -- implementing properties/methods required by superclass --------------
    @property
    def parent(self):
        return self._parent

    @property
    def net_type(self):
        return NetType.port

    @property
    def is_source(self):
        return self._direction.is_input

    @property
    def is_sink(self):
        return self._direction.is_output

    @property
    def is_clock(self):
        return self._is_clock

# ----------------------------------------------------------------------------
# -- Pin ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Pin(_Bus):
    """Pins of instances.

    Args:
        instance (`Instance`): The instance that this pin belongs to
        model (`Port`): The port in the model of ``instance`` that this pin corresponds to

    Keyword Args:
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes
    """

    __slots__ = ['_instance', '_model']

    def __init__(self, instance, model, **kwargs):
        self._instance = instance
        self._model = model

        super().__init__(**kwargs)

    def __repr__(self):
        return "Pin({}/{})".format(self._instance, self._model.name)

    def __len__(self):
        return len(self._model)

    # == low-level API =======================================================
    @property
    def instance(self):
        """`Instance`: The instance that this pin belongs to."""
        return self._instance

    @property
    def model(self):
        """`Port`: The port in the model of `Pin.instance` that this pin corresponds to."""
        return self._model

    # -- implementing properties/methods required by superclass --------------
    @property
    def parent(self):
        return self._instance.parent

    @property
    def net_type(self):
        return NetType.pin

    @property
    def is_source(self):
        return self._model.direction.is_output

    @property
    def is_sink(self):
        return self._model.direction.is_input

    @property
    def is_clock(self):
        return self._model.is_clock

# ----------------------------------------------------------------------------
# -- Hierarchical Pin Reference ----------------------------------------------
# ----------------------------------------------------------------------------
class HierarchicalPin(AbstractNet):
    """Reference to a pin of a hierarchical instance.

    Args:
        instance (`HierarchicalInstance`): The instance that this pin belongs to
        model (`Port`): The port in the model of ``instance`` that this pin corresponds to
    """

    __slots__ = ['_instance', '_model']

    def __init__(self, instance, model):
        self._instance = instance
        self._model = model

    def __repr__(self):
        return "HierPin({}/{})".format(self._instance, self._model.name)

    def __len__(self):
        return len(self._model)

    def __getitem__(self, index):
        return NetUtils._slice(self, self._auto_index(index))

    def __iter__(self):
        if len(self) == 1:
            yield self
        else:
            for i in range(len(self)):
                yield Slice(self, slice(i, i + 1))

    def __reversed__(self):
        if len(self) == 1:
            yield self
        else:
            for i in reversed(range(len(self))):
                yield Slice(self, slice(i, i + 1))

    # == low-level API =======================================================
    @property
    def instance(self):
        """`HierarchicalInstance`: The instance that this pin belongs to."""
        return self._instance

    @property
    def model(self):
        """`Port`: The port in the model of `Pin.instance` that this pin corresponds to."""
        return self._model

    @property
    def parent(self):
        """`Module`: Parent module of this net."""
        return self._instance.parent

    @property
    def is_clock(self):
        return self._model.is_clock

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.hierarchical
