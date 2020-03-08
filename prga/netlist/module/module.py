# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import AbstractModule
from .instance import HierarchicalInstance
from ..net.common import NetType
from ...util import Object, ReadonlyMappingProxy, uno
from ...exception import PRGAInternalError

from collections import OrderedDict
from enum import Enum
import networkx as nx

__all__ = ['Module']

# ----------------------------------------------------------------------------
# -- Hierarchical Instance Mapping Proxy -------------------------------------
# ----------------------------------------------------------------------------
class _HierarchicalInstanceProxy(Object, Mapping):
    """Helper class for `AbstractModule.hierarchy` property.

    Args:
        module (`AbstractModule`):
    """

    __slots__ = ['module']
    def __init__(self, module):
        super(_HierarchicalInstanceProxy, self).__init__()
        self.module = module

    def __getitem__(self, key):
        try:
            parent, instances = self.module, []
            for k in reversed(key):
                instance = parent.instances[k]
                parent = instance.model
                instances.append(instance)
            if len(instances) == 0:
                return tuple()
            elif len(instances) == 1:
                return instances[0]
            else:
                return HierarchicalInstance(reversed(instances))
        except KeyError:
            raise KeyError(key)

    def __len__(self):
        raise PRGAInternalError("`{}.hierarchy` property is for key-value access only"
                .format(type(self.module)))

    def __iter__(self):
        raise PRGAInternalError("`{}.hierarchy` property is for key-value access only"
                .format(type(self.module)))

# ----------------------------------------------------------------------------
# -- Module ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Module(Object, AbstractModule):
    """A netlist module.

    Args:
        name (:obj:`str`): Name of the module

    Keyword Args:
        key (:obj:`Hashable`): A hashable key used to index this module in the database. If not given \(default
            argument: ``None``\), ``name`` is used by default
        ports (:obj:`Mapping`): A mapping object used to index ports by keys. ``None`` by default, which disallows
            ports to be added into this module
        instances (:obj:`Mapping`): A mapping object used to index instances by keys. ``None`` by default, which
            disallows instances to be added into this module
        conn_graph (`networkx.DiGraph`_): Connection & Timing Graph. It's strongly recommended to subclass
            `networkx.DiGraph`_ to optimize memory usage
        allow_multisource (:obj:`bool`): If set, a sink net may be driven by multiple source nets. Incompatible with
            ``coalesce_connections``
        coalesce_connections (:obj:`bool`): If set, all connections are made at the granularity of buses.
            Incompatible with ``allow_multisource``.
        **kwargs: Custom key-value arguments. For each key-value pair ``key: value``, ``setattr(self, key, value)``
            is executed at the BEGINNING of ``__init__``

    .. _networkx.DiGraph: https://networkx.github.io/documentation/stable/reference/classes/digraph.html#networkx.DiGraph
    """

    __slots__ = ['_name', '_key', '_children', '_ports', '_instances', '_conn_graph',
            '_allow_multisource', '_coalesce_connections', '_hierarchy', '__dict__']

    # == internal API ========================================================
    def __init__(self, name, *,
            key = None, ports = None, instances = None, conn_graph = None,
            allow_multisource = False, coalesce_connections = False, **kwargs):
        if allow_multisource and coalesce_connections:
            raise PRGAInternalError("`allow_multisource` and `coalesce_connections` are incompatible")
        self._name = name
        self._key = uno(key, name)
        self._children = OrderedDict()  # Mapping from names to children (ports and instances)
        if ports is not None:
            self._ports = ports
        if instances is not None:
            self._instances = instances
        self._allow_multisource = allow_multisource
        self._coalesce_connections = coalesce_connections
        self._conn_graph = uno(conn_graph, nx.DiGraph())
        self._hierarchy = _HierarchicalInstanceProxy(self)
        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def __str__(self):
        return 'Module({})'.format(self.name)

    # == low-level API =======================================================
    def _add_port(self, port):
        """Add ``port`` into this module.

        Args:
            port (`AbstractPort`):
        """
        # check parent of the port
        if port.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent of '{}'".format(self, port))
        # check name conflict
        if port.name in self._children:
            raise PRGAInternalError("Name '{}' taken by {} in module '{}'"
                    .format(port.name, self._children[port.name], self))
        # check ports modifiable and key conflict
        try:
            value = self._ports.setdefault(port.key, port)
            if value is not port:
                raise PRGAInternalError("Port key '{}' taken by {} in module '{}'".format(port.key, value, self))
        except AttributeError:
            raise PRGAInternalError("Cannot add '{}' to module '{}'".format(port, self))
        # add port to children mapping
        return self._children.setdefault(port.name, port)

    def _add_instance(self, instance):
        """Add ``instance`` into this module.

        Args:
            instance (`AbstractInstance`):
        """
        # check parent of the instance
        if instance.parent is not self:
            raise PRGAInternalError("Module '{}' is not the parent of '{}'".format(self, instance))
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
        return self._key

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
    def instances(self):
        try:
            return ReadonlyMappingProxy(self._instances)
        except AttributeError:
            return ReadonlyMappingProxy({})

    @property
    def hierarchy(self):
        return self._hierarchy
