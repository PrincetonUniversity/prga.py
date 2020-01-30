# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import AbstractInstance
from prga.netlist.net.bus import Pin
from prga.util import Object

__all__ = ['Instance']

# ----------------------------------------------------------------------------
# -- Instance Pins Mapping Proxy ---------------------------------------------
# ----------------------------------------------------------------------------
class _InstancePinsProxy(Object, Mapping):
    """Helper class for `AbstractInstance.children` and `AbstractInstance.pins` properties.

    Args:
        instance (`AbstractInstance`): 
        children (:obj:`bool`):
    """

    __slots__ = ['instance', 'children']
    def __init__(self, instance, children):
        super(_InstancePinsProxy, self).__init__()
        self.instance = instance
        self.children = children

    def __getitem__(self, key):
        try:
            port = (self.instance.model.children if self.children else self.instance.model.ports)[key]
            if port.net_type.is_port:
                pin = self.instance._mutable_pins.get(key)
                if pin is None:
                    pin = self.instance._mutable_pins[key] = Pin(self.instance, port)
                return pin
        except (KeyError, AttributeError):
            pass
        try:
            del self.instance._mutable_pins[key]
        except KeyError:
            pass
        raise KeyError(key)

    def __len__(self):
        return len(self.instance.model.ports)

    def __iter__(self):
        for key, port in iteritems(self.instance.model.ports):
            if self.children:
                yield port.name
            else:
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
        key (:obj:`Hashable`): A hashable key used to index this net in the parent module/instance. If not given
            \(default argument: ``None``\), ``name`` is used by default
        **kwargs: Arbitrary key-value arguments. For each key-value pair ``key: value``, ``setattr(self, key, value)``
            is executed at the BEGINNING of ``__init__``
    """

    __slots__ = ['_parent', '_model', '_name', '_key', '_mutable_pins',
            '_children', '_pins', '__dict__']

    # == internal API ========================================================
    def __init__(self, parent, model, name, key = None, **kwargs):
        for k, v in iteritems(kwargs):
            setattr(self, k, v)
        self._parent = parent
        self._model = model
        self._name = name
        if key is not None:
            self._key = key
        self._mutable_pins = {}
        self._children = _InstancePinsProxy(self, True)
        self._pins = _InstancePinsProxy(self, False)

    def __str__(self):
        return 'Instance({}/{})'.format(self._parent.name, self._name)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

    @property
    def key(self):
        try:
            return self._key
        except AttributeError:
            return self._name

    @property
    def children(self):
        return self._children

    @property
    def pins(self):
        return self._pins

    @property
    def parent(self):
        return self._parent

    @property
    def model(self):
        return self._model
