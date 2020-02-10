# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import AbstractModule
from ..net.common import NetType
from ...util import Object, ReadonlyMappingProxy
from ...exception import PRGAInternalError

from collections import OrderedDict
import networkx as nx

__all__ = ['Module']

# ----------------------------------------------------------------------------
# -- Module ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Module(Object, AbstractModule):
    """A netlist module.

    Args:
        name (:obj:`str`): Name of the module
        key (:obj:`Hashable`): A hashable key used to index this net in the parent module/instance. If not given
            \(default argument: ``None``\), ``name`` is used by default
        ports (:obj:`Mapping`): A mapping object used to index ports by keys. No object by default, disallowing ports
            to be added into this module
        logics (:obj:`Mapping`): A mapping object used to index logic nets by keys. No object by default, disallowing
            logic nets to be added into this module
        instances (:obj:`Mapping`): A mapping object used to index instances by keys. No object by default, disallowing
            instances to be added into this module
        allow_multisource (:obj:`bool`): If set, a sink net may be driven by multiple source nets
        **kwargs: Custom key-value arguments. For each key-value pair ``key: value``, ``setattr(self, key, value)``
            is executed at the BEGINNING of ``__init__``
    """

    __slots__ = ['_name', '_key', '_children', '_ports', '_logics', '_instances', '_conn_graph', '_allow_multisource',
            '__dict__']

    # == internal API ========================================================
    def __init__(self, name, key = None, ports = None, logics = None, instances = None, allow_multisource = False,
            **kwargs):
        for k, v in iteritems(kwargs):
            setattr(self, k, v)
        self._name = name
        if key is not None:
            self._key = key
        self._children = OrderedDict()  # Mapping from names to children (ports, logics and instances)
        if ports is not None:
            self._ports = ports
        if logics is not None:
            self._logics = logics
        if instances is not None:
            self._instances = instances
        self._allow_multisource = allow_multisource
        self._conn_graph = nx.DiGraph()

    def __str__(self):
        return 'Module({})'.format(self.name)

    # == low-level API =======================================================
    def _add_net(self, net):
        """Add ``net`` into this module.

        Args:
            net (`AbstractNet`):
        """
        # check parent of the net
        if net.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent of '{}'"
                    .format(self, net))
        # check name conflict
        if net.name in self._children:
            raise PRGAInternalError("Name '{}' taken by {} in module '{}'".format(net.name,
                self._children[net.name], self))
        # check ports/logics modifiable and key conflict
        try:
            if net.net_type.is_port:
                port = self._ports.setdefault(net.key, net)
                if port is not net:
                    raise PRGAInternalError("Port key '{}' taken by {} in module '{}'".format(net.key, port, self))
            elif net.net_type.is_logic:
                logic = self._logics.setdefault(net.key, net)
                if logic is not net:
                    raise PRGAInternalError("Logic net key '{}' taken by {} in module '{}'".format(net.key, logic, self))
            else:
                raise PRGAInternalError("Cannot add '{}' to module '{}'".format(net, self))
        except AttributeError:
            raise PRGAInternalError("Cannot add '{}' to module '{}'".format(net, self))
        # add net to children mapping
        return self._children.setdefault(net.name, net)

    def _add_instance(self, instance):
        """Add ``instance`` into this module.

        Args:
            instance (`AbstractInstance`):
        """
        # check parent of the instance
        if instance.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent of '{}'"
                    .format(self, instance))
        # check name conflict
        if instance.name in self._children:
            raise PRGAInternalError("Name '{}' taken by {} in module '{}'"
                    .format(instance.name, self._children[net.name], self))
        # check instances modifiable and key conflict
        try:
            value = self._instances.setdefault(instance.key, instance)
            if value is not instance:
                raise PRGAInternalError("Instance key '{}' taken by {} in module '{}'"
                        .format(instance.key, value, self))
        except AttributeError:
            raise PRGAInternalError("Cannot add '{}' to module '{}'".format(instance, self))
        # add instance to children mapping
        return self._children.setdefault(instance.name, instance)

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
        return ReadonlyMappingProxy(self._children)

    @property
    def ports(self):
        try:
            return ReadonlyMappingProxy(self._ports)
        except AttributeError:
            return ReadonlyMappingProxy({})

    @property
    def logics(self):
        try:
            return ReadonlyMappingProxy(self._logics)
        except AttributeError:
            return ReadonlyMappingProxy({})

    @property
    def instances(self):
        try:
            return ReadonlyMappingProxy(self._instances)
        except AttributeError:
            return ReadonlyMappingProxy({})
