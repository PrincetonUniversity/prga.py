# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Common enums and abstract base classes for modules."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...util import Enum, Abstract, Object

from abc import abstractproperty, abstractmethod
from enum import Enum
import networkx as nx

__all__ = []

# ----------------------------------------------------------------------------
# -- Abstract Module ---------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractModule(Abstract):
    """Abstract class for modules."""

    @abstractproperty
    def name(self):
        """:obj:`str`: Name of this module."""
        raise NotImplementedError

    @abstractproperty
    def key(self):
        """:obj:`Hashable`: A hashable key used to index this module in the database."""
        raise NotImplementedError

    @abstractproperty
    def children(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractPort` or `AbstractInstance` ]: A mapping from names to
        ports/immediate instances."""
        raise NotImplementedError

    @abstractproperty
    def ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Port` ]: A mapping from port keys to ports."""
        raise NotImplementedError

    @abstractproperty
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from instance keys to immediate instances."""
        raise NotImplementedError

    @abstractproperty
    def is_cell(self):
        """:obj:`bool`: Test if this module is a leaf cell."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Instance -------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractInstance(Abstract):
    """Abstract class for instances."""

    @abstractproperty
    def is_hierarchical(self):
        """:obj:`bool`: Test if this is a hierarchical instance."""
        raise NotImplementedError

    @abstractproperty
    def parent(self):
        """`AbstractModule`: Parent module of this instance."""
        raise NotImplementedError

    @abstractproperty
    def model(self):
        """`AbstractModule`: Model of this instance."""
        raise NotImplementedError

    @abstractproperty
    def pins(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Pin` ]: A mapping from port keys to pins."""
        raise NotImplementedError

    @abstractproperty
    def hierarchy(self):
        """:obj:`Sequence` [`Instance` ]: Hierarchy in bottom-up order."""
        raise NotImplementedError

    @abstractmethod
    def extend_hierarchy(self, *, above = None, below = None):
        """`AbstractInstance`: Build a hierarchical instance with additional hierarchy below
        and/or above the current instance."""
        raise NotImplementedError

    @abstractmethod
    def shrink_hierarchy(self, index):
        """`AbstractInstance`: Shrink the current hierarchy.

        Args:
            index (:obj:`int` or :obj:`slice`):
        """
        raise NotImplementedError

    @property
    def node(self):
        """:obj:`Hashable`: Key of this instance in a module's connection graph."""
        return tuple(inst.key for inst in self.hierarchy)

# ----------------------------------------------------------------------------
# -- Memory-Optimized Connection Graph ---------------------------------------
# ----------------------------------------------------------------------------
class _Placeholder(Enum):
    placeholder = 0

class _MemOptNonCoalescedNodeDict(MutableMapping):

    __slots__ = ['_dict']
    def __init__(self):
        self._dict = {}

    def __getitem__(self, k):
        idx, key = k
        try:
            v = self._dict[key][idx]
        except (KeyError, IndexError):
            raise KeyError(k)
        if v is _Placeholder.placeholder:
            raise KeyError(k)
        return v

    def __setitem__(self, k, v):
        idx, key = k
        try:
            l = self._dict[key]
        except KeyError:
            l = tuple()
            self._dict[key] = tuple(_Placeholder.placeholder for i in range(idx)) + (v, )
        if idx >= len(l):
            self._dict[key] = l +  tuple(_Placeholder.placeholder for i in range(idx - len(l))) + (v, )
        else:
            self._dict[key] = tuple(v if i == idx else item for i, item in enumerate(l))

    def __delitem__(self, k):
        idx, key = k
        l = self._dict[key]
        if idx >= len(l):
            raise KeyError(k)
        elif idx == len(l) - 1:
            if len(l) == 1:
                del self._dict[key]
            else:
                self._dict[key] = tuple(iter(l[:-1]))
        else:
            self._dict[key] = tuple(_Placeholder.placeholder if i == idx else item for i, item in enumerate(l))

    def __len__(self):
        return sum(1 for _ in iter(self))

    def __iter__(self):
        for key, l in iteritems(self._dict):
            for idx, item in enumerate(l):
                if item is not _Placeholder.placeholder:
                    yield idx, key

