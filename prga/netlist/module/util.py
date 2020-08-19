# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Unitility methods for accessing modules and instances."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .module import Module
from .instance import Instance
from ..net.common import AbstractNet, NetType, TimingArcType
from ..net.util import NetUtils
from ..net.bus import Port, Pin, HierarchicalPin
from ...exception import PRGAInternalError
from ...util import uno, Object

from itertools import chain, product
from networkx import NetworkXError, DiGraph

import logging
_logger = logging.getLogger(__name__)

__all__ = ['ModuleUtils']

# ----------------------------------------------------------------------------
# -- Module Utilities --------------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleUtils(Object):
    """A wrapper class for utility functions for modules and instances."""

    @classmethod
    def _iter_nets(cls, obj, blackbox_instance = lambda i: True):
        module, hierarchy = None, None
        if isinstance(obj, Module):
            module = obj
            for net in itervalues(obj.ports):
                yield net
        else:
            module, hierarchy = obj.model, obj

        for i in itervalues(module.instances):
            i = i._extend_hierarchy(above = hierarchy)
            for net in itervalues(i.pins):
                yield net
            if not (i.model.is_cell or blackbox_instance(i)):
                for net in cls._iter_nets(i, blackbox_instance):
                    yield net

    @classmethod
    def _analyze_sink(cls, net):
        bus, index = (net.bus, net.index) if net.net_type in (NetType.bit, NetType.slice_) else (net, None)
        sink, hierarchy = bus, None
        if bus.net_type in (NetType.pin, NetType.hierarchical):
            if bus.model.direction.is_output:
                sink, hierarchy = bus.model, bus.instance
            elif bus.net_type.is_hierarchical:
                sink = bus.instance.hierarchy[0].pins[bus.model.key]
                hierarchy = bus.instance._shrink_hierarchy(low = 1)
        if index is not None:
            sink = sink[index]
        return sink, hierarchy

    @classmethod
    def _attach_hierarchy(cls, net, hierarchy):
        if hierarchy is None:
            return net
        bus, index = (net.bus, net.index) if net.net_type in (NetType.bit, NetType.slice_) else (net, None)
        if bus.net_type in (NetType.pin, NetType.hierarchical):
            bus = HierarchicalPin(bus.instance._extend_hierarchy(above = hierarchy), bus.model)
        elif bus.net_type.is_port:
            bus = hierarchy.pins[bus.key]
        else:
            raise PRGAInternalError("Unsuppoted net type: {}".format(bus.net_type))
        if index is None:
            return bus
        else:
            return bus[index]

    @classmethod
    def _reference(cls, obj, *, byname = False):
        """Create a reference to ``obj``.

        Args:
            obj (`AbstractInstance` or `AbstractNet`):

        Keyword Args:
            byname (:obj:`bool`): If set, this method returns a string instead of a sequence of keys

        Returns:
            :obj:`Sequence` [:obj:`Hashable` ] or :obj:`str`:
        """
        raise NotImplementedError

    @classmethod
    def _dereference(cls, module, ref):
        """De-reference ``ref`` in ``module``.

        Args:
            module (`Module`): Top-level module
            ref (:obj:`Sequence` [:obj:`Hashable` ] or :obj:`str`):

        Returns:
            `AbstractInstance` or `AbstractNet`:
        """
        raise NotImplementedError

    @classmethod
    def create_port(cls, module, name, width, direction, *, is_clock = False, key = None, **kwargs):
        """Create a port in ``module``.

        Args:
            module (`Module`):
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Number of bits in the port
            direction (`PortDirection`): Direction of the port

        Keyword Args:
            is_clock (:obj:`bool`): Mark this port as a clock
            key (:obj:`Hashable`): A hashable key used to index the port in the ``ports`` mapping the parent module.
                If not set \(default argument: ``None``\), ``name`` is used by default
            **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of the created port
                and accessible as dynamic attributes

        Returns:
            `Port`: The created port
        """
        if is_clock and width != 1:
            raise PRGAInternalError("Clock port must be 1-bit wide")
        return module._add_child(Port(module, name, width, direction, is_clock = is_clock, key = key, **kwargs))

    @classmethod
    def instantiate(cls, module, model, name, *, key = None, **kwargs):
        """Instantiate ``model`` and add it as a sub-module in ``parent``.

        Args:
            module (`Module`):
            model (`Module`):
            name (:obj:`str`): Name of the instance

        Keyword Args:
            key (:obj:`Hashable`): A hashable key used to index the instance in the ``instances`` mapping in the
                parent module. If not set \(default argument: ``None``\), ``name`` is used by default
            **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of the created port
                and accessible as dynamic attributes

        Returns:
            `Instance`: The created instance
        """
        return module._add_child(Instance(module, model, name, key = key, **kwargs))

    @classmethod
    def reduce_conn_graph(cls, module, *,
            allow_multisource = False,
            coalesce_connections = False,
            blackbox_instance = lambda i: False,
            node_key = lambda n: NetUtils._reference(n),
            node_attrs = lambda n: {},
            edge_attrs = lambda p: {}):
        """Create a connection graph for ``module``.

        Args:
            module (`Module`):

        Keyword Args:
            allow_multisource (:obj:`bool`): If set, multi-source connections are allowed in the reduced graph.
                It's OK if some levels of hierarchy don't allow so. Incompatible with ``coalesce_connections``
            coalesce_connections (:obj:`bool`): If set, the reduced connection graph coalesce bus connections. This
                requires all levels of hierarchy do so. Incompatible with ``allow_multisource``
            blackbox_instance (:obj:`Function` [`AbstractInstance` ] -> :obj:`bool`): A function testing if an
                instance should be blackboxed during elaboration. If ``True`` is returned, everything inside the
                instance is ignored.
            node_key (:obj:`Function` [`AbstractNet` ] -> :obj:`Hashable`):
                A function that returns a hasable key to be used as the node ID in the graph. If ``None`` is returned,
                the net and all paths starting from/ending at it are not added to the graph. Paths passing through the
                net may be added depending on the endpoints of the paths. This function might be called multiple times
                upon the same net and should be deterministic
            node_attrs (:obj:`Function` [`AbstractNet` ] -> :obj:`dict`):
                A function that returns additional attributes for a [hierarchical] net. This function is called only
                once when a node with a valid key is created. ``"net"`` is a reserved key whose corresponding value is
                the corresponding net object.
            edge_attrs (:obj:`Function` [:obj:`Sequence` [`AbstractNet` ]] -> :obj:`dict`):
                A function that returns additional attributes for a path. This function is called only once when an edge
                with valid endpoints is created. ``"path"`` is a reserved key whose corresponding value is a sequence
                of nets that this path includes, from the startpoint to the endpoint, inclusively.

        Returns:
            `networkx.DiGraph`_:

        .. _networkx.DiGraph: https://networkx.github.io/documentation/stable/reference/classes/digraph.html
        """
        # 0. validate
        if allow_multisource and coalesce_connections:
            raise PRGAInternalError("'allow_multisource' and 'coalesce_connections' are incompatible")
        elif module.is_cell:
            raise PRGAInternalError("{} is a cell module".format(module))
        # 1. build graph
        g = DiGraph()
        for bus in cls._iter_nets(module, blackbox_instance):
            for net in ((bus, ) if coalesce_connections else bus):
                if (node := node_key(net)) is None or node in g:
                    continue
                # create node && add attributes
                if "net" in (attrs := node_attrs(net)):
                    raise PRGAInternalError("'net' is a reserved attribute for a node")
                g.add_node(node, net = net, **attrs)
                # DFS:    head net, endpoint, path(end to start, will be reversed when added to the graph)
                stack = [(net,      node,      (net, ))]
                while stack:
                    head_net, endpoint, path = stack.pop()
                    # 1.1 set up the environment for analyzing `head_net`
                    sink, hierarchy = cls._analyze_sink(head_net)
                    # 1.2 determine if we should keep on searching
                    if not sink.is_sink or sink.parent.is_cell:
                        # Top-level input port, or a cell output pin
                        continue
                    # 1.3 validate parent module
                    if coalesce_connections and not sink.parent.coalesce_connections:
                        raise PRGAInternalError("{} supports bit-wise connections".format(sink.parent))
                    elif not allow_multisource and sink.parent.allow_multisource:
                        raise PRGAInternalError("{} allows multi-source connections".format(sink.parent))
                    # 1.4 iterate the source(s) 
                    for src in (NetUtils.get_multisource(sink) if sink.parent.allow_multisource else
                            (NetUtils.get_source(sink), )):
                        # 1.4.1 attach hierarchy to the source
                        if src.net_type.is_const:
                            continue
                        src = cls._attach_hierarchy(src, hierarchy)
                        # 1.4.1 check if this is a valid startpoint
                        if (startpoint := node_key(src)) is not None:
                            # Yes it is. Add the node if it's not already added
                            if startpoint not in g:
                                if "net" in (attrs := node_attrs(net)):
                                    raise PRGAInternalError("'net' is a reserved attribute for a node")
                                g.add_node(startpoint, net = src, **attrs)
                            # add the edge, too
                            if g.has_edge(startpoint, endpoint):
                                raise PRGAInternalError("Bad reducing: multiple paths from {} to {}"
                                        .format(src, path[0]))
                            path = (src, ) + tuple(reversed(path))
                            if "path" in (attrs := edge_attrs(path)):
                                raise PRGAInternalError("'path' is a reserved attribute for an edge")
                            g.add_edge(startpoint, endpoint, path = path, **attrs)
                            # put it in the DFS stack
                            stack.append( (src, startpoint, (src, )) )
                        else:
                            # No it is not. Keep searching
                            stack.append( (src, endpoint, path + (src, )) )
        # 2. return
        return g

    @classmethod
    def reduce_timing_graph(cls, module, *,
            blackbox_instance = lambda i: False,
            node_key = lambda n: NetUtils._reference(n),
            node_attrs = lambda n: {},
            edge_attrs = lambda p: {}):
        """Create a timing graph for ``module``.

        Args:
            module (`Module`):

        Keyword Args:
            blackbox_instance (:obj:`Function` [`AbstractInstance` ] -> :obj:`bool`): A function testing if an
                instance should be blackboxed during elaboration. If ``True`` is returned, all connections or timing
                arcs inside the instance are ignored
            node_key (:obj:`Function` [`AbstractNet` ] -> :obj:`Hashable`):
                A function that returns a hasable key to be used as the node ID in the graph. If ``None`` is returned,
                the net and all paths starting from/ending at it are not added to the graph. Paths passing through the
                net may be added depending on the endpoints of the paths. This function might be called multiple times
                upon the same net and should be deterministic
            node_attrs (:obj:`Function` [`AbstractNet` ] -> :obj:`dict`):
                A function that returns additional attributes for a [hierarchical] net. This function is called only
                once when a node with a valid key is created. ``"net"`` is a reserved key whose corresponding value is
                the net object.
            edge_attrs (:obj:`Function` [:obj:`Sequence` [`AbstractNet` ]] -> :obj:`dict`):
                A function that returns additional attributes for a path. This function is called only once when an edge
                with valid endpoints is created. ``"path"`` is a reserved key whose corresponding value is a sequence
                of nets that this path includes, from the startpoint to the endpoint, inclusively.

        Returns:
            `networkx.DiGraph`_:

        Notes:
            The current implementation ignores sequential timing arcs

        .. _networkx.DiGraph: https://networkx.github.io/documentation/stable/reference/classes/digraph.html
        """
        # build graph
        g = DiGraph()
        for bus in cls._iter_nets(module, blackbox_instance):
            for net in bus:
                if (node := node_key(net)) is None or node in g:
                    continue
                # create node && add attributes
                if "net" in (attrs := node_attrs(net)):
                    raise PRGAInternalError("'net' is a reserved attribute for a node")
                g.add_node(node, net = net, **attrs)
                # DFS:    head net, endpoint, path(end to start, will be reversed when added to the graph)
                stack = [(net,      node,      (net, ))]
                while stack:
                    head_net, endpoint, path = stack.pop()
                    # 1.1 set up the environment for analyzing `head_net`
                    sink, hierarchy = cls._analyze_sink(head_net)
                    if hierarchy is not None and blackbox_instance(hierarchy):
                        continue
                    # 1.2 get timing arc(s)
                    srcs = []
                    sinkbus, sinkidx = ((sink.bus, sink.index) if sink.net_type.is_bit or sink.net_type.is_slice
                            else (sink, None))
                    if sinkbus.parent.coalesce_connections:
                        for arc in NetUtils.get_timing_arcs(sink = sinkbus,
                                types = (TimingArcType.comb_bitwise, TimingArcType.comb_matrix)):
                            if arc.type_.is_comb_bitwise:
                                srcs.append(arc.source if sinkidx is None else arc.source[sinkidx])
                            else:
                                srcs.extend(arc.source)
                    else:
                        for arc in NetUtils.get_timing_arcs(sink = sink):
                            srcs.append(arc.source)
                    # 1.3 iterate the source(s)
                    for src in srcs:
                        # 1.3.1 attach hierarchy to the source
                        src = cls._attach_hierarchy(src, hierarchy)
                        # 1.3.2 check if this is a valid startpoint
                        if (startpoint := node_key(src)) is not None:
                            # Yes it is. Add the node if it's not already added
                            if startpoint not in g:
                                if "net" in (attrs := node_attrs(net)):
                                    raise PRGAInternalError("'net' is a reserved attribute for a node")
                                g.add_node(startpoint, net = src, **attrs)
                            # add the edge, too
                            if g.has_edge(startpoint, endpoint):
                                raise PRGAInternalError("Bad reducing: multiple paths from {} to {}"
                                        .format(src, path[0]))
                            path = (src, ) + tuple(reversed(path))
                            if "path" in (attrs := edge_attrs(path)):
                                raise PRGAInternalError("'path' is a reserved attribute for an edge")
                            g.add_edge(startpoint, endpoint, path = path, **attrs)
                            # put it in the DFS stack
                            stack.append( (src, startpoint, (src, )) )
                        else:
                            # No it is not. Keep searching
                            stack.append( (src, endpoint, path + (src, )) )
        # 2. return
        return g
