# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import AbstractInstance
from ...util import Object, uno
from ...exception import PRGAInternalError

__all__ = ['Instance']

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
            return self.instance.model.ports[key]._to_pin([self.instance])
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
    """Instance of a module.

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

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

    @property
    def key(self):
        return self._key

    @property
    def pins(self):
        return self._pins

    @property
    def parent(self):
        return self._parent

    @property
    def model(self):
        return self._model
