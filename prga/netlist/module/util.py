# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .module import Module
from .instance import Instance
from ..net.common import PortDirection
from ..net.util import NetUtils
from ..net.bus import Port, Pin
from ...exception import PRGAInternalError
from ...util import uno

from collections import OrderedDict
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
            key (:obj:`Hashable`): A hashable key used to index the port in the parent module. If not given
                \(default argument: ``None``\), ``name`` is used by default
            is_clock (:obj:`bool`): Mark this as a clock
            **kwargs: Arbitrary attributes assigned to the created port
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
        """Instantiate ``model`` in ``parent``.

        Args:
            module (`AbstractModule`):
            model (`AbstractModule`):
            name (:obj:`str`): Name of the instance

        Keyword Args:
            key (:obj:`Hashable`): A hashable key used to index the instance in the parent module. If not given
                \(default argument: ``None``\), ``name`` is used by default
            **kwargs: Arbitrary attributes assigned to the instantiated instance
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

    @classmethod
    def _elaborate_clocks(cls, module, graph, instance = None):
        for net in itervalues(module.ports) if instance is None else itervalues(instance.pins):
            if not net.is_clock:
                continue
            node = NetUtils._reference(net)
            # 1. find the predecessor(s) of this net
            try:
                predit = graph.predecessors(node)
                pred_node = next(predit)
            except (NetworkXError, StopIteration):
                # 2. if there's no predecessor, assign a clock group
                if instance is not None:
                    _logger.warning("Clock {} is not connected".format(net))
                graph.add_node(node, clock_group = node)
                continue
            # 3. make sure there is only one predecessor
            try:
                next(predit)
                raise PRGAInternalError("Clock {} is connected to multiple sources".format(net))
            except StopIteration:
                pass
            # 4. get the clock group of the predecessor
            try:
                clock_group = graph.nodes[pred_node]["clock_group"]
            except KeyError:
                pred_net = NetUtils._dereference(module, pred_node)
                raise PRGAInternalError("Clock {} is connected to non-clock {}".format(net, pred_net))
            # 5. update clock group
            graph.add_node(node, clock_group = clock_group)

    @classmethod
    def _elaborate_sub_timing_graph(cls, module, graph, blackbox_instance, instance = None):
        model = instance.model if instance is not None else module
        hierarchy = tuple(inst.key for inst in instance.hierarchy) if instance is not None else tuple()
        # 1. add connections in this model to the timing graph
        if model._coalesce_connections:
            for u, v in model._conn_graph.edges:
                bu, bv = map(lambda node: NetUtils._dereference(model, node, coalesced = True), (u, v))
                assert len(bu) == len(bv)
                for i in range(len(bu)):
                    graph.add_edge((i, u + hierarchy), (i, v + hierarchy))
        else:
            for u, v in model._conn_graph.edges:
                graph.add_edge((u[0], u[1] + hierarchy), (v[0], v[1] + hierarchy))
        # 2. elaborate clocks
        cls._elaborate_clocks(module, graph, instance)
        # 3. elaborate sub-instances
        for sub in itervalues(model.instances):
            if instance is not None:
                sub = sub.extend_hierarchy(above = instance)
            if blackbox_instance(sub):
                continue
            cls._elaborate_sub_timing_graph(module, graph, blackbox_instance, sub)

    @classmethod
    def reduce_timing_graph(cls, module, *,
            initial_graph = None,
            blackbox_instance = lambda i: False,
            create_node = lambda m, n: {},
            create_edge = lambda m, path: {"path": path[1:-1]},
            ):
        """`networkx.DiGraph`_: Create a timing graph for ``module``.

        Args:
            module (:obj:`AbstractModule`): The module to be processed

        Keyword Args:
            initial_graph (`networkx.DiGraph`_):
            blackbox_instance (:obj:`Function` [`AbstractInstance` ] -> :obj:`bool`): A function testing if an
                instance should be blackboxed during elaboration. If ``True`` is returned, everything inside the
                instance will be ignored. Only the pins of the instance will be kept.
            create_node (:obj:`Function` [`AbstractModule`, :obj:`Hashable` ] -> :obj:`Mapping`): A function that
                returns a node attribute mapping. Return ``None`` if the node should be discarded (will be kept in the
                path if ``drop_path`` is not set
            create_path (:obj:`Function` [`AbstractModule`, :obj:`Sequence` [:obj:`Hashable` ] -> :obj:`Mapping`): A
                function that returns an edge attribute mapping

        .. _networkx.DiGraph: https://networkx.github.io/documentation/stable/reference/classes/digraph.html#networkx.DiGraph
        """
        graph = uno(initial_graph, DiGraph())
        # 1. phase 1: elaborate the entire timing graph
        cls._elaborate_sub_timing_graph(module, graph, blackbox_instance)
        # 2. phase 2: reduce the timing graph
        # 2.1 filter out leaf nodes
        leaf_nodes = tuple(node for node in graph if graph.out_degree(node) == 0)
        discard_nodes = set()
        for node in leaf_nodes:
            attributes = create_node(module, node)
            if attributes is None:
                discard_nodes.add(node)
            else:
                graph.add_node(node, kept = True, **attributes)
            # 2.2 DFS
            stack = [(node,         None if attributes is None else node, None if attributes is None else (node, ))]
            while stack:
                head, tail, path = stack.pop()
                predecessors = tuple(graph.predecessors(head))
                for prev in predecessors:
                    if graph.nodes[prev].get("kept"):   # previous node already processed
                        if tail is None:
                            continue
                        elif graph.edges.get((prev, tail), {}).get("kept"):
                            raise PRGAInternalError("Multiple paths found from {} to {}"
                                    .format(NetUtils._dereference(module, prev),
                                        NetUtils._dereference(module, tail)))
                        else:
                            graph.add_edge(prev, tail, kept = True, **create_edge(module, (prev, ) + path))
                        continue
                    prev_attrs = create_node(module, prev)
                    if prev_attrs is not None:
                        graph.add_node(prev, kept = True, **prev_attrs)
                        if tail is not None:
                            graph.add_edge(prev, tail, kept = True, **create_edge(module, (prev, ) + path))
                        stack.append( (prev, prev, (prev, )) )
                    else:
                        discard_nodes.add(prev)
                        if tail is not None:
                            stack.append( (prev, tail, (prev, ) + path) )
                        else:
                            stack.append( (prev, None, None) )
        # 2.3 remove unwanted nodes
        graph.remove_nodes_from(discard_nodes)
        return graph
