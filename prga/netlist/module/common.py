# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...util import Enum, Abstract, Object

from abc import abstractproperty

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
        ports/instances."""
        raise NotImplementedError

    @abstractproperty
    def ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Port` ]: A mapping from port keys to ports."""
        raise NotImplementedError

    @abstractproperty
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from instance keys to immediate instances."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Instance -------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractInstance(Abstract):
    """Abstract class for instances."""

    @abstractproperty
    def name(self):
        """:obj:`str`: Name of this instance."""
        raise NotImplementedError

    @abstractproperty
    def key(self):
        """:obj:`Hashable`: A hashable key used to index this instance in its parent module."""
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
