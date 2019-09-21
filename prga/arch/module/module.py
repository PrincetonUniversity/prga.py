# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.module.common import ModuleClass
from prga.exception import PRGAInternalError
from prga.util import Abstract, ReadonlyMappingProxy

from abc import abstractproperty, abstractmethod

__all__ = ['AbstractModule']

# ----------------------------------------------------------------------------
# -- Abstract Module ---------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractModule(Abstract):
    """Abstract base class for modules."""

    # == internal API ========================================================
    def __str__(self):
        return self.name

    def _add_port(self, port):
        """Add a port to this module.

        Args:
            port (`AbstractPort`):

        Returns:
            `AbstractPort`: Echoing back the added port
        """
        if port.is_physical and not self.is_physical:
            raise PRGAInternalError("Cannot add a physical port '{}' to a non-physical module '{}'"
                    .format(port, self))
        elif port.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent module of port '{}'"
                    .format(self, port))
        elif port.key in self.all_ports:
            raise PRGAInternalError("Key '{}' for port '{}' already exists in module '{}'"
                    .format(port.key, port, self))
        return self.setdefault(port.key, port)

    def _add_instance(self, instance):
        """Add an instance to this module.

        Args:
            instance (`AbstractInstance`):

        Returns:
            `AbstractInstance`: Echoing back the added instance
        """
        if instance.is_physical and not self.is_physical:
            raise PRGAInternalError("Cannot add a physical instance '{}' to a non-physical module '{}'"
                    .format(instance, self))
        elif instance.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent module of instance '{}'"
                    .format(self, instance))
        elif instance.key in self.all_instances:
            raise PRGAInternalError("Key '{}' for instance '{}' already exists in module '{}'"
                    .format(instance.key, instance, self))
        return self.setdefault(instance.key, instance)

    # == low-level API =======================================================
    @property
    def physical_ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to physical ports
        in this module."""
        return ReadonlyMappingProxy(self.all_ports, lambda kv: kv[1].is_physical)

    @property
    def physical_instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to physical
        instances in this module."""
        return ReadonlyMappingProxy(self.all_instances, lambda kv: kv[1].is_physical)

    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def all_ports(self):
        """:obj:`MutableMapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to ports in
        this module. Note that physical/logical/user ports are mixed together in this mapping."""
        raise NotImplementedError

    @abstractproperty
    def all_instances(self):
        """:obj:`MutableMapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from some hashable indices to
        instances in this module. Note that physical/logical/user instances are mixed together in this mapping."""
        raise NotImplementedError

    @property
    def is_physical(self):
        """:obj:`bool`: Test if this module is physical."""
        return True

    @abstractproperty
    def name(self):
        """:obj:`str`: Name of this module."""
        raise NotImplementedError

    @abstractproperty
    def module_class(self):
        """`ModuleClass`: Logical class of this module."""
        raise NotImplementedError

    @property
    def verilog_template(self):
        """:obj:`str`: Template used for generating Verilog model of this module."""
        return 'module.tmpl.v'

    @abstractproperty
    def verilog_source(self):
        """:obj:`str`: Path to the source file generated for this module."""
        raise NotImplementedError

    # == high-level API ======================================================
    @property
    def ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to user-accessible
        ports."""
        return ReadonlyMappingProxy(self.all_ports, lambda kv: kv[1].is_user_accessible)

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from some hashable indices to
        user-accessible instances."""
        return ReadonlyMappingProxy(self.all_instances, lambda kv: kv[1].is_user_accessible)

    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractmethod
    def instantiate(self, model, name):
        """Instantiate a module and add it to this module as a sub-instance.

        Args:
            model (`AbstractModule`):
            name (:obj:`str`):
        """
        raise NotImplementedError

    @abstractmethod
    def connect(self, sources, sinks, fully_connected = False, pack_pattern = False):
        """Connect a sequence of source net bits to a sequence of sink net bits.

        Args:
            sources (:obj:`Sequence` [`AbstractSourceBit` ]):
            sinks (:obj:`Sequence` [`AbstractSinkBit` ]):
            fully_connected (:obj:`bool`): Connections are created bit-wise by default. If ``fully_connected`` is set,
                connections are created in a all-to-all manner
            pack_pattern (:obj:`bool`): An advanced feature in VPR
        """
        raise NotImplementedError
