# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import AbstractInstance
from ..net.bus import Pin
from ...util import Object, uno
from ...exception import PRGAInternalError, PRGATypeError, PRGAIndexError

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
            return Pin(self.instance.model.ports[key], self.instance)
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
    """[Hierarchical] instance of a module.

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

    __slots__ = ['_parent', '_model', '_name', '_key', '__dict__']

    # == internal API ========================================================
    def __init__(self, parent, model, name, *, key = None, **kwargs):
        self._parent = parent
        self._model = model
        self._name = name
        self._key = uno(key, name)
        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def __repr__(self):
        return 'Instance({}/{}[{}])'.format(self._parent.name, self._name, self._model.name)

    # == low-level API =======================================================
    @property
    def name(self):
        return self._name

    @property
    def key(self):
        return self._key

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_hierarchical(self):
        return False

    @property
    def pins(self):
        return _InstancePinsProxy(self)

    @property
    def parent(self):
        return self._parent

    @property
    def model(self):
        return self._model

    @property
    def hierarchy(self):
        return (self, )

    def extend_hierarchy(self, *, above = None, below = None):
        if above is None and below is None:
            return self
        hierarchy = self.hierarchy
        if isinstance(above, AbstractInstance):
            hierarchy = hierarchy + above.hierarchy
        elif above is not None:
            hierarchy = hierarchy + above
        if isinstance(below, AbstractInstance):
            hierarchy = below.hierarchy + hierarchy
        elif below is not None:
            hierarchy = below + hierarchy
        return HierarchicalInstance(hierarchy)

    def shrink_hierarchy(self, index):
        if isinstance(index, int):
            if index == 0:
                return self
            else:
                raise PRGAIndexError("Index out of range. {} has 1 levels of hierarchy".format(self))
        elif isinstance(index, slice):
            start = max(0, uno(index.start, 0))
            stop = min(1, uno(index.stop, 1))
            if start <= 0 < stop:
                return self
            else:
                return None
        else:
            raise PRGATypeError("index", "int or slice")

# ----------------------------------------------------------------------------
# -- Hierarchical Instance ---------------------------------------------------
# ----------------------------------------------------------------------------
class HierarchicalInstance(Object, AbstractInstance):
    """Hierarchical instance of a module.

    Args:
        hierarchy (:obj:`Sequence` [:obj:`Instance` ]): Hierarchy in bottom-up order
    """

    __slots__ = ['_hierarchy']

    # == internal API ========================================================
    def __init__(self, hierarchy):
        self._hierarchy = tuple(iter(hierarchy))
        if len(self._hierarchy) < 2:
            raise PRGAInternalError("Cannot create hierarchical instance with less than 2 levels")

    def __repr__(self):
        s = '{}/{}'.format(self._hierarchy[-1].parent.name, self._hierarchy[-1].name)
        for inst in reversed(self._hierarchy[:-1]):
            s += "[{}]/{}".format(inst.parent.name, inst.name)
        s += "[{}]".format(self.model.name)
        return "HierarchicalInstance({})".format(s)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_hierarchical(self):
        return True

    @property
    def parent(self):
        return self._hierarchy[-1].parent

    @property
    def model(self):
        return self._hierarchy[0].model

    @property
    def pins(self):
        return _InstancePinsProxy(self)

    @property
    def hierarchy(self):
        return self._hierarchy

    def extend_hierarchy(self, *, above = None, below = None):
        if above is None and below is None:
            return self
        hierarchy = self.hierarchy
        if isinstance(above, AbstractInstance):
            hierarchy = hierarchy + above.hierarchy
        elif above is not None:
            hierarchy = hierarchy + above
        if isinstance(below, AbstractInstance):
            hierarchy = below.hierarchy + hierarchy
        elif below is not None:
            hierarchy = below + hierarchy
        return HierarchicalInstance(hierarchy)

    def shrink_hierarchy(self, index):
        hierarchy = self._hierarchy[index]
        if len(hierarchy) == 0:
            return None
        elif len(hierarchy) == 1:
            return hierarchy[0]
        else:
            return type(self)(hierarchy)
