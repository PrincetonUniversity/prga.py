# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.module.common import ModuleClass
from prga.exception import PRGAInternalError
from prga.util import Abstract, Object, ReadonlyMappingProxy

from abc import abstractproperty, abstractmethod

__all__ = ['AbstractModule', 'AbstractLeafModule', 'BaseModule']

# ----------------------------------------------------------------------------
# -- Abstract Module ---------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractModule(Abstract):
    """Abstract base class for modules."""

    # == internal API ========================================================
    def __str__(self):
        return self.name

    @property
    def _ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: Internal variable holding the ports."""
        return ReadonlyMappingProxy({})

    @property
    def _instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: Internal variable holding the instances."""
        return ReadonlyMappingProxy({})

    def _add_port(self, port):
        """Add a port to this module.

        Args:
            port (`AbstractPort`):

        Returns:
            `AbstractPort`: Echoing back the added port
        """
        if port.in_physical_domain and not self.in_physical_domain:
            raise PRGAInternalError("Cannot add a physical port '{}' to a non-physical module '{}'"
                    .format(port, self))
        elif port.in_logical_domain and not self.in_logical_domain:
            raise PRGAInternalError("Cannot add a logical port '{}' to a non-logical module '{}'"
                    .format(port, self))
        elif port.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent module of port '{}'"
                    .format(self, port))
        elif port.key in self._ports:
            raise PRGAInternalError("Key '{}' for port '{}' already exists in module '{}'"
                    .format(port.key, port, self))
        try:
            return self._ports.setdefault(port.key, port)
        except AttributeError:
            raise PRGAInternalError("Cannot add port '{}' to module '{}'. Port mapping is read-only"
                    .format(port, self))

    def _add_instance(self, instance):
        """Add an instance to this module.

        Args:
            instance (`AbstractInstance`):

        Returns:
            `AbstractInstance`: Echoing back the added instance
        """
        if instance.in_physical_domain and not self.in_physical_domain:
            raise PRGAInternalError("Cannot add a physical instance '{}' to a non-physical module '{}'"
                    .format(instance, self))
        elif instance.in_logical_domain and not self.in_logical_domain:
            raise PRGAInternalError("Cannot add a logical instance '{}' to a non-logical module '{}'"
                    .format(instance, self))
        elif instance.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent module of instance '{}'"
                    .format(self, instance))
        elif instance.key in self._instances:
            raise PRGAInternalError("Key '{}' for instance '{}' already exists in module '{}'"
                    .format(instance.key, instance, self))
        try:
            return self._instances.setdefault(instance.key, instance)
        except AttributeError:
            raise PRGAInternalError("Cannot add instance '{}' to module '{}'. Instance mapping is read-only"
                    .format(instance, self))

    # == low-level API =======================================================
    @property
    def physical_ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to physical ports
        in this module."""
        return ReadonlyMappingProxy(self.all_ports, lambda kv: kv[1].in_physical_domain)

    @property
    def logical_ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to logical ports
        in this module."""
        return ReadonlyMappingProxy(self.all_ports, lambda kv: kv[1].in_logical_domain)

    @property
    def physical_instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to physical
        instances in this module."""
        return ReadonlyMappingProxy(self.all_instances, lambda kv: kv[1].in_physical_domain)

    @property
    def logical_instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to logical
        instances in this module."""
        return ReadonlyMappingProxy(self.all_instances, lambda kv: kv[1].in_logical_domain)

    # -- properties/methods to be implemented/overriden by subclasses --------
    @property
    def all_ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractPort` ]: A mapping from some hashable indices to ports in
        this module. Note that physical/logical/user ports are mixed together in this mapping."""
        return ReadonlyMappingProxy(self._ports)

    @property
    def all_instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from some hashable indices to
        instances in this module. Note that physical/logical/user instances are mixed together in this mapping."""
        return ReadonlyMappingProxy(self._instances)

    @property
    def in_physical_domain(self):
        """:obj:`bool`: Test if this module is in the physical domain."""
        return not self.module_class.is_mode

    @property
    def in_logical_domain(self):
        """:obj:`bool`: Test if this module is in the logical domain."""
        return True

    @property
    def is_leaf_module(self):
        """:obj:`bool`: Test if this module is a leaf-level module."""
        return False

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
        return ReadonlyMappingProxy(self._ports, lambda kv: kv[1].in_user_domain)

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from some hashable indices to
        user-accessible instances."""
        return ReadonlyMappingProxy(self._instances, lambda kv: kv[1].in_user_domain)

# ----------------------------------------------------------------------------
# -- Abstract Leaf Module ----------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractLeafModule(AbstractModule):
    """Abstract base class for leaf modules."""

    # == internal API ========================================================
    def _elaborate(self):
        """Verify all the ``clock`` and ``combinational_sources`` attributes are valid."""
        for port in itervalues(self.ports):
            if port.is_clock:
                continue
            if port.clock is not None:
                clock = self.ports.get(port.clock, None)
                if clock is None:
                    raise PRGAInternalError("Clock '{}' of port '{}' not found in primitive '{}'"
                            .format(port.clock, port, self))
                elif not clock.is_clock:
                    raise PRGAInternalError("Clock '{}' of port '{}' in primitive '{}' is not a clock"
                            .format(clock, port, self))
            if port.direction.is_input:
                continue
            for source_name in port.combinational_sources:
                source = self.ports.get(source_name, None)
                if source is None:
                    raise PRGAInternalError("Combinational source '{}' of port '{}' not found in primitive '{}'"
                            .format(source_name, port, self))
                elif not source.direction.is_input:
                    raise PRGAInternalError("Combinational source '{}' of port '{}' in primitive '{}' is not an input"
                            .format(source_name, port, self))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_leaf_module(self):
        return True

# ----------------------------------------------------------------------------
# -- Base Module -------------------------------------------------------------
# ----------------------------------------------------------------------------
class BaseModule(Object, AbstractModule):
    """Base class for non-leaf modules.

    Args:
        name (:obj:`str`): Name of this module
    """

    __slots__ = ['_name', '_verilog_source']
    def __init__(self, name):
        super(BaseModule, self).__init__()
        self._name = name

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

    @property
    def verilog_source(self):
        try:
            return self._verilog_source
        except AttributeError:
            return None

    @verilog_source.setter
    def verilog_source(self, source):
        self._verilog_source = source
