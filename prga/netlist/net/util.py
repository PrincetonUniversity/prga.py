# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Utility methods for accessing nets."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import BusType, NetType, AbstractGenericBus, AbstractGenericNet, Const, Slice, Concat
from ...util import Object, uno
from ...exception import PRGAInternalError, PRGATypeError, PRGAIndexError

from networkx.exception import NetworkXError
from itertools import product

import logging
_logger = logging.getLogger(__name__)

__all__ = ['NetUtils']

# ----------------------------------------------------------------------------
# -- Net Utilities -----------------------------------------------------------
# ----------------------------------------------------------------------------
class NetUtils(object):
    """A wrapper class for utility functions for nets."""

    @classmethod
    def _slice(cls, bus, index):
        """`Slice` or `AbstractGenericNet`: Create a slice of ``bus``.

        ``index`` won't be validated, so use with care.
        """
        if isinstance(index, int):
            index = slice(index, index + 1)
        if index.stop <= index.start:
            return Const()
        elif index.stop - index.start == len(bus):
            return bus
        else:
            return Slice(bus, index)

    @classmethod
    def _reference(cls, net, *, coalesced = False):
        """Get the node corresponding to ``net`` in its parent module's connection graph.

        Args:
            net (`AbstractGenericNet`):

        Keyword Args:
            coalesced (:obj:`bool`): If not set (by default), ``net`` must be one-bit wide, and this method returns a
                reference to the bit. If set, ``net`` must be a `BusType.nonref` bus, and this method returns a
                reference to the bus.
        """
        if coalesced:
            if not net.bus_type.is_nonref:
                raise PRGAInternalError("Cannot create coalesced reference for {}".format(net))
            else:
                return net.node
        elif len(net) != 1:
            raise PRGAInternalError("Cannot create reference for {}: width > 1".format(net))
        else:
            return (0, net.node) if net.bus_type.is_nonref else net.node

    @classmethod
    def _dereference(cls, module, node, *, coalesced = False):
        """Dereference ``node`` in ``modules``'s connection graph.

        Args:
            module (`AbstractModule`):
            node (:obj:`tuple` [:obj:`int`, :obj:`tuple` [:obj:`Hashable`, ... ]]):

        Keyword Args:
            coalesced (:obj:`bool`): Set if ``node`` is a reference to a bus

        Return:
            net (`Port`, `Pin`, `Slice` or `Const`): 
        """
        # no matter if `coalesced` is set, check if the node refers to a constant net
        if node[0] is NetType.const:
            return Const(*node[1:])
        index, node = (None, node) if coalesced else node
        net_key, hierarchy = node[0], node[1:]
        instance = None
        for inst_key in reversed(hierarchy):
            if instance is None:
                instance = module.instances[inst_key]
            else:
                instance = instance.extend_hierarchy(below = instance.model.instances[inst_key])
        bus = instance.pins[net_key] if instance else module.ports[net_key]
        if index is not None:
            return bus[index]
        else:
            return bus

    @classmethod
    def _navigate_backwards(cls, module, endpoint, *,
            path = tuple(),
            yield_ = lambda module, node: True,
            stop = lambda module, node: False,
            skip = lambda module, node: False):
        """Navigate the connection graph backwards, yielding startpoints and paths from the startpoints to the
        endpoints.
        
        Args:
            module (`AbstractModule`): Top-level module to perform navigation
            endpoint (:obj:`Hashable`): Endpoint for the navigation

        Keyword Arguments:
            path (:obj:`Sequence` [:obj:`Hashable` ]): An additional path appended to any path reported by this
                method. This is mainly used in recusive calls to this method
            yield_ (:obj:`Function` [`AbstractModule`, :obj:`Hashable` ] -> :obj:`bool`): Test if
                a path should be yielded when reaching this node
            stop (:obj:`Function` [`AbstractModule`, :obj:`Hashable` ] -> :obj:`bool`): Test if
                the navigation should stop at the specified node (i.e. force treating it as a startpoint)
            skip (:obj:`Function` [`AbstractModule`, :obj:`Hashable` ] -> :obj:`bool`): Test if
                a node should be ignored when reporting the path

        Yields:
            path (:obj:`Sequence` [:obj:`Hashable` ]): a path to the endpoint
        """
        # 1. disassemble the node
        idx, net_key = endpoint
        # 2. check elaboration status and determine in which module to do the navigation
        model, hierarchy_key = module, tuple()
        while len(net_key) >= 3 and net_key[2:] not in model._elaborated:
            done = False
            for split in range(3, len(net_key) - 1):
                cur_up, cur_down = net_key[split:], net_key[:split]
                if cur_up in model._elaborated:
                    model = model.hierarchy[cur_up].model
                    hierarchy_key, net_key = cur_up + hierarchy_key, cur_down
                    done = True
                    break
            if not done:
                model = model.instances[net_key[-1]].model
                hierarchy_key, net_key = net_key[-1:] + hierarchy_key, net_key[:-1]
        # 3. move forward
        while True:
            while True:
                try:
                    nodes = tuple(model._conn_graph.predecessors( 
                        net_key if model._coalesce_connections else (idx, net_key) ))
                except NetworkXError:
                    break
                if not nodes:
                    break
                for node in nodes:
                    cur = ((idx, node + hierarchy_key) if model._coalesce_connections else 
                            (node[0], node[1] + hierarchy_key))
                    next_path = path if skip( module, cur ) else ((cur, ) + path)
                    if yield_( module, cur ):
                        yield next_path
                    if stop( module, cur ) or 'clock' in model._conn_graph.nodes[node]:
                        continue
                    for p in cls._navigate_backwards(module, cur,
                            path = next_path, yield_ = yield_, stop = stop, skip = skip):
                        yield p
                return
            # 4. one more chance if this net is an output pin of a leaf instance (in terms of elaboration)
            if len(net_key) == 1 or net_key[1:] in model._elaborated:
                return
            model, hierarchy_key = model.hierarchy[net_key[1:]].model, net_key[1:] + hierarchy_key
            net_key = net_key[:1]

    @classmethod
    def concat(cls, items, *, skip_flatten = False):
        """`Slice`, `Concat` or other nets: Concatenate the provided iterable of nets. Set ``skip_flatten`` if
        ``items`` does not contain a `Concat` object."""
        # flatten the iterable
        flatten = None
        if skip_flatten:
            flatten = items
        else:
            flatten = []
            for i in items:
                if i.bus_type.is_concat:
                    for ii in i.items:
                        flatten.append(ii)
                else:
                    flatten.append(i)
        # concatenating
        concat = []
        for i in flatten:
            if len(i) == 0:
                continue
            elif len(concat) == 0 or i.net_type is not concat[-1].net_type:
                concat.append( i )
            elif i.net_type.is_const:
                if i.value is None and concat[-1].value is None:
                    concat[-1] = Const(width = len(concat[-1]) + len(i))
                elif i.value is not None and concat[-1].value is not None:
                    concat[-1] = Const((i.value << len(concat[-1])) + concat[-1].value, len(concat[-1]) + len(i))
                else:
                    concat.append( i )
            elif i.bus == concat[-1].bus and i.index.start == concat[-1].index.stop:
                concat[-1] = cls._slice(i.bus, slice(concat[-1].index.start, i.index.stop))
            else:
                concat.append( i )
        # emitting final result
        if len(concat) == 0:
            return Const()
        elif len(concat) == 1:
            return concat[0]
        else:
            return Concat(tuple(iter(concat)))

    @classmethod
    def connect(cls, sources, sinks, *, fully = False, **kwargs):
        """Connect ``sources`` and ``sinks``.

        Args:
            sources: a bus, a slice of a bus, a bit of a bus, or an iterable of the items listed above
            sink: a bus, a slice of a bus, a bit of a bus, or an iterable of the items listed above

        Keyword Args:
            fully (:obj:`bool`): If set, every bit in ``sources`` is connected to all bits in ``sinks``.
            **kwargs: Custom attibutes assigned all connections
        """
        # 1. concat the sources & sinks
        sources, sinks = map(cls.concat, (sources, sinks))
        # 2. get the parent module
        module = sinks.items[0].parent if sinks.bus_type.is_concat else sinks.parent
        # 3. if module does not support bitwise connection, recreate the source list and sink list
        if module._coalesce_connections:
            if fully:
                raise PRGAInternalError("'{}' does not support bitwise connections (invalid 'fully' flag)"
                        .format(module))
            source_list, sink_list = [], []
            for concat, list_ in ( (sources, source_list), (sinks, sink_list) ):
                if concat.bus_type.is_slice:
                    raise PRGAInternalError("'{}' does not support bitwise connections ('{}' is a slice)"
                            .format(module, concat))
                elif concat.bus_type.is_nonref:
                    list_.append( concat )
                else:
                    for i in concat.items:
                        if i.bus_type.is_slice:
                            raise PRGAInternalError("'{}' does not support bitwise connections ('{}' is a slice)"
                                    .format(module, i))
                        else:
                            list_.append( i )
            sources, sinks = source_list, sink_list
        # 4. connect!
        if not fully and len(sources) != len(sinks):
            _logger.warning("Width mismatch: len({}) = {} != len({}) = {}"
                    .format(sources, len(sources), sinks, len(sinks)))
        pairs = product(sources, sinks) if fully else zip(sources, sinks)
        for src, sink in pairs:
            if not src.is_source:
                raise PRGAInternalError("'{}' is not a valid source".format(src))
            elif not src.net_type.is_const and src.parent is not module:
                raise PRGAInternalError("Cannot connect {}: different parent module".format(src))
            elif not sink.is_sink and not (module.is_cell and src.is_clock and not sink.is_clock):
                raise PRGAInternalError("'{}' is not a valid sink".format(sink))
            elif sink.parent is not module:
                raise PRGAInternalError("Cannot connect {}: different parent module".format(sink))
            elif sink.is_clock and not src.is_clock:
                raise PRGAInternalError("{} is a clock but {} is not".format(sink, src))
            elif src.net_type.is_const and src.value is None:
                continue
            src_node, sink_node = map(lambda x: cls._reference(x, coalesced = module._coalesce_connections),
                    (src, sink))
            if not (module._allow_multisource or
                    sink_node not in module._conn_graph or 
                    module._conn_graph.in_degree( sink_node ) == 0 or
                    next(iter(module._conn_graph.predecessors( sink_node ))) == src_node):
                raise PRGAInternalError(
                        "'{}' does not support multi-source connections. ('{}' is already connected to '{}')"
                        .format(module, sink, cls.get_source(sink)))
            module._conn_graph.add_edge( src_node, sink_node, **kwargs )

    @classmethod
    def get_source(cls, sink, *, return_none_if_unconnected = False):
        """Get the source connected to ``sink``. This method is for accessing connections in modules that do not allow
        multi-source connections only."""
        ret = None
        if not sink.is_sink:
            raise PRGAInternalError("{} is not a valid sink".format(sink))
        elif sink.parent._allow_multisource:
            raise PRGAInternalError(
                    "Module {} allows multi-source connections. Use `NetUtils.get_multisource` instead"
                    .format(sink.parent))
        elif sink.parent._coalesce_connections:
            try:
                node = next(sink.parent._conn_graph.predecessors( cls._reference(sink.bus, coalesced = True) ))
                ret = cls._dereference(sink.parent, node, coalesced = True)[sink.index]
            except (StopIteration, NetworkXError):
                ret = Const( width = len(sink) )
        else:
            sources = []
            for bit in sink:
                try:
                    node = next(sink.parent._conn_graph.predecessors( cls._reference(bit) ))
                    sources.append( cls._dereference(sink.parent, node) )
                except (StopIteration, NetworkXError):
                    sources.append( Const(width = 1) )
            ret = cls.concat(sources)
        if return_none_if_unconnected and ret.bus_type.is_nonref and ret.net_type.is_const and ret.value is None:
            return None
        else:
            return ret

    @classmethod
    def get_multisource(cls, sink):
        """Get the sources connected to ``sink``. This method is for accessing connections in modules that allow
        multi-source connections."""
        if not sink.is_sink:
            raise PRGAInternalError("{} is not a sink".format(sink))
        elif len(sink) != 1:
            raise PRGAInternalError("{} is not 1-bit wide".format(sink))
        elif not sink.parent._allow_multisource:
            raise PRGAInternalError("'{}' does not allow multi-source connections".format(sink.parent))
        try:
            return cls.concat( iter(cls._dereference(sink.parent, node) for node in
                    sink.parent._conn_graph.predecessors( cls._reference(sink) )) )
        except NetworkXError:
            return Const()
    @classmethod

    def get_connection(cls, source, sink):
        """Get an edittable :obj:`dict` for key-value attributes associated with the edge from ``source`` to
        ``sink``."""
        if source.parent is not sink.parent:
            raise PRGAInternalError("Source net '{}' and sink net '{}' are not in the same module"
                    .format(source, sink))
        elif source.parent._coalesce_connections:
            if not source.bus_type.is_nonref:
                raise PRGAInternalError("'{}' does not support bitwise connection (source net '{}' is not a nonref bus)"
                        .format(source.parent, source))
            elif not sink.bus_type.is_nonref:
                raise PRGAInternalError("'{}' does not support bitwise connection (sink net '{}' is not a nonref bus)"
                        .format(source.parent, sink))
        elif len(source) != 1:
            raise PRGAInternalError("source net: len({}) != 1".format(source))
        elif len(sink) != 1:
            raise PRGAInternalError("sink net: len({}) != 1".format(sink))
        try:
            return source.parent._conn_graph.edges[
                    cls._reference(source, coalesced = source.parent._coalesce_connections),
                    cls._reference(sink, coalesced = source.parent._coalesce_connections)]
        except KeyError:
            return None
