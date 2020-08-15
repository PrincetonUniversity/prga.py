# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Netlist module instances, i.e. sub-modules."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..net.bus import Pin, HierarchicalPin
from ...util import uno, Abstract
from ...exception import PRGAInternalError, PRGATypeError, PRGAIndexError

from abc import abstractproperty, abstractmethod

# In Python 3.7 and above, ``dict`` preserves insertion order and is more performant than ``OrderedDict``
OrderedDict = dict

__all__ = ['Instance', 'HierarchicalInstance']

# ----------------------------------------------------------------------------
# -- Instance Pins Mapping Proxy ---------------------------------------------
# ----------------------------------------------------------------------------
class _InstancePinsProxy(Mapping):
    """Helper class for `AbstractInstance.pins` property.

    Args:
        instance (`AbstractInstance`):
    """

    __slots__ = ["instance"]

    def __init__(self, instance):
        self.instance = instance

    def __getitem__(self, key):
        if (model := self.instance.model.ports.get(key)) is None:
            if (not self.instance.is_hierarchical and
                    (pin := self.instance._pins.get(key)) is not None):
                raise PRGAInternalError("Port {} removed from {}"
                        .format(key, self.instance.model))
            raise KeyError(key)
        elif self.instance.is_hierarchical:
            return HierarchicalPin(self.instance, model)
        elif (pin := self.instance._pins.get(key)) is None:
            pin = self.instance._pins.setdefault(key, Pin(self.instance, model))
        return pin

    def __len__(self):
        return len(self.instance.model.ports)

    def __iter__(self):
        for key in self.instance.model.ports:
            yield key

# ----------------------------------------------------------------------------
# -- Abstract Instance -------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractInstance(Abstract):
    """Abstract base class for instances."""

    @abstractproperty
    def is_hierarchical(self):
        """:obj:`bool`: Test if this is a hierarchical instance."""
        raise NotImplementedError

    @abstractproperty
    def parent(self):
        """`Module`: Module which instance belongs to. For a hierarchical instance, this means the top-level
        module."""
        raise NotImplementedError

    @abstractproperty
    def model(self):
        """`Module`: The module instantiated. For a hierarchical instance, this is the model of the leaf instance."""
        raise NotImplementedError

    @abstractproperty
    def hierarchy(self):
        """:obj:`Sequence` [`Instance` ]: Hierarchy of this instance in bottom-up order."""
        raise NotImplementedError

    @property
    def pins(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Pin` or `HierarchicalPin`]: Pins of this instance."""
        return _InstancePinsProxy(self)

    def _extend_hierarchy(self, *, above = None, below = None):
        """Extend the hierarchy.

        Keyword Args:
            above (`AbstractInstance` or :obj:`Sequence` [`Instance`]): Append above the current hierarchy
            below (`AbstractInstance` or :obj:`Sequence` [`Instance`]): Append below the current hierarchy 

        Returns:
            `AbstractInstance`:
        """
        hierarchy = self.hierarchy
        if above is not None:
            hierarchy = hierarchy + (above.hierarchy if isinstance(above, AbstractInstance) else above)
        if below is not None:
            hierarchy = (below.hierarchy if isinstance(below, AbstractInstance) else below) + hierarchy
        if len(hierarchy) > 1:
            return HierarchicalInstance(hierarchy)
        else:
            return hierarchy[0]

    def _shrink_hierarchy(self, *, low = None, high = None):
        """Shrink the hierarchy.

        Keyword Args:
            low (:obj:`int`): The lowest hierarchy (INCLUSIVE) to be kept
            high (:obj:`int`): The highest hierarchy (EXCLUSIVE) to be kept

        Returns:
            `AbstractInstance`:

        Notes:
            The difference in the inclusiveness of args ``low`` and ``high`` is intended to match the list indexing
            mechanism in Python.
        """
        hierarchy = self.hierarchy[low:high]
        if len(hierarchy) == 0:
            return None
        elif len(hierarchy) > 1:
            return HierarchicalInstance(hierarchy)
        else:
            return hierarchy[0]

# ----------------------------------------------------------------------------
# -- Instance ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class Instance(AbstractInstance):
    """Direct sub-instance in a module.

    Args:
        parent (`Module`): Parent module
        model (`Module`): Model of this instance
        name (:obj:`str`): Name of the instance

    Keyword Args:
        key (:obj:`Hashable`): A hashable key used to index this instance in the instances mapping in the parent
            module. If not set \(default argument: ``None``\), ``name`` is used by default
        **kwargs: Custom attributes associated with this instance
    """

    __slots__ = ['_parent', '_model', '_name', '_key', '_pins', '__dict__']

    # == internal API ========================================================
    def __init__(self, parent, model, name, *, key = None, **kwargs):
        self._parent = parent
        self._model = model
        self._name = name
        self._key = uno(key, name)
        self._pins = OrderedDict()

        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def __repr__(self):
        return 'Instance({}/{}[{}])'.format(self._parent.name, self._name, self._model.name)

    # == low-level API =======================================================
    @property
    def name(self):
        """:obj:`str`: Name of this instance."""
        return self._name

    @property
    def key(self):
        """:obj:`Hashable`: A hashable key used to index this instance in the parent module's isntance mapping."""
        return self._key

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_hierarchical(self):
        return False

    @property
    def parent(self):
        return self._parent

    @property
    def model(self):
        return self._model

    @property
    def hierarchy(self):
        return (self, )

# ----------------------------------------------------------------------------
# -- Hierarchical Instance ---------------------------------------------------
# ----------------------------------------------------------------------------
class HierarchicalInstance(AbstractInstance):
    """Hierarchical instance in a module.

    Args:
        hierarchy (:obj:`Sequence` [:obj:`Instance` ]): Hierarchy in bottom-up order.

    Notes:
        Direct instantiation of this class is not recommended. Use `AbstractInstance._shrink_hierarchy`,
        `AbstractInstance._extend_hierarchy`, or `ModuleUtils._dereference` instead.
    """

    __slots__ = ["hierarchy"]

    # == internal API ========================================================
    def __init__(self, hierarchy):
        if len(hierarchy) < 2:
            raise PRGAInternalError("Cannot create hierarchical instance with less than 2 levels")
        self.hierarchy = hierarchy

    def __repr__(self):
        s = '{}/{}'.format(self.hierarchy[-1].parent.name, self.hierarchy[-1].name)
        for inst in reversed(self.hierarchy[:-1]):
            s += "[{}]/{}".format(inst.parent.name, inst.name)
        s += "[{}]".format(self.model.name)
        return "HierInstance({})".format(s)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_hierarchical(self):
        return True

    @property
    def parent(self):
        return self.hierarchy[-1].parent

    @property
    def model(self):
        return self.hierarchy[0].model
