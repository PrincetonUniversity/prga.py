# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import BusType, NetType, AbstractGenericBus, AbstractGenericNet
from .const import Unconnected, Const
from ...util import Object, uno, compose_slice
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

        ``index`` will not be validated.
        """
        if isinstance(index, int):
            if len(bus) == 1:
                return bus
            else:
                return Slice(bus, index)
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
            coalesced (:obj:`bool`): Set if ``net`` is a nonref-bus
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
        bus = module.hierarchy[hierarchy].pins[net_key] if hierarchy else module.ports[net_key]
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
            path (:obj:`Sequence` [:obj:`Hashable` ]): Path to be appended to any path reported by this method
            yield_ (:obj:`Function` [`AbstractModule`, :obj:`Hashable` ] -> :obj:`bool`): Lambda function testing if
                a node should be emitted during navigation
            stop (:obj:`Function` [`AbstractModule`, :obj:`Hashable` ] -> :obj:`bool`): Lambda function testing if
                the navigation should stop at the specified node (i.e. force treating it as a startpoint)
            skip (:obj:`Function` [`AbstractModule`, :obj:`Hashable` ] -> :obj:`bool`): Lambda function testing if
                a node should be ignored when reporting the path

        Yields:
            path (:obj:`Sequence` [:obj:`Hashable` ]): a path to endpoint
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
            if len(concat) == 0 or i.bus_type is not concat[-1].bus_type:
                concat.append( i )
            elif i.bus_type.is_slice:
                if i.bus != concat[-1].bus:
                    concat.append( i )
                elif isinstance(i.index, int):
                    if isinstance(concat[-1].index, int) and i.index == concat[-1].index + 1:
                        concat[-1] = cls._slice(i.bus, slice(concat[-1].index, i.index + 1))
                    elif isinstance(concat[-1].index, slice) and i.index == concat[-1].index.stop:
                        concat[-1] = cls._slice(i.bus, slice(concat[-1].index.start, i.index + 1))
                    else:
                        concat.append( i )
                else:
                    if isinstance(concat[-1].index, int) and i.index.start == concat[-1].index + 1:
                        concat[-1] = cls._slice(i.bus, slice(concat[-1].index, i.index.stop))
                    elif isinstance(concat[-1].index, slice) and i.index.start == concat[-1].index.stop:
                        concat[-1] = cls._slice(i.bus, slice(concat[-1].index.start, i.index.stop))
                    else:
                        concat.append( i )
            else:   # nonref
                if i.net_type.is_unconnected and concat[-1].net_type.is_unconnected:
                    concat[-1] = Unconnected(len(i) + len(concat[-1]))
                elif i.net_type.is_const and concat[-1].net_type.is_const:
                    concat[-1] = Const((i.value << len(concat[-1])) + concat[-1].value, len(concat[-1]) + len(i))
                else:
                    concat.append( i )
        # emitting final result
        if len(concat) == 0:
            return Unconnected(0)
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
            **kwargs: Custom attibutes assigned to the connections
        """
        # 1. concat the sources & sinks
        sources, sinks = map(cls.concat, (sources, sinks))
        # 2. get the parent module
        module = sources.items[0].parent if sources.bus_type.is_concat else sources.parent
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
            elif not sink.is_sink:
                raise PRGAInternalError("'{}' is not a valid sink".format(sink))
            elif src.net_type.is_unconnected:
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
    def get_source(cls, sink):
        """Get the source connected to ``sink``. This method is for accessing connections in modules that do not allow
        multi-source connections only."""
        if not sink.is_sink:
            raise PRGAInternalError("{} is not a valid sink".format(sink))
        if sink.parent._allow_multisource:
            raise PRGAInternalError(
                    "Module {} allows multi-source connections. Use `NetUtils.get_multisource` instead"
                    .format(sink.parent))
        if sink.parent._coalesce_connections:
            sinks = sink.items if sink.bus_type.is_concat else (sink, )
            sources = []
            for sink_ in sinks:
                bus, index = (sink_.bus, sink.index) if sink_.bus_type.is_slice else (sink_, None)

                try:
                    node = next(sink.parent._conn_graph.predecessors( cls._reference(bus, coalesced = True) ))
                except (StopIteration, NetworkXError):
                    sources.append( Unconnected( len(sink_) ))
                    continue

                if index is not None:
                    sources.append( cls._dereference(bus.parent, node, coalesced = True)[index] )
                else:
                    sources.append( cls._dereference(bus.parent, node, coalesced = True) )
            return cls.concat(sources)
        else:
            sources = []
            for bit in sink:
                try:
                    node = next(sink.parent._conn_graph.predecessors( cls._reference(bit) ))
                except (StopIteration, NetworkXError):
                    sources.append( Unconnected(1) )
                    continue

                sources.append( cls._dereference(sink.parent, node) )
            return cls.concat(sources)

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
            return Unconnected(0)

    # @classmethod
    # def get_hierarchical_multisource(cls, sink):
    #     """Get the hierarchical sources connected to ``sink``."""
    #     if sink.net_type.is_port:
    #         if sink.parent._allow_multisource:
    #             return cls.get_multisource(sink)
    #         else:
    #             s = cls.get_source(sink)
    #             if s.net_type.is_unconnected:
    #                 return Unconnected(0)
    #             else:
    #                 return s
    #     elif sink.net_type.is_pin:
    #         flat_sink, hierarchy = None, None
    #         if sink.bus_type.is_nonref:
    #             if sink.model.direction.is_output:
    #                 flat_sink = sink.model
    #                 hierarchy = sink.hierarchy
    #             else:
    #                 flat_sink = sink.model._to_pin(sink.hierarchy[:1])
    #                 hierarchy = sink.hierarchy[1:]
    #         else:
    #             if sink.bus.model.direction.is_output:
    #                 flat_sink = sink.bus.model[sink.index]
    #                 hierarchy = sink.bus.hierarchy
    #             else:
    #                 flat_sink = sink.bus.model._to_pin(sink.bus.hierarchy[:1])[sink.index]
    #                 hierarchy = sink.bus.hierarchy[1:]
    #         flat_sources = None
    #         if flat_sink.parent._allow_multisource:
    #             flat_sources = cls.get_multisource(flat_sink)
    #         else:
    #             flat_sources = cls.get_source(flat_sink)
    #             if flat_sources.net_type.is_unconnected:
    #                 flat_sources = Unconnected(0)
    #         if not hierarchy:
    #             return cls.concat(flat_sources)
    #         else:
    #             flat_sources = flat_sources.items if flat_sources.bus_type.is_concat else (flat_sources, )
    #             sources = []
    #             for source in flat_sources:
    #                 if source.bus_type.is_nonref:
    #                     if source.net_type.is_port:
    #                         sources.append( source._to_pin(hierarchy) )
    #                     elif source.net_type.is_pin:
    #                         sources.append( source.model._to_pin(source.hierarchy + hierarchy) )
    #                     elif source.net_type.is_const:
    #                         sources.append( source )
    #                 else:
    #                     if source.net_type.is_port:
    #                         sources.append( source.bus._to_pin(hierarchy)[source.index] )
    #                     else:
    #                         sources.append( source.bus.model._to_pin(source.bus.hierarchy + hierarchy)[source.index] )
    #             return cls.concat(sources)

    @classmethod
    def get_connection(cls, source, sink):
        """Get an edittable :obj:`dict` for key-value attributes associated with the edge from ``source`` to
        ``sink``."""
        if source.parent is not sink.parent:
            raise PRGAInternalError("Source net '{}' and sink net '{}' are not in the same module"
                    .format(source, sink))
        elif source.parent._coalesce_connections:
            if not source.bus_type.is_nonref:
                raise PRGAInternalError("'{}' does not support bitwise connection (source net '{}' is not a bus)"
                        .format(source.parent, source))
            elif not sink.bus_type.is_nonref:
                raise PRGAInternalError("'{}' does not support bitwise connection (sink net '{}' is not a bus)"
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

# ----------------------------------------------------------------------------
# -- Slice Reference of a Bus ------------------------------------------------
# ----------------------------------------------------------------------------
class Slice(Object, AbstractGenericNet):
    """Reference to a consecutive subset of a port/pin/logic bus.

    Args:
        bus (`AbstractGenericBus`): The referred bus
        index (:obj:`int` or :obj:`slice`): Index of the bit(s) in the bus.

    Direct instantiation of this class is not recommended.
    """

    __slots__ = ['bus', 'index']

    # == internal API ========================================================
    def __init__(self, bus, index):
        self.bus = bus
        self.index = index

    def __str__(self):
        if isinstance(self.index, int):
            return 'Bit({}[{}])'.format(self.bus, self.index)
        else:
            return 'Slice({}[{}:{}])'.format(self.bus, self.index.start, self.index.stop)

    # == low-level API =======================================================
    @property
    def bus_type(self):
        return BusType.slice_

    @property
    def net_type(self):
        return self.bus.net_type

    @property
    def name(self):
        if isinstance(self.index, int):
            return '{}[{}]'.format(self.bus.name, self.index)
        else:
            return '{}[{}:{}]'.format(self.bus.name, self.index.stop - 1, self.index.start)

    @property
    def is_source(self):
        return self.bus.is_source

    @property
    def is_sink(self):
        return self.bus.is_sink

    @property
    def node(self):
        return self.index, self.bus.node

    @property
    def parent(self):
        return self.bus.parent

    def __len__(self):
        if isinstance(self.index, int):
            return 1
        else:
            return self.index.stop - self.index.start

    def __getitem__(self, index):
        if not isinstance(index, int) and not isinstance(index, slice):
            raise PRGATypeError("index", "int or slice")
        index = compose_slice(self.index, index)
        if index is None:
            return Unconnected(0)
        else:
            return type(self)(self.bus, index)

# ----------------------------------------------------------------------------
# -- A Concatenation of Slices and/or buses ----------------------------------
# ----------------------------------------------------------------------------
class Concat(Object, AbstractGenericBus):
    """A concatenation of slices and/or buses.

    Args:
        items (:obj:`Sequence` [`AbstractGenericNet` ]): Items to be contenated together

    Direct instantiation of this class is not recommended. Use `NetUtils.concat` instead.
    """

    __slots__ = ['items']

    # == internal API ========================================================
    def __init__(self, items):
        self.items = items

    def __str__(self):
        return 'Concat({})'.format(", ".join(str(i) for i in self.items))

    # == low-level API =======================================================
    @property
    def bus_type(self):
        return BusType.concat

    @property
    def name(self):
        return '{{{}}}'.format(", ".join(i.name for i in reversed(self.items)))

    @property
    def is_source(self):
        return all(i.is_source for i in self.items)

    @property
    def is_sink(self):
        return all(i.is_sink for i in self.items)

    def __len__(self):
        return sum(len(i) for i in self.items)

    def __getitem__(self, index):
        start, range_ = None, None
        if isinstance(index, int):
            start = index
            range_ = 1
        elif isinstance(index, slice):
            if index.step not in (None, 1):
                raise PRGAIndexError("'step' must be 1 when indexing a concat with a slice")
            start = max(0, uno(index.start, 0))
            if index.stop is not None:
                if index.stop <= start:
                    return Unconnected(0)
                else:
                    range_ = index.stop - start
        # count down
        items = []
        for i in self.items:
            l = len(i)
            # update start
            if start >= l:
                start -= l
                continue
            # start concatenating
            if range_ is None:
                items.append(i[start:])
                start = 0
            else:
                ll = min(l - start, range_)
                items.append(i[start:start + ll])
                start = 0
                range_ -= ll
                if range_ == 0:
                    break
        if not items and isinstance(index, int):
            raise IndexError(index)
        # convert concatenation to a valid form
        return NetUtils.concat(items, skip_flatten = True)
