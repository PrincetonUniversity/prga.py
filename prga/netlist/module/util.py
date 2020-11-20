# -*- encoding: ascii -*-
"""Unitility methods for accessing modules and instances."""

from .module import Module
from .instance import Instance
from ..net.common import AbstractNet, NetType, TimingArcType
from ..net.util import NetUtils
from ..net.bus import Port, Pin, HierarchicalPin
from ...exception import PRGAInternalError
from ...util import uno, Object, Enum

from itertools import chain, product
from networkx import NetworkXError, DiGraph, MultiDiGraph

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
            for net in obj.ports.values():
                yield net
        else:
            module, hierarchy = obj.model, obj

        for i in module.instances.values():
            i = i._extend_hierarchy(above = hierarchy)
            for net in i.pins.values():
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
        return sink, index, hierarchy

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
    def _dereference(cls, module, ref, *, byname = False):
        """De-reference ``ref`` in ``module``.

        Args:
            module (`Module`): Top-level module
            ref (:obj:`Sequence` [:obj:`Hashable` ] or :obj:`str`):

        Keyword Args:
            byname (:obj:`bool`): If set, ``ref`` is treated as a hierarchical name

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
    def __add_node_to_graph(cls, g, node, net, node_attrs, **reserved):
        attrs = node_attrs(net)
        reserved.update(net = net)
        for k in reserved.keys():
            if k in attrs:
                raise PRGAInternalError("'{}' is a reserved attribute for a node".format(k))
        g.add_node(node, **reserved, **attrs)

    @classmethod
    def __add_edge_to_graph(cls, g, u, v, path, edge_attrs, *key, prefix = "", **reserved):
        if g.has_edge(u, v, *key):
            raise PRGAInternalError("Bad reducing: multiple {}paths from {} to {}"
                    .format(prefix, path[0], path[-1]))
        reserved.update(path = path)
        if (attrs := edge_attrs(path)) is not None:
            for k in reserved.keys():
                if k in attrs:
                    raise PRGAInternalError("'{}' is a reserved attribute for an edge".format(k))
            g.add_edge(u, v, *key, **reserved, **attrs)

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
                once when a node with a valid key is created. ``"net"`` is a reserved key whose value is the
                corresponding net object.
            edge_attrs (:obj:`Function` [:obj:`Sequence` [`AbstractNet` ]] -> :obj:`dict`):
                A function that returns additional attributes for a path. This function is called only once when an edge
                with valid endpoints is created. ``"path"`` is a reserved key whose corresponding value is a sequence
                of nets that this path includes, from the startpoint to the endpoint, inclusively. If ``None`` is
                returned, the edge is not added to the graph

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
                cls.__add_node_to_graph(g, node, net, node_attrs)
                # DFS:    head net, endpoint, path(start to end)
                stack = [(net,      node,      (net, ))]
                while stack:
                    head_net, endpoint, path = stack.pop()
                    # 1.1 set up the environment for analyzing `head_net`
                    sink, index, hierarchy = cls._analyze_sink(head_net)
                    if index is not None:
                        sink = sink[index]
                    # 1.2 determine if we should keep on searching
                    if not sink.is_sink or sink.parent.is_cell or (hierarchy is not None and
                            blackbox_instance(hierarchy)):
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
                        if src is None:
                            continue
                        # 1.4.1 attach hierarchy to the source
                        src = cls._attach_hierarchy(src, hierarchy)
                        # 1.4.1 check if this is a valid startpoint
                        if (startpoint := node_key(src)) is not None:
                            # Yes it is
                            if startpoint not in g:
                                # put it in the DFS stack
                                stack.append( (src, startpoint, (src, )) )
                                # Add the node
                                cls.__add_node_to_graph(g, startpoint, src, node_attrs)
                            # add the edge, too
                            cls.__add_edge_to_graph(g, startpoint, endpoint, (src, ) + path, edge_attrs)
                        else:
                            # No it is not. Keep searching
                            stack.append( (src, endpoint, (src, ) + path) )
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
                arcs inside the instance are ignored. Consequentially, all timing paths passing through the instance
                are ignored as well.
            node_key (:obj:`Function` [`AbstractNet` ] -> :obj:`Hashable`):
                A function that returns a hasable key to be used as the node ID in the graph. If ``None`` is returned,
                the net and all paths starting from/ending at it are not added to the graph. Paths passing through the
                net may be added depending on the endpoints of the paths. This function might be called multiple times
                upon the same net and should be deterministic
            node_attrs (:obj:`Function` [`AbstractNet` ] -> :obj:`dict`):
                A function that returns additional attributes for a [hierarchical] net. This function is called only
                once when a node with a valid key is created. ``"net"`` is a reserved key whose value is the
                corresponding net object; ``"clock_root"`` is a reserved key whose value is the node of the root net of
                the clock network that this net belongs to, or ``None`` if this net is not a clock. 
            edge_attrs (:obj:`Function` [`TimingArcType`, :obj:`Sequence` [`AbstractNet` ]] -> :obj:`dict`):
                A function that returns additional attributes for a path. This function is called only once when an edge
                with valid endpoints is created. ``"path"`` is a reserved key whose corresponding value is a sequence
                of nets that this path includes, from the startpoint to the endpoint, inclusively; ``"type_"`` is a
                reserved key indicating the type of this timing arc.  If ``None`` is returned, the edge is not added
                to the graph

        Returns:
            `networkx.MultiDiGraph`_:

        Notes:
            Clock networks are handled relatively naively in this method. Clock networks are detected using the
            ``is_clock`` attribute on nets and collected following connections. For each network, a clock "root" is
            identified (currently the root must be a clock input of ``module``), and combinational timing arcs are
            created in the clock network. Reference clocks for all sequential timing arcs are updated to be the "root"
            clock.

        .. _networkx.MultiDiGraph: https://networkx.org/documentation/stable/reference/classes/multigraph.html
        """
        # build graph
        g = MultiDiGraph()
        for bus in cls._iter_nets(module, blackbox_instance):
            for net in bus:
                if (node := node_key(net)) is None or node in g:
                    continue
                # create node && add attributes. cannot determine clock root yet
                cls.__add_node_to_graph(g, node, net, node_attrs, clock_root = None)
                # DFS:    type,                    head net, endpoint, path(start to end), clock network nodes
                stack = [(TimingArcType.comb_bitwise, net,   node,     (net, ), (node, ) if net.is_clock else tuple())]
                while stack:
                    type_, head_net, endpoint, path, clk_nodes = stack.pop()
                    # define a helper function here for correct closure
                    def process_valid_startpoint(src, startpoint):
                        if startpoint not in g:
                            # put new head net into DFS stack
                            stack.append( (type_, src, startpoint, (src, ),
                                (clk_nodes + (startpoint, )) if src.is_clock else clk_nodes) )
                            # add the node
                            cls.__add_node_to_graph(g, startpoint, src, node_attrs, clock_root = None)
                    # 1.1 set up the environment for analyzing `head_net`
                    sinkbus, sinkidx, hierarchy = cls._analyze_sink(head_net)
                    sink = sinkbus if sinkidx is None else sinkbus[sinkidx]
                    # 1.2 determine if we should keep on searching
                    if not sinkbus.is_sink:     # top-level input port
                        assert sinkbus.net_type.is_port and hierarchy is None
                        # update clock network, or create edge
                        if clk_nodes or type_.is_seq_start or type_.is_seq_end:
                            if not sink.is_clock:
                                raise PRGAInternalError("Clock network driven by non-clock port {}"
                                        .format(sink))
                            elif (clock_root := node_key(sink)) is None:
                                raise PRGAInternalError("Clock root ({}) ignored due to user-specified node_key"
                                        .format(sink))
                            for clk_node in clk_nodes:
                                if (conflict := (d := g.nodes[clk_node])["clock_root"]) is not None:
                                    if conflict != clock_root:
                                        raise PRGAInternalError("Clock network driven by multiple sources: {}, {}"
                                                .format(g[conflict]["net"], sink))
                                    break
                                d["clock_root"] = clock_root
                            if type_.is_seq_start or type_.is_seq_end:
                                cls.__add_edge_to_graph(g, clock_root, endpoint, path, edge_attrs, type_,
                                        type_ = type_)
                        # stop searching
                        continue
                    elif hierarchy is not None and blackbox_instance(hierarchy):
                        # black-boxed instance
                        continue
                    # 1.3 DFS traversal
                    # 1.3.1 check combinational timing arcs if ``sinkbus`` is a cell output
                    if sinkbus.net_type.is_port and sinkbus.parent.is_cell:
                        for arc in NetUtils.get_timing_arcs(sink = sinkbus,
                                types = (TimingArcType.comb_bitwise, TimingArcType.comb_matrix)):
                            for src in (arc.source if arc.type_.is_comb_matrix or sinkidx is None else
                                    arc.source[sinkidx]):
                                # attach hierarchy
                                src = cls._attach_hierarchy(src, hierarchy)
                                # check if ``src`` is a valid startpoint
                                if (startpoint := node_key(src)) is not None:
                                    # Yes it is
                                    process_valid_startpoint(src, startpoint)
                                    # add the edge if ``type_`` is combinational
                                    if type_.is_comb_bitwise:
                                        cls.__add_edge_to_graph(g, startpoint, endpoint, (src, ) + path,
                                                edge_attrs, type_, type_ = type_)
                                else:
                                    # No it is not. Keep traversing
                                    stack.append( (type_, src, endpoint, (src, ) + path, clk_nodes) )
                    # 1.3.2 check connections if ``sinkbus`` is not a cell output
                    else:
                        for src in (NetUtils.get_multisource(sink) if sink.parent.allow_multisource else
                                (NetUtils.get_source(sink), )):
                            if src is None:
                                continue
                            # attach hierarchy
                            src = cls._attach_hierarchy(src, hierarchy)
                            # check if ``src`` is a valid startpoint
                            if (startpoint := node_key(src)) is not None:
                                # Yes it is
                                process_valid_startpoint(src, startpoint)
                                # add the edge if ``type_`` is combinational
                                if type_.is_comb_bitwise:
                                    cls.__add_edge_to_graph(g, startpoint, endpoint, (src, ) + path,
                                            edge_attrs, type_, type_ = type_)
                            else:
                                # No it is not. Keep traversing
                                stack.append( (type_, src, endpoint, (src, ) + path, clk_nodes) )
                    # 1.3.3 check sequential timing arcs if ``sinkbus`` is a cell input/output and ``type_`` is not
                    # sequential
                    if type_.is_comb_bitwise:
                        if sinkbus.net_type.is_pin:
                            # convert from input pin to input port
                            hierarchy = sinkbus.instance._extend_hierarchy(above = hierarchy)
                            sinkbus = sinkbus.model
                        if not sinkbus.parent.is_cell:
                            continue
                        for arc in NetUtils.get_timing_arcs(sink = sinkbus,
                                types = (TimingArcType.seq_start, TimingArcType.seq_end)):
                            assert arc.source.is_clock
                            # attach hierarchy
                            src = cls._attach_hierarchy(arc.source, hierarchy)
                            # check if ``src`` is a valid startpoint
                            if (startpoint := node_key(src)) is not None:
                                # Yes it is
                                process_valid_startpoint(src, startpoint)
                                # regardless of the validity, keep traversing as a different type of arc
                                stack.append( (arc.type_, src, endpoint, (src, ) + path, clk_node + (startpoint, )) )
                            else:
                                # No it is not. Keep traversing as a different type of arc
                                stack.append( (arc.type_, src, endpoint, (src, ) + path, clk_node) )
        # 2. return
        return g
