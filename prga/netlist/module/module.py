# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Modules."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import AbstractModule, ConnGraph
from ...util import Object, ReadonlyMappingProxy, uno
from ...exception import PRGAInternalError

# In Python 3.7 and above, ``dict`` preserves insertion order and is more performant than ``OrderedDict``
OrderedDict = dict

from enum import Enum

__all__ = ['Module']

# ----------------------------------------------------------------------------
# -- Module ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Module(Object, AbstractModule):
    """A netlist module.

    Args:
        name (:obj:`str`): Name of the module

    Keyword Args:
        key (:obj:`Hashable`): A hashable key used to index this module in the database. If not set \(default
            argument: ``None``\), ``name`` is used by default
        is_cell (:obj:`bool`): If set to ``True``, the following arguments are overwritten: ``instances`` is set to
            ``False``, ``allow_multisource`` is set to ``True``, ``coalesce_connections`` is set to ``False``
        instances (:obj:`MutableMapping` or :obj:`bool`): If set to ``False``, no instance mapping is created,
            marking this module as a leaf cell which contains no sub-modules; If set to ``True``, an ``OrderedDict``
            object is created for the instance mapping; Otherwise, the given argument is used for the instance
            mapping.
        conn_graph (`networkx.DiGraph`_): Connection & Timing Graph
        allow_multisource (:obj:`bool`): If set to ``True``, a sink net may be driven by multiple source nets.
            Incompatible with ``coalesce_connections``
        coalesce_connections (:obj:`bool`): If set to ``True``, bit-wise connections are not allowed.
            Incompatible with ``allow_multisource``.
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes

    .. _networkx.DiGraph: https://networkx.github.io/documentation/stable/reference/classes/digraph.html#networkx.DiGraph
    """

    __slots__ = ['_name', '_key', '_children', '_ports', '_instances', '_conn_graph',
            '_allow_multisource', '_coalesce_connections', '__dict__']

    # == internal API ========================================================
    def __init__(self, name, *,
            key = None, is_cell = False, instances = True, conn_graph = None,
            allow_multisource = False, coalesce_connections = False, **kwargs):
        if not is_cell and allow_multisource and coalesce_connections:
            raise PRGAInternalError("`allow_multisource` and `coalesce_connections` are incompatible")
        self._name = name
        self._key = uno(key, name)
        self._children = OrderedDict()  # Mapping from names to children (ports and instances)
        self._ports = OrderedDict()
        if is_cell:
            self._allow_multisource = True
            self._coalesce_connections = False
        else:
            if isinstance(instances, MutableMapping):
                self._instances = instances
            elif instances:
                self._instances = OrderedDict()
            self._allow_multisource = allow_multisource
            self._coalesce_connections = coalesce_connections
        if conn_graph is not None:
            self._conn_graph = conn_graph
        else:
            self._conn_graph = ConnGraph(self._coalesce_connections)
        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def __repr__(self):
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
        return ReadonlyMappingProxy(self._ports)

    @property
    def instances(self):
        try:
            return ReadonlyMappingProxy(self._instances)
        except AttributeError:
            return ReadonlyMappingProxy({})

    @property
    def is_cell(self):
        return not hasattr(self, "_instances")