_attr_dict_factories = {}
def _get_attr_dict_factory(slots = tuple()):
    slots = tuple(sorted(slots))

    # shortcut
    if factory := _attr_dict_factories.get( slots ):
        return factory
    elif not slots:
        _attr_dict_factories[slots] = dict
        return dict

    # create new class
    class _AttrDict(MutableMapping):
        "Memory optimized attribute dict."

        __slots__ = ('_dict', ) + slots

        def __getitem__(self, k):
            if k in self.__slots__:
                try:
                    return getattr(self, k)
                except AttributeError:
                    raise KeyError(k)
            else:
                try:
                    return self._dict[k]
                except AttributeError:
                    raise KeyError(k)

        def __setitem__(self, k, v):
            if k in self.__slots__:
                setattr(self, k, v)
            else:
                try:
                    self._dict[k] = v
                except AttributeError:
                    self._dict = {k: v}

        def __delitem__(self, k):
            if k in self.__slots__:
                try:
                    delattr(self, k)
                except AttributeError:
                    raise KeyError(k)
            else:
                try:
                    del self._dict[k]
                except AttributeError:
                    raise KeyError(k)

        def __len__(self):
            return sum(1 for _ in iter(self))

        def __iter__(self):
            for k in self.__slots__:
                if hasattr(self, k):
                    yield k
            try:
                for k in self._dict:
                    yield k
            except AttributeError:
                return

        def __reduce__(self):
            return AttrDict, slots

    # register and return class
    _attr_dict_factories[slots] = _AttrDict
    return _AttrDict

def AttrDict(slots = tuple()):
    """Construct a memory-optimized connection graph node.

    Args:
        slots (:obj:`Sequence` [:obj:`str` ]): Pre-allocated keys

    Returns:
        :obj:`MutableMapping`:
    """
    return _get_conn_graph_factory(slots)()

_conn_graph_factories = {}
def _get_conn_graph_factory(
        coalesce_connections = False,
        node_attr_slots = tuple(),
        edge_attr_slots = tuple()):
    node_attr_slots = tuple(sorted(node_attr_slots))
    edge_attr_slots = tuple(sorted(edge_attr_slots))

    # shortcut
    if factory := _conn_graph_factories.get( (coalesce_connections, node_attr_slots, edge_attr_slots) ):
        return factory

    # create new class
    if coalesce_connections:
        class _ConnGraph(nx.DiGraph):
            """Memory-optimized connection graph."""

            node_attr_dict_factory = _get_attr_dict_factory(node_attr_slots)
            edge_attr_dict_factory = _get_attr_dict_factory(edge_attr_slots)

            def __reduce__(self):
                return ConnGraph, (True, node_attr_slots, edge_attr_slots)

        factory = _ConnGraph
    else:
        class _ConnGraph(nx.DiGraph):
            """Memory-optimized connection graph."""

            node_dict_factory = _MemOptNonCoalescedNodeDict
            node_attr_dict_factory = _get_attr_dict_factory(node_attr_slots)
            adjlist_outer_dict_factory = _MemOptNonCoalescedNodeDict
            edge_attr_dict_factory = _get_attr_dict_factory(edge_attr_slots)

            def __reduce__(self):
                return ConnGraph, (False, node_attr_slots, edge_attr_slots)

        factory = _ConnGraph

    # register and return class
    _conn_graph_factories[coalesce_connections, node_attr_slots, edge_attr_slots] = factory
    return factory

def ConnGraph(
        coalesce_connections = False,
        node_attr_slots = tuple(),
        edge_attr_slots = tuple()):
    """Construct a memory-optimized connection graph.

    Args:
        coalesce_connections (:obj:`bool`): If set to ``True``, not bitwise connections are allowed in the connection
            graph
        node_attr_slots (:obj:`Sequence` [:obj:`str` ]):
        edge_attr_slots (:obj:`Sequence` [:obj:`str` ]):

    Returns:
        `networkx.DiGraph`_:

    .. networkx.DiGraph:
        https://networkx.github.io/documentation/networkx-2.4/reference/classes/digraph.html
    """
    return _get_conn_graph_factory(coalesce_connections, node_attr_slots, edge_attr_slots)()
