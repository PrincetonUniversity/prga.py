# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import NetType
from prga.util import Abstract

from abc import abstractproperty, abstractmethod

__all__ = ['AbstractBit', 'AbstractSourceBit', 'AbstractSinkBit', 'AbstractBus']

# ----------------------------------------------------------------------------
# -- Abstract Bit ------------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractBit(Abstract):
    """Abstract base class for all bits."""

    # == internal API ========================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def _is_static(self):
        """:obj:`bool`: Test if this bit is static."""
        raise NotImplementedError

    @abstractproperty
    def _static_cp(self):
        """`AbstractBit` or ``None``: The static counterpart of this bit."""
        raise NotImplementedError

    @abstractmethod
    def _get_or_create_static_cp(self):
        """Get the static counterpart of this (dynamic) bit. Create if not found.
            
        Returns:
            `AbstractBit`: the static counterpart if found or created
        """
        raise NotImplementedError

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def is_physical(self):
        """:obj:`bool`: Test if this net is physical."""
        raise NotImplementedError

    @abstractproperty
    def is_user_accessible(self):
        """:obj:`bool`: Test if this net is user-accessible."""
        raise NotImplementedError

    @abstractproperty
    def physical_cp(self):
        """`AbstractBit`: Physical counterpart of this bit."""
        raise NotImplementedError

    @abstractproperty
    def net_type(self):
        """`NetType`: Type of this net."""
        raise NotImplementedError
 
    @abstractproperty
    def is_sink(self):
        """:obj:`bool`: Test if this net is a sink."""
        raise NotImplementedError

    @property
    def is_bus(self):
        """:obj:`bool`: Test if this net is a bus."""
        return False

# ----------------------------------------------------------------------------
# -- Abstract Source Bit -----------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractSourceBit(AbstractBit):
    """Abstract base class for all source bits."""

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_sink(self):
        return False

# ----------------------------------------------------------------------------
# -- Abstract Sink Bit -------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractSinkBit(AbstractBit):
    """Abstract base class for all sink bits."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def physical_source(self):
        """`AbstractSourceBit`: Physical source of this bit."""
        raise NotImplementedError

    @abstractproperty
    def logical_source(self):
        """`AbstractSourceBit`: Logical source of this bit."""
        raise NotImplementedError

    @abstractproperty
    def user_sources(self):
        """:obj:`Sequence` [`AbstractSourceBit` ]: User sources of this bit."""
        raise NotImplementedError

    @abstractmethod
    def add_user_sources(self, sources):
        """Add user sources to this bit.

        Args:
            sources (:obj:`Iterable` [`AbstractSourceBit` ]):
        """
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_sink(self):
        return True

# ----------------------------------------------------------------------------
# -- Abstract Bus ------------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractBus(Abstract, Sequence):
    """Abstract base class for all buses."""

    # == internal API ========================================================
    def __len__(self):
        return len(self._static_bits)

    def __getitem__(self, index):
        try:
            return self._static_bits[index]
        except AttributeError:
            if isinstance(index, int):
                if index < 0 or index >= self.width:
                    raise IndexError
                return self._get_or_create_bit(index, True)
            elif isinstance(index, slice):
                return tuple(self._get_or_create_bit(i, True) for i in
                        tuple(range(self.width))[index])

    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def _static_bits(self):
        """:obj:`Sequence` [`AbstractBit` ]: Array of bits in this bus."""
        raise NotImplementedError

    @abstractmethod
    def _get_or_create_bit(self, index, dynamic):
        """Get the ``index``-th bit in this bus. Create a bit if not already created.

        Args:
            index (:obj:`int`):
            dynamic (:obj:`bool`): If set, dynamic bit will be created
        """
        raise NotImplementedError

    # == low-level API =======================================================
    @property
    def is_bus(self):
        """:obj:`bool`: Test if this net is a bus."""
        return True

    @abstractproperty
    def physical_cp(self):
        """:obj:`Sequence` [`AbstractBit` ]: Physical counterpart of this bus."""
        raise NotImplementedError

    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def is_physical(self):
        """:obj:`bool`: Test if this net is physical."""
        raise NotImplementedError

    @abstractproperty
    def is_user_accessible(self):
        """:obj:`bool`: Test if this net is user-accessible."""
        raise NotImplementedError

    @abstractproperty
    def net_type(self):
        """`NetType`: Type of this net."""
        raise NotImplementedError
 
    @abstractproperty
    def is_sink(self):
        """:obj:`bool`: Test if this net is a sink."""
        raise NotImplementedError

    @abstractproperty
    def width(self):
        """:obj:`int`: Number of bits in this bus."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Abstract Port -----------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractPort(AbstractBus):
    """Abstract base class for ports."""

    # == internal API ========================================================
    def __str__(self):
        return '{}/{}'.format(self.parent, self.name)

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def parent(self):
        """`AbstractModule`: Parent module of this port."""
        raise NotImplementedError

    @abstractproperty
    def name(self):
        """:obj:`str`: Name of this port."""
        raise NotImplementedError

    @abstractproperty
    def direction(self):
        """:obj:`bool`: Direction of this port."""
        raise NotImplementedError

    @abstractproperty
    def is_clock(self):
        """:obj:`bool`: Test if this is a clock port."""
        raise NotImplementedError

    @property
    def key(self):
        """:obj:`Hashable`: Index of this port in the port mapping of the parent module."""
        return self.name

    @abstractproperty
    def net_class(self):
        """`NetClass`: Logical class of this net."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return NetType.port

# ----------------------------------------------------------------------------
# -- Abstract Pin ------------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractPin(AbstractBus):
    """Abstract base class for pins."""

    # == internal API ========================================================
    def __str__(self):
        return '{}/{}'.format(self.parent, self.name)

    # == low-level API =======================================================
    @property
    def name(self):
        """:obj:`str`: Name of this pin."""
        return self.model.name

    @property
    def direction(self):
        """:obj:`bool`: Direction of this pin."""
        return self.model.direction

    @property
    def is_clock(self):
        """:obj:`bool`: Test if this is a clock pin."""
        raise self.model.is_clock

    @property
    def net_class(self):
        """`NetClass`: Logical class of this net."""
        return self.model.net_class

    @property
    def key(self):
        """:obj:`Hashable`: Index of this pin in the pin mapping of the parent instance."""
        return self.model.key

    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def model(self):
        """`AbstractPort`: Model of this pin."""
        raise NotImplementedError

    @abstractproperty
    def parent(self):
        """`AbstractInstance`: Parent instance of this pin."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_user_accessible(self):
        return self.model.is_user_accessible

    @property
    def net_type(self):
        return NetType.pin

    @property
    def width(self):
        return self.model.width
