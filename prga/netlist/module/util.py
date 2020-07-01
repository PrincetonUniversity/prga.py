# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Unitility methods for accessing modules and instances."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .module import Module
from .instance import Instance
from ..net.common import PortDirection
from ..net.util import NetUtils
from ..net.bus import Port, Pin
from ...exception import PRGAInternalError
from ...util import uno

from itertools import chain, product
from networkx import NetworkXError, DiGraph

import logging
_logger = logging.getLogger(__name__)

__all__ = ['ModuleUtils']

# ----------------------------------------------------------------------------
# -- Module Utilities --------------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleUtils(object):
    """A wrapper class for utility functions for modules."""

    @classmethod
    def create_port(cls, module, name, width, direction, *, key = None, is_clock = False, **kwargs):
        """Create a port in ``module``.

        Args:
            module (`AbstractModule`):
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Number of bits in the port
            direction (`PortDirection`): Direction of the port

        Keyword Args:
            key (:obj:`Hashable`): A hashable key used to index the port in the ``ports`` mapping the parent module.
                If not set \(default argument: ``None``\), ``name`` is used by default
            is_clock (:obj:`bool`): Mark this as a clock
            **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of the created port
                and accessible as dynamic attributes

        Returns:
            `Port`: The created port
        """
        if is_clock and width != 1:
            raise PRGAInternalError("Clock port must be 1-bit wide")
        # check name conflict
        if name in module._children:
            raise PRGAInternalError("Name '{}' already taken by {} in {}"
                    .format(name, module._children[name], module))
        # check key conflict
        new = Port(module, name, width, direction, key = key, is_clock = is_clock, **kwargs)
        value = module._ports.setdefault(new.key, new)
        if value is not new:
            raise PRGAInternalError("Key '{}' already taken by {} in {}"
                    .format(new.key, value, module))
        return module._children.setdefault(name, value)

    @classmethod
    def instantiate(cls, module, model, name, *, key = None, **kwargs):
        """Instantiate ``model`` and add it as a sub-module in ``parent``.

        Args:
            module (`AbstractModule`):
            model (`AbstractModule`):
            name (:obj:`str`): Name of the instance

        Keyword Args:
            key (:obj:`Hashable`): A hashable key used to index the instance in the ``instances`` mapping in the
                parent module. If not set \(default argument: ``None``\), ``name`` is used by default
            **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of the created port
                and accessible as dynamic attributes

        Returns:
            `Instance`: The created instance
        """
        if module.is_cell:
            raise PRGAInternalError("Cannot instantiate {} in {}".format(model, module))
        # check name conflict
        if name in module._children:
            raise PRGAInternalError("Name '{}' already taken by {} in {}"
                    .format(name, module._children[name], module))
        # check key conflict
        new = Instance(module, model, name, key = key, **kwargs)
        value = module._instances.setdefault(new.key, new)
        if value is not new:
            raise PRGAInternalError("Key '{}' already taken by {} in {}".format(new.key, value, module))
        return module._children.setdefault(name, value)

    # @classmethod
    # def _elaborate_clocks(cls, module, graph, instance = None, coalesce_connections = False):
    #     for net in itervalues(module.ports) if instance is None else itervalues(instance.pins):
    #         if not net.is_clock:
    #             continue
    #         node = NetUtils._reference(net, coalesced = coalesce_connections)
    #         # 1. find the predecessor(s) of this net
    #         try:
    #             predit = graph.predecessors(node)
    #             pred_node = next(predit)
    #         except (NetworkXError, StopIteration):
    #             # 2. if there's no predecessor, assign a clock group
    #             if instance is not None:
    #                 _logger.warning("Clock {} is not connected".format(net))
    #             graph.add_node(node, clock_group = node)
    #             continue
    #         # 3. make sure there is only one predecessor
    #         try:
    #             next(predit)
    #             raise PRGAInternalError("Clock {} is connected to multiple sources".format(net))
    #         except StopIteration:
    #             pass
    #         # 4. get the clock group of the predecessor
    #         try:
    #             clock_group = graph.nodes[pred_node]["clock_group"]
    #         except KeyError:
    #             pred_net = NetUtils._dereference(module, pred_node, coalesced = coalesce_connections)
    #             raise PRGAInternalError("Clock {} is connected to non-clock {}".format(net, pred_net))
    #         # 5. update clock group
    #         graph.add_node(node, clock_group = clock_group)

    @classmethod
    def _elaborate_sub_timing_graph(cls, module, graph, blackbox_instance, instance = None,
            coalesce_connections = False, elaborate_clocks = False):
        model = instance.model if instance is not None else module
        hierarchy = tuple(inst.key for inst in instance.hierarchy) if instance is not None else tuple()
        # 1. add connections in this model to the timing graph
        if coalesce_connections:
            if not model._coalesce_connections:
                raise PRGAInternalError("{} supports bit-wise connections".format(model))
            for u, v in model._conn_graph.edges:
                graph.add_edge(u + hierarchy, v + hierarchy)
        elif model._coalesce_connections:
            for u, v in model._conn_graph.edges:
                bu, bv = map(lambda node: NetUtils._dereference(model, node, coalesced = True), (u, v))
                assert len(bu) == len(bv)
                for i in range(len(bu)):
                    graph.add_edge((i, u + hierarchy), (i, v + hierarchy))
        else:
            for u, v in model._conn_graph.edges:
                graph.add_edge((u[0], u[1] + hierarchy), (v[0], v[1] + hierarchy))
        # 2. elaborate clocks
        if elaborate_clocks:
            raise NotImplementedError("Unsupported option: elaborate_clocks")
            # cls._elaborate_clocks(module, graph, instance, coalesce_connections)
        # 3. elaborate sub-instances
        for sub in itervalues(model.instances):
            if instance is not None:
                sub = sub.extend_hierarchy(above = instance)
            if blackbox_instance(sub):
                continue
            cls._elaborate_sub_timing_graph(module, graph, blackbox_instance, sub,
                    coalesce_connections, elaborate_clocks)

    @classmethod
    def reduce_timing_graph(cls, module, *,
            graph = None,
            blackbox_instance = lambda i: False,
            create_node = lambda m, n: {},
            create_edge = lambda m, path: {"path": path[1:-1]},
            coalesce_connections = False,
            ):
        """`networkx.DiGraph`_: Create a full timing graph for ``module``.

        Args:
            module (:obj:`AbstractModule`): The module to be processed

        Keyword Args:
            graph: Output graph. If not set, a new `networkx.DiGraph`_ is used
            blackbox_instance (:obj:`Function` [`AbstractInstance` ] -> :obj:`bool`): A function testing if an
                instance should be blackboxed during elaboration. If ``True`` is returned, everything inside the
                instance will be ignored. Only the pins of the instance will be kept.
            create_node (:obj:`Function` [`AbstractModule`, :obj:`Hashable` ] -> :obj:`Mapping`): A function that
                returns a node attribute mapping. Return ``None`` if the node should be discarded
            create_path (:obj:`Function` [`AbstractModule`, :obj:`Sequence` [:obj:`Hashable` ] -> :obj:`Mapping`): A
                function that returns an edge attribute mapping
            coalesce_connections (:obj:`bool`): If set, the reduced timing graph coalesce bus connections

        .. _networkx.DiGraph: https://networkx.github.io/documentation/stable/reference/classes/digraph.html
        """
        if graph is None:
            graph = DiGraph()
        tmp = type(graph)()
        # 1. phase 1: elaborate the entire timing graph
        cls._elaborate_sub_timing_graph(module, tmp, blackbox_instance, coalesce_connections = coalesce_connections)
        # 2. phase 2: reduce the timing graph
        for node in tmp:
            # 2.1 filter out leaf nodes
            if tmp.out_degree(node) > 0:
                continue
            if (attributes := create_node(module, node)) is not None:
                graph.add_node(node, **attributes)
            # 2.2 DFS
            #         head node, tail node,                            path
            stack = [(node,      None if attributes is None else node, None if attributes is None else (node, ))]
            while stack:
                head, tail, path = stack.pop()
                for prev in tmp.predecessors(head):
                    if prev in graph:                   # previous node already processed
                        if tail is None:
                            continue
                        elif (prev, tail) in graph.edges:
                            raise PRGAInternalError("Multiple paths found from {} to {}"
                                    .format(NetUtils._dereference(module, prev),
                                        NetUtils._dereference(module, tail)))
                        elif create_edge is not None:
                            graph.add_edge(prev, tail, **create_edge(module, (prev, ) + path))
                        else:
                            graph.add_edge(prev, tail)
                        continue
                    if (prev_attrs := create_node(module, prev)) is not None:
                        graph.add_node(prev, **prev_attrs)
                        if tail is not None:
                            if create_edge is not None:
                                graph.add_edge(prev, tail, **create_edge(module, (prev, ) + path))
                            else:
                                graph.add_edge(prev, tail)
                        stack.append( (prev, prev, (prev, )) )
                    elif tail is not None:
                        stack.append( (prev, tail, (prev, ) + path) )
                    else:
                        stack.append( (prev, None, None) )
        return graph
