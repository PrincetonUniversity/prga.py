# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Port & Pin classes."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import NetType, PortDirection, AbstractNet, AbstractNonReferenceNet
from .util import NetUtils
from ...util import Object, uno
from ...exception import PRGAInternalError

__all__ = ["Port", "Pin", "HierarchicalPin"]

# ----------------------------------------------------------------------------
# -- Bit ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class _Bit(Object, AbstractNonReferenceNet):
    """A single, persistent bit in a bus.

    Args:
        bus (`AbstractNonReferenceNet`): The bus that this bit belongs to
        index (:obj:`int`): The index of this bit in the bus

    Keyword Args:
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes
    """

    __slots__ = ["_bus", "_index", "_sources", "_sinks", "__dict__"]
    def __init__(self, bus, index, **kwargs):
        self._bus = bus
        self._index = index

        if self.is_source:
            self._sinks = {}

        if self.is_sink:
            self._sources = {}

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return 'Bit({}[{}])'.format(self.bus, self.index)

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
    def parent(self):
        return self._bus.parent

# ----------------------------------------------------------------------------
# -- Port --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Port(Object, AbstractNonReferenceNet):
    """Ports of modules.

    Args:
        parent (`Module`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int` or :obj:`str`): Width of this port, or name of the paramter in the parent module that
            controls the width of this port
        direction (`PortDirection`): Direction of the port

    Keyword Args:
        key (:obj:`Hashable`): A hashable key used to index this port in the ports mapping in the parent module.
            If not set \(default argument: ``None``\), ``name`` is used by default
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes
    """

    __slots__ = ['_parent', '_name', '_width', '_direction', '_key', '_sources', '_sinks', '_bits', '__dict__']

    def __init__(self, parent, name, width, direction, *, key = None, **kwargs):
        if isinstance(width, str) and width not in parent.parameters:
            raise PRGAInternalError("No parameter '{}' found in {}".format(width, parent))

        self._parent = parent
        self._name = name
        self._width = width
        self._direction = direction
        self._key = uno(key, name)

        if not self.parent._coalesce_connections:
            self._bits = tuple(_Bit(self, i) for i in range(len(self)))
        else:
            if self.is_source:
                self._sinks = {}
            if self.is_sink:
                self._sources = {}

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return "{}Port({}/{})".format(self._direction.case("In", "Out"), self._parent, self._name)

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
        return self.direction.is_input

    @property
    def is_sink(self):
        return self.direction.is_output

    def __len__(self):
        if isinstance(self._width, str):
            return self._parent.parameters[self._width]
        else:
            return self._width

    def __getitem__(self, index):
        index = self._auto_index(index)
        if not self._parent._coalesce_connections and index.stop - index.start == 1:
            return self._bits[index.start]
        else:
            return NetUtils._slice(self, index)

# ----------------------------------------------------------------------------
# -- Pin ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Pin(Object, AbstractNonReferenceNet):
    """Pins of instances.

    Args:
        instance (`Instance`): The instance that this pin belongs to
        model (`Port`): The port in the model of ``instance`` that this pin corresponds to

    Keyword Args:
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes
    """

    __slots__ = ['_instance', '_model', '_sources', '_sinks', '_bits', '__dict__']

    def __init__(self, instance, model, **kwargs):
        self._instance = instance
        self._model = model

        if not self.parent._coalesce_connections:
            self._bits = tuple(_Bit(self, i) for i in range(len(self)))
        else:
            if self.is_source:
                self._sinks = {}
            if self.is_sink:
                self._sources = {}

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return "Pin({}/{})".format(self._instance, self._model.name)

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
        return self.direction.is_output

    @property
    def is_sink(self):
        return self.direction.is_input

    def __len__(self):
        return len(self._model)

    def __getitem__(self, index):
        index = self._auto_index(index)
        if not self._parent._coalesce_connections and index.stop - index.start == 1:
            return self._bits[index.start]
        else:
            return NetUtils._slice(self, index)

# ----------------------------------------------------------------------------
# -- Hierarchical Pin Reference ----------------------------------------------
# ----------------------------------------------------------------------------
class HierarchicalPin(Object, AbstractNet):
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

    # == low-level API =======================================================
    @property
    def instance(self):
        """`HierarchicalInstance`: The instance that this pin belongs to."""
        return self._instance

    @property
    def model(self):
        """`Port`: The port in the model of `Pin.instance` that this pin corresponds to."""
        return self._model

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.hierarchical

    def __len__(self):
        return len(self._model)

    def __getitem__(self, index):
        return NetUtils._slice(self, self._auto_index(index))
