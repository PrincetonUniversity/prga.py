# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import NetType, PortDirection, AbstractPort, AbstractPin
from .util import NetUtils
from ...util import Object, uno
from ...exception import PRGATypeError, PRGAInternalError

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
        is_clock (:obj:`bool`): Mark this port as a clock port
        **kwargs: Custom key-value arguments. These attributes are to be added to the ``__dict__`` of this port object
            and accessible as dynamic attributes
    """

    __slots__ = ['_parent', '_name', '_width', '_direction', '_key', '_is_clock', '__dict__']
    def __init__(self, parent, name, width, direction, *, key = None, is_clock = False, **kwargs):
        self._parent = parent
        self._name = name
        self._width = width
        self._direction = direction
        self._key = uno(key, name)
        self._is_clock = is_clock
        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def __repr__(self):
        return '{}Port({}/{})'.format(self._direction.case('In', 'Out'), self._parent.name, self._name)

    # == low-level API =======================================================
    @property
    def is_clock(self):
        """:obj:`bool`: Test if this is a clock port."""
        return self._is_clock

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
    def bus(self):
        """`AbstractGenericNet`: The bus that this net belongs to."""
        return self

    @property
    def index(self):
        """:obj:`int` or :obj:`slice`: Index of this net in the bus."""
        return slice(0, len(self))

    @property
    def node(self):
        return (self._key, )

    def __len__(self):
        return self._width

    def __getitem__(self, index):
        return NetUtils._slice(self, self._auto_index(index))

# ----------------------------------------------------------------------------
# -- Pin ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Pin(Object, AbstractPin):
    """Pins of [Hierarchical] instances in a module.

    Args:
        model (`Port`): Model of this pin
        instance (`AbstractInstance`): Hierarchy of instances down to the pin in bottom-up order.
            See `Pin.hierarchy` for more information
    """

    __slots__ = ['_model', '_instance']

    # == internal API ========================================================
    def __init__(self, model, instance):
        self._model = model
        self._instance = instance

    def __repr__(self):
        return 'Pin({}/{}/{})'.format(self.parent.name, self._instance.name, self._model.name)

    def __eq__(self, other):
        return (isinstance(other, type(self)) and self._model is other._model and
                self._instance.hierarchy == other._instance.hierarchy)

    def __ne__(self, other):
        return not self.__eq__(other)

    # == low-level API =======================================================
    @property
    def model(self):
        return self._model

    @property
    def instance(self):
        return self._instance

    @property
    def bus(self):
        """`AbstractGenericNet`: The bus that this net belongs to."""
        return self

    @property
    def index(self):
        """:obj:`int` or :obj:`slice`: Index of this net in the bus."""
        return slice(0, len(self))

    # -- implementing properties/methods required by superclass --------------
    def __len__(self):
        return len(self._model)

    def __getitem__(self, index):
        return NetUtils._slice(self, self._auto_index(index))
