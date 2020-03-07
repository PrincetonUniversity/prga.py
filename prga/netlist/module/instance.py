# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import AbstractInstance
from ...util import Object, uno
from ...exception import PRGAInternalError

__all__ = ['Instance', 'HierarchicalInstance']

# ----------------------------------------------------------------------------
# -- Instance Pins Mapping Proxy ---------------------------------------------
# ----------------------------------------------------------------------------
class _InstancePinsProxy(Object, Mapping):
    """Helper class for `AbstractInstance.pins` properties.

    Args:
        instance (`AbstractInstance`): 
    """

    __slots__ = ['instance']
    def __init__(self, instance):
        super(_InstancePinsProxy, self).__init__()
        self.instance = instance

    def __getitem__(self, key):
        try:
            return self.instance.model.ports[key]._to_pin(self.instance)
        except (KeyError, AttributeError):
            raise KeyError(key)

    def __len__(self):
        return len(self.instance.model.ports)

    def __iter__(self):
        for key in self.instance.model.ports:
            yield key

# ----------------------------------------------------------------------------
# -- Instance ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class Instance(Object, AbstractInstance):
    """Immediate instance of a module.

    Args:
        parent (`AbstractModule`): Parent module
        model (`AbstractModule`): Model of this instance
        name (:obj:`str`): Name of the instance

    Keyword Args:
        key (:obj:`Hashable`): A hashable key used to index this instance in the parent module. If not given
            \(default argument: ``None``\), ``name`` is used by default
        **kwargs: Custom key-value arguments. For each key-value pair ``key: value``, ``setattr(self, key, value)``
            is executed at the BEGINNING of ``__init__``
    """

    __slots__ = ['_parent', '_model', '_name', '_key', '_pins', '__dict__']

    # == internal API ========================================================
    def __init__(self, parent, model, name, *, key = None, **kwargs):
        self._parent = parent
        self._model = model
        self._name = name
        self._key = uno(key, name)
        self._pins = _InstancePinsProxy(self)
        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def __str__(self):
        return 'Instance({}/{})'.format(self._parent.name, self._name)

    def __getitem__(self, idx):
        l = (True, )
        if l[idx]:
            return self
        else:
            return tuple()

    def __iter__(self):
        yield self

    def __len__(self):
        return 1

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

    @property
    def key(self):
        return self._key

    @property
    def node(self):
        return (self._key, )

    @property
    def pins(self):
        return self._pins

    @property
    def parent(self):
        return self._parent

    @property
    def model(self):
        return self._model

# ----------------------------------------------------------------------------
# -- Hierarchical Instance ---------------------------------------------------
# ----------------------------------------------------------------------------
class HierarchicalInstance(Object, AbstractInstance):
    """Hierarchical instance of a module.

    Args:
        hierarchy (:obj:`Sequence` [:obj:`Instance` ]): Hierarchy in bottom-up order
    """

    __slots__ = ['_hierarchy', '_key', '_pins']

    # == internal API ========================================================
    def __init__(self, hierarchy):
        self._hierarchy = tuple(iter(hierarchy))
        self._key = tuple(i.key for i in self._hierarchy)
        self._pins = _InstancePinsProxy(self)

    def __str__(self):
        return 'HierarchicalInstance({}/{})'.format(self._hierarchy[-1].parent.name, self.name)

    def __getitem__(self, idx):
        items = self._hierarchy[idx]
        if len(items) == 1:
            return items[0]
        elif len(items) > 1:
            return type(self)(items)
        else:
            return tuple()

    def __iter__(self):
        return iter(self._hierarchy)

    def __len__(self):
        return len(self._hierarchy)

    def __eq__(self, other):
        return isinstance(other, type(self)) and self._hierarchy == other._hierarchy

    def __ne__(self, other):
        return not self.__eq__(other)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return '/'.join(i.name for i in reversed(self._hierarchy))

    @property
    def key(self):
        return self._key

    @property
    def node(self):
        return self._key

    @property
    def pins(self):
        return self._pins

    @property
    def parent(self):
        return self._hierarchy[-1].parent

    @property
    def model(self):
        return self._hierarchy[0].model
