# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Enum, Abstract, Object

from abc import abstractproperty

__all__ = []

# ----------------------------------------------------------------------------
# -- Abstract Netlist Object (Module/Instance) -------------------------------
# ----------------------------------------------------------------------------
class AbstractNetlistObject(Abstract):
    """Abstract class for modules and instances."""

    @abstractproperty
    def name(self):
        """:obj:`str`: String name of this module/instance (to be used in Verilog/VPR)"""
        raise NotImplementedError

    @abstractproperty
    def key(self):
        """:obj:`Hashable`: A hashable key used to index this instance in the parent module, or this module in the
        database."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Module ---------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractModule(AbstractNetlistObject):
    """Abstract class for modules."""

    @abstractproperty
    def children(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractNetlistObject` or `AbstractNet` ]: A mapping from names to
        ports/logic nets/instances."""
        raise NotImplementedError

    @abstractproperty
    def ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Port` ]: A mapping from port keys to ports."""
        raise NotImplementedError

    @abstractproperty
    def logics(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Logic` ]: A mapping from logic keys to logic nets."""
        raise NotImplementedError

    @abstractproperty
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from instance keys to instances."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Instance -------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractInstance(AbstractNetlistObject):
    """Abstract class for instances."""

    @abstractproperty
    def children(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractNet` ]: A mapping from names to pins."""
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
