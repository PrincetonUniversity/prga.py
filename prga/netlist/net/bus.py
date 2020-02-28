# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import NetType, PortDirection, AbstractPort, AbstractPin
from .const import Unconnected
from .util import NetUtils
from ...util import Object, uno
from ...exception import PRGATypeError

__all__ = ['Port', 'Pin']

# ----------------------------------------------------------------------------
# -- Port --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Port(Object, AbstractPort):
    """Ports in a module.

    Args:
        parent (`AbstractModule`): Parent module of this port
        name (:obj:`str`): Name of this port
        width (:obj:`int`): Number of bits in this net
        direction (`PortDirection`): Direction of the port

    Keyword Args:
        key (:obj:`Hashable`): A hashable key used to index this net in the parent module. If not given
            \(default argument: ``None``\), ``name`` is used by default
        clock (:obj:`Hashable`): Mark this port as a sequential startpoint/endpoint controlled by the specified clock
            in the parent module
        is_clock (:obj:`bool`): Mark this port as a clock port
        **kwargs: Custom key-value arguments. These attributes are to be added to the ``__dict__`` of this port object
            and accessible as dynamic attributes
    """

    __slots__ = ['_parent', '_name', '_width', '_direction', '_key', '_clock', '_is_clock', '__dict__']
    def __init__(self, parent, name, width, direction, *,
            key = None, clock = None, is_clock = False, **kwargs):
        self._parent = parent
        self._name = name
        self._width = width
        self._direction = direction
        self._key = uno(key, name)
        self._clock = clock
        self._is_clock = is_clock
        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def __str__(self):
        return '{}Port({}/{})'.format(self._direction.case('In', 'Out'), self._parent.name, self._name)

    # == internal API ========================================================
    def _to_pin(self, hierarchy):
        return Pin(self, hierarchy)

    # == low-level API =======================================================
    @property
    def is_clock(self):
        """:obj:`bool`: Test if this is a clock port."""
        return self._is_clock

    @property
    def clock(self):
        """:obj:`bool`: Test if this is a sequential startpoint/endpoint and if so, which clock controls it."""
        return self._clock

    # -- implementing properties/methods required by superclass --------------
    @property
    def parent(self):
        return self._parent

    @property
    def name(self):
        return self._name

    @property
    def direction(self):
        return self._direction

    @property
    def key(self):
        return self._key

    @property
    def node(self):
        return (self._key, )

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
# -- Pin ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Pin(Object, AbstractPin):
    """Pins of [Hierarchical] instances in a module.

    Args:
        model (`Port`): Model of this pin
        hierarchy (:obj:`Iterable` [`AbstractInstance` ]): Hierarchy of instances down to the pin in ascending order.
            See `Pin.hierarchy` for more information
    """

    __slots__ = ['_model', '_hierarchy']

    # == internal API ========================================================
    def __init__(self, model, hierarchy):
        self._model = model
        self._hierarchy = tuple(iter(hierarchy))

    def __str__(self):
        return 'Pin({}/{}/{})'.format(self.parent.name,
                "/".join(i.name for i in self._hierarchy),
                self._model.name)

    def __eq__(self, other):
        return isinstance(other, type(self)) and self._model is other._model and self._hierarchy == other._hierarchy

    def __ne__(self, other):
        return not self.__eq__(other)

    # == low-level API =======================================================
    @property
    def model(self):
        return self._model

    @property
    def hierarchy(self):
        return self._hierarchy

    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return '{}/{}'.format('/'.join(i.name for i in self._hierarchy), self._model.name)

    @property
    def node(self):
        return self.model.node + tuple(inst.key for inst in self._hierarchy)

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
