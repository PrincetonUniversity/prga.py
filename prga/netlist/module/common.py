# -*- encoding: ascii -*-
# Python 2 and 3 compatible
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
    def hierarchy(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from hierarchical instance keys to
        hierarchical instances."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Instance -------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractInstance(Abstract, Sequence):
    """Abstract class for instances."""

    @abstractproperty
    def name(self):
        """:obj:`str`: Name of this instance."""
        raise NotImplementedError

    @abstractproperty
    def key(self):
        """:obj:`Hashable`: A hashable key used to index this instance in its immediate parent module."""
        raise NotImplementedError

    @abstractproperty
    def hierarchical_key(self):
        """:obj:`Hashable`: A hashable key used to index this instance in its ancestor parent module."""
        raise NotImplementedError

    @abstractproperty
    def pins(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Pin` ]: A mapping from port keys to pins."""
        raise NotImplementedError

    @abstractproperty
    def parent(self):
        """`AbstractModule`: Parent module of this instance."""
        raise NotImplementedError

    @abstractproperty
    def model(self):
        """`AbstractModule`: Model of this instance."""
        raise NotImplementedError

    @abstractmethod
    def extend(self, hierarchy):
        """`AbstractInstance`: Extend up the hierarchy."""
        raise NotImplementedError

    @abstractmethod
    def delve(self, hierarchy):
        """`AbstractInstance`: Extend down the hierarchy."""
        raise NotImplementedError

    @abstractproperty
    def is_hierarchical(self):
        """:obj:`bool`: Test if this instance is hierarchical, i.e. not immediate sub-instance of its parent module."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Memory-Optimized DiGraph for Non-Coalesced Connection Graph -------------
# ----------------------------------------------------------------------------
class _Placeholder(Enum):
    placeholder = 0

class _NodeDict(MutableMapping):

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

class MemOptNonCoalescedConnGraph(nx.DiGraph):
    node_dict_factory = _NodeDict
    adjlist_outer_dict_factory = _NodeDict

class LazyDict(MutableMapping):
    """Memory-optimized lazy dict."""

    __slots__ = ['_dict']

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
