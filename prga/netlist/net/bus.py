# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import NetType, BusType, PortDirection, AbstractNet, AbstractInterfaceNet
from .const import Unconnected
from .util import NetUtils, Slice
from prga.util import Object, uno
from prga.exception import PRGATypeError

__all__ = []

# ----------------------------------------------------------------------------
# -- Base Net ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class _BaseNet(Object, AbstractNet):
    """Base class of all nets.

    Args:
        parent (`AbstractNetlistObject`): Parent module/instance of this net
        name (:obj:`str`): Name of this net
        width (:obj:`int`): Number of bits in this net
        key (:obj:`Hashable`): A hashable key used to index this net in the parent module/instance. If not given
            \(default argument: ``None``\), ``name`` is used by default
        **kwargs: Arbitrary key-value arguments. For each key-value pair ``key: value``, ``setattr(self, key, value)``
            is executed at the BEGINNING of ``__init__``
    """

    __slots__ = ['_parent', '_name', '_width', '_key', '__dict__']

    # == internal API ========================================================
    def __init__(self, parent, name, width, key = None, **kwargs):
        for k, v in iteritems(kwargs):
            setattr(self, k, v)
        self._parent = parent
        self._name = name
        self._width = width
        if key is not None:
            self._key = key

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def bus_type(self):
        return BusType.nonref

    @property
    def name(self):
        return self._name

    @property
    def parent(self):
        return self._parent

    @property
    def key(self):
        try:
            return self._key
        except AttributeError:
            return self._name

    def __len__(self):
        return self._width

    def __getitem__(self, index):
        if not isinstance(index, int) and not isinstance(index, slice):
            raise PRGATypeError("index", "int or slice")
        index = NetUtils._slice_intersect(slice(0, len(self)), index)
        if index is None:
            return Unconnected(0)
        else:
            return NetUtils._slice(self, index)

# ----------------------------------------------------------------------------
# -- Logic Net ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class Logic(_BaseNet):
    """Non-interface nets in a module.

    Args:
        parent (`AbstractModule`): Parent module of this logic net
        name (:obj:`str`): Name of this logic net
        width (:obj:`int`): Number of bits in this net
        key (:obj:`Hashable`): A hashable key used to index this net in the parent module. If not given
            \(default argument: ``None``\), ``name`` is used by default
        **kwargs: Arbitrary key-value arguments. For each key-value pair ``key: value``, ``setattr(self, key, value)``
            is executed at the BEGINNING of ``__init__``
    """

    # == internal API ========================================================
    def __str__(self):
        return 'Logic({}/{})'.format(self._parent.name, self._name)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.logic

    @property
    def is_source(self):
        return True

    @property
    def is_sink(self):
        return True

# ----------------------------------------------------------------------------
# -- Port --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Port(_BaseNet, AbstractInterfaceNet):
    """Ports in a module.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Number of bits in this net
        direction (`PortDirection`): Direction of the port
        key (:obj:`Hashable`): A hashable key used to index this net in the parent module. If not given
            \(default argument: ``None``\), ``name`` is used by default
        is_clock (:obj:`bool`): Mark this port as a clock port
        **kwargs: Arbitrary key-value arguments. For each key-value pair ``key: value``, ``setattr(self, key, value)``
            is executed at the BEGINNING of ``__init__``
    """

    __slots__ = ['_direction', '_is_clock']

    # == internal API ========================================================
    def __init__(self, parent, name, width, direction, key = None, is_clock = False, **kwargs):
        super(Port, self).__init__(parent, name, width, key, **kwargs)
        if is_clock and (width != 1 or not direction.is_input):
            raise PRGATypeError("is_clock", "bool", "Only single-bit input port may be marked as a clock")
        self._is_clock = is_clock
        self._direction = direction

    def __str__(self):
        return '{}Port({}/{})'.format(self._direction.case('In', 'Out'), self._parent.name, self._name)

    # == low-level API =======================================================
    @property
    def is_clock(self):
        """:obj:`bool`: Test if this port is a clock."""
        return self._is_clock

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.port

    @property
    def direction(self):
        return self._direction

# ----------------------------------------------------------------------------
# -- Pin ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Pin(Object, AbstractInterfaceNet):
    """Pins in an instance.

    Args:
        parent (`AbstractInstance`): Parent instance of this pin
        model (`Port`): Model port of this pin
        **kwargs: Arbitrary key-value arguments. For each key-value pair ``key: value``, ``setattr(self, key, value)``
            is executed at the BEGINNING of ``__init__``
    """

    __slots__ = ['_parent', '_model', '__dict__']

    # == internal API ========================================================
    def __init__(self, parent, model, **kwargs):
        for k, v in iteritems(kwargs):
            setattr(self, k, v)
        self._parent = parent
        self._model = model

    def __str__(self):
        return 'Pin({}/{}/{})'.format(self._parent.parent.name, self._parent.name, self._model.name)

    # == low-level API =======================================================
    @property
    def model(self):
        """`Port`: Model port of this pin."""
        return self._model

    @property
    def is_clock(self):
        """:obj:`bool`: Test if this pin is a clock."""
        return self._model.is_clock

    # -- implementing properties/methods required by superclass --------------
    @property
    def bus_type(self):
        return BusType.nonref

    @property
    def net_type(self):
        return NetType.pin

    @property
    def name(self):
        return self._model.name

    @property
    def parent(self):
        return self._parent

    @property
    def key(self):
        return self._model.key

    @property
    def direction(self):
        return self._model.direction

    def __len__(self):
        return len(self._model)

    def __getitem__(self, index):
        if not isinstance(index, int) and not isinstance(index, slice):
            raise PRGATypeError("index", "int or slice")
        index = NetUtils._slice_intersect(slice(0, len(self._model)), index)
        if index is None:
            return Unconnected(0)
        else:
            return NetUtils._slice(self, index)
