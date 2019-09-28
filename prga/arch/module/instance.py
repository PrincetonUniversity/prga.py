# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.bus import InputPin, OutputPin
from prga.arch.module.common import ModuleClass
from prga.exception import PRGAInternalError
from prga.util import Abstract, Object, ReadonlyMappingProxy

from abc import abstractproperty, abstractmethod

__all__ = ['AbstractInstance', 'RegularInstance']

# ----------------------------------------------------------------------------
# -- Instance Pins Mapping Proxy ---------------------------------------------
# ----------------------------------------------------------------------------
class _InstancePinsProxy(Object, Mapping):
    """Helper class for `AbstractInstance.all_pins` property.

    Args:
        instance (`AbstractInstance`):
    """

    __slots__ = ['instance']
    def __init__(self, instance):
        super(_InstancePinsProxy, self).__init__()
        self.instance = instance

    def __getitem__(self, key):
        try:
            port = self.instance.model.all_ports[key]
        except KeyError:
            raise KeyError(key)
        return self.instance._pins.setdefault(key, self.instance._create_pin(port))

    def __len__(self):
        return len(self.instance.model.all_ports)

    def __iter__(self):
        return iter(self.instance.model.all_ports)

# ----------------------------------------------------------------------------
# -- Abstract Instance -------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractInstance(Abstract):
    """Abstract base class for instances."""

    # == internal API ========================================================
    def __str__(self):
        return '{}/{}'.format(self.parent, self.name)

    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def _pins(self):
        """:obj:`MutableMapping` [:obj:`Hashable`, `AbstractPin` ]: Internal storage for pins."""
        raise NotImplementedError

    @abstractmethod
    def _create_pin(self, port):
        """Create a pin with model ``port``."""
        raise NotImplementedError

    # == low-level API =======================================================
    @property
    def all_pins(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPin` ]: A mapping from some hashable indices to the pins of this
        instance."""
        return _InstancePinsProxy(self)

    @property
    def module_class(self):
        """`ModuleClass`: Logical class of this module."""
        return self.model.module_class

    @property
    def physical_pins(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPin` ]: A mapping from some hashable indices to physical pins of
        this instance."""
        return ReadonlyMappingProxy(self.all_pins, lambda kv: kv[1].is_physical)

    @property
    def is_user_accessible(self):
        """:obj:`bool`: Test if this instance is user-accessible."""
        return self.module_class in (ModuleClass.primitive, ModuleClass.cluster)

    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def is_physical(self):
        """:obj:`bool`: Test if this instance is physical."""
        raise NotImplementedError

    @abstractproperty
    def parent(self):
        """`AbstractModule`: Parent module of this instance."""
        raise NotImplementedError

    @abstractproperty
    def name(self):
        """:obj:`str`: Name of this instance."""
        raise NotImplementedError

    @abstractproperty
    def model(self):
        """`AbstractModule`: Model of this instance."""
        raise NotImplementedError

    @property
    def key(self):
        """:obj:`Hashable`: Index of this instance in the instance mapping of the parent module."""
        return self.name

    # == high-level API ======================================================
    @property
    def pins(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPin` ]: A mapping from some hashable indices to user-accessible
        pins of this instance."""
        return ReadonlyMappingProxy(self.all_pins, lambda kv: kv[1].is_user_accessible)

# ----------------------------------------------------------------------------
# -- Base Instance -----------------------------------------------------------
# ----------------------------------------------------------------------------
class BaseInstance(Object, AbstractInstance):
    """Base class for instances.

    Args:
        parent (`AbstractModule`): parent module of this instance
        model (`AbstractModule`): model of this instance
    """

    __slots__ = ['_parent', '_model', '_pins']
    def __init__(self, parent, model):
        super(BaseInstance, self).__init__()
        self._parent = parent
        self._model = model
        self._pins = {}

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def parent(self):
        return self._parent

    @property
    def model(self):
        return self._model

# ----------------------------------------------------------------------------
# -- Regular Instance --------------------------------------------------------
# ----------------------------------------------------------------------------
class RegularInstance(BaseInstance):
    """Most basic and commonly-used type of instance.

    Args:
        parent (`AbstractModule`): parent module of this instance
        model (`AbstractModule`): model of this instance
        name (:obj:`str`): name of this instance
    """

    __slots__ = ['_name']
    def __init__(self, parent, model, name):
        super(RegularInstance, self).__init__(parent, model)
        self._name = name

    # == internal API ========================================================
    # -- implementing properties/methods required by superclass --------------
    def _create_pin(self, port):
        return port.direction.switch(InputPin, OutputPin)(self, port)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return self.parent.is_physical and self.model.is_physical

    @property
    def name(self):
        return self._name
