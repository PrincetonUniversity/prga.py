# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import BusType, NetType, AbstractGenericBus, AbstractInterfaceNet
from .const import Unconnected, Const
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
    def _slice_intersect(cls, src, dst):
        """``None``, :obj:`int` or :obj:`slice`: Apply :obj:`int` or :obj:`slice` ``dst`` on :obj:`int` or :obj:`slice`
        ``src``.  If any argument is :obj:`slice`, its ``step`` is ignored and treated as ``1``."""
        if isinstance(src, int):
            if (dst == 0 if isinstance(dst, int) else dst.start <= 0 < dst.stop):
                return src
            else:
                raise PRGAIndexError("Index out of range")
        else:
            low, high = 0, max(0, src.stop - src.start)
            if isinstance(dst, int):
                if low <= dst < high:
                    return src.start + dst
                else:
                    raise PRGAIndexError("Index out of range")
            else:
                start = max(low, uno(dst.start, low))
                stop = min(high, uno(dst.stop, high))
                if stop <= start:
                    return None
                elif stop == start + 1:
                    return src.start + start
                else:
                    return slice(src.start + start, src.start + stop)

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
    def _reference(cls, net, hierarchy = tuple(), coalesced = False):
        """Get the node ID of ``net`` to be used in accessing the connection graph.

        Args:
            net (`Slice` or `AbstractNet`): 
            hierarchy (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical instance in ascending order
            coalesced (:obj:`bool`): See below

        Returns:
            :obj:`tuple` [:obj:`Hashable`, ... ]: Returns the hierarchy of the bus if ``coalesced`` is set
            :obj:`tuple` [:obj:`int`, :obj:`tuple` [:obj:`Hashable`, ... ]]: Returns the index of the bit in the bus
                plus the hierarchy of the bus if ``coalesced`` is not set

        The returned value if ``coalesced`` is set, or the second element in the returned tuple if ``coalesced`` is
        not set, is a sequence of keys. The contents of this sequence are as follows:
        
        If the referred net is a port, the sequence contains only one element, the key of the port in its parent
        module's port mapping.
        
        If the referred net is a pin, the sequence contains two elements: 1. the key of the pin in its parent
        instance's pin mapping, and 2. the key of the instance in its parent module's instance mapping.

        If the referred net is a hierarchical pin, the sequence may contain more than two elements: the first being
        the key of the pin in its parent instance's pin mapping, and the rest being the keys of the instances in the
        hierarchy in bottom-up order.
        """
        if net.net_type.is_const:
            return net.value
        elif net.net_type.is_pin and (not hierarchy or net.parent is not hierarchy[0]):
            hierarchy = (net.parent.key, ) + tuple(inst.key for inst in hierarchy)
        else:
            hierarchy = tuple(inst.key for inst in hierarchy)
        if coalesced:
            if not net.bus_type.is_nonref:
                raise PRGAInternalError("Cannot get the reference to {} when `coalesced` is set"
                        .format(net))
            return (net.key, ) + hierarchy
        else:
            if len(net) != 1:
                raise PRGAInternalError("Cannot get the reference to {} when `coalesced` is not set"
                        .format(net))
            elif net.bus_type.is_nonref:
                return 0, (net.key, ) + hierarchy
            else:
                return net.index, (net.bus.key, ) + hierarchy

    @classmethod
    def _dereference(cls, module, node, hierarchical = False, coalesced = False):
        """Dereference ``node`` in ``modules``'s connection graph.

        Args:
            module (`AbstractModule`):
            node (:obj:`int`, :obj:`tuple` [:obj:`Hashable`, ... ] or :obj:`tuple` [:obj:`int`, :obj:`tuple`
                [:obj:`Hashable`, ... ]]):
            hierarchical (:obj:`bool`): If set, allow dereferencing hierarchical references
            coalesced (:obj:`bool`): See ``coalesced`` in `NetUtils._reference`

        Return:
            net (`Port`, `Pin`, `Slice` or `Const`): 
            hierarchy (:obj:`tuple` [`AbstractInstance` ]): Hierarchy in bottom-up order. Only available if
                ``hierarchical`` is set
        """
        if isinstance(node, int):
            if hierarchical:
                return Const(node, 1), tuple()
            else:
                return Const(node, 1)
        index, node = (None, node) if coalesced else node
        net_key, hierarchy = node[0], node[1:]
        if len(hierarchy) > 1 and not hierarchical:
            raise PRGATypeError("Node '{}' is a hierarchical reference".format(node))
        instances, parent = [], module
        for instance_key in reversed(hierarchy):
            instance = parent.instances[instance_key]
            instances.append(instance)
            parent = instance.model
        bus, hierarchy = None, tuple(reversed(instances))
        if hierarchical:
            try:
                bus = parent.ports[net_key]
            except KeyError:
                bus = parent.logics[net_key]
            if index is None:
                return bus, hierarchy
            else:
                return bus[index], hierarchy
        else:
            if instances:
                bus = instances[0].pins[net_key]
            else:
                try:
                    bus = module.ports[net_key]
                except KeyError:
                    bus = module.logics[net_key]
            if index is None:
                return bus
            else:
                return bus[index]

    @classmethod
    def _get_connection_by_node(cls, module, source, sink):
        """Get an edittable :obj:`dict` for key-value attributes associated with the edge from ``source`` to
        ``sink``."""
        try:
            return module._conn_graph.edges[source, sink]
        except KeyError:
            return None

    @classmethod
    def concat(cls, items, skip_flatten = False):
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
                if i.bus is not concat[-1].bus:
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
    def connect(cls, sources, sinks, fully = False, coalesced = False, **kwargs):
        """Connect ``sources`` and ``sinks``.

        Args:
            sources: a bus, a slice of a bus, a bit of a bus, or an iterable of the items listed above
            sink: a bus, a slice of a bus, a bit of a bus, or an iterable of the items listed above
            fully (:obj:`bool`): If set, every bit in ``sources`` is connected to all bits in ``sinks``. Incompatible
                with ``coalesced``
            coalesced (:obj:`bool`): If set, connections are made in the granularity of buses. Incompatible with
                ``fully``
            **kwargs: Custom attibutes assigned to the connections
        """
        if fully and coalesced:
            raise PRGAInternalError("`fully` and `coalesced` are incompatible")
        sources, sinks = map(cls.concat, (sources, sinks))
        if coalesced:
            if sources.bus_type.is_slice:
                raise PRGAInternalError(
                        "Source '{}' is not a bus so cannot be connected with a coalesced connection"
                        .format(sources))
            elif sources.bus_type.is_nonref:
                sources = (sources, )
            else:
                for source in sources.items:
                    if not source.bus_type.is_slice:
                        raise PRGAInternalError(
                                "Source '{}' is not a bus so cannot be connected with a coalesced connection"
                                .format(source))
                sources = sources.items
            if sinks.bus_type.is_slice:
                raise PRGAInternalError(
                        "Sink '{}' is not a bus so cannot be connected with a coalesced connection"
                        .format(sinks))
            elif sinks.bus_type.is_nonref:
                sinks = (sinks, )
            else:
                for sink in sinks.items:
                    if not sink.bus_type.is_slice:
                        raise PRGAInternalError(
                                "Sink '{}' is not a bus so cannot be connected with a coalesced connection"
                                .format(sink))
                sinks = sinks.items
            if len(sources) != len(sinks):
                _logger.warning("Length mismatch: sources({}) != sinks({})"
                        .format(len(sources), len(sinks)))
            for src, sink in zip(sources, sinks):
                if len(src) != len(sink):
                    raise PRGAInternalError("Width mismatch: len({}) = {} != len({}) = {}"
                            .format(src, len(src), sink, len(sink)))
                parent = sink.parent.parent if sink.net_type.is_pin else sink.parent
                if not (sink.net_type.is_const or
                        parent is (src.parent.parent if src.net_type.is_pin else src.parent)):
                    raise PRGAInternalError("Cannot connect {} and {}. Different parent modules.".format(src, sink))
                elif not parent._coalesce_connections:
                    raise PRGAInternalError("'{}' does not support coalesced connections".format(parent))
                sink_node = cls._reference(sink, coalesced = True)
                if not (sink_node not in parent._conn_graph or parent._conn_graph.in_degree( sink_node ) == 0):
                    raise PRGAInternalError(
                            "{} is already connected to {} and module {} does not allow multi-source connections"
                            .format(sink, cls.get_source(sink), parent))
                parent._conn_graph.add_edge( cls._reference(src, coalesced = True), sink_node, **kwargs )
        else:
            if not fully and len(sources) != len(sinks):
                _logger.warning("Width mismatch: len({}) = {} != len({}) = {}"
                        .format(sources, len(sources), sinks, len(sinks)))
            pairs = product(sources, sinks) if fully else zip(sources, sinks)
            for src, sink in pairs:
                if not src.is_source:
                    raise PRGAInternalError("{} of {} is not a source".format(src, sources))
                elif not sink.is_sink:
                    raise PRGAInternalError("{} of {} is not a sink".format(sink, sinks))
                elif src.net_type.is_unconnected:
                    continue    # use disconnect to disconnect instead of connect it to "unconnected"
                parent = sink.parent.parent if sink.net_type.is_pin else sink.parent
                if parent._coalesce_connections:
                    raise PRGAInternalError("{} requires coalesced connections".format(parent))
                sink_node = cls._reference(sink)
                if not (parent._allow_multisource or
                        sink_node not in parent._conn_graph or
                        parent._conn_graph.in_degree( sink_node ) == 0):
                    raise PRGAInternalError(
                            "{} is already connected to {} and module {} does not allow multi-source connections"
                            .format(sink, cls.get_source(sink), parent))
                elif not (sink.net_type.is_const or
                        parent is (src.parent.parent if src.net_type.is_pin else src.parent)):
                    raise PRGAInternalError("Cannot connect {} and {}. Different parent modules.".format(src, sink))
                else:
                    parent._conn_graph.add_edge( cls._reference(src), sink_node, **kwargs )

    @classmethod
    def get_source(cls, sink):
        """Get the source connected to ``sink``. This method is for accessing connections in modules that do not allow
        multi-source connections only."""
        if not sink.is_sink:
            raise PRGAInternalError("{} is not a sink".format(sink))
        parent = sink.parent.parent if sink.net_type.is_pin else sink.parent
        if parent._allow_multisource:
            raise PRGAInternalError(
                    "Module {} allows multi-source connections. Use `NetUtils.get_multisource` instead"
                    .format(parent))
        if parent._coalesce_connections:
            sinks = sink.items if sink.bus_type.is_concat else (sink, )
            sources = []
            for sink_ in sinks:
                if sink_.bus_type.is_slice:
                    try:
                        node = next(parent._conn_graph.predecessors( cls._reference(sink_.bus, coalesced = True) ))
                    except (StopIteration, NetworkXError):
                        sources.append( Unconnected( len(sink_) ))
                        continue

                    sources.append( cls._dereference(parent, node, coalesced = True)[sink_.index] )
                else:
                    try:
                        node = next(parent._conn_graph.predecessors( cls._reference(sink_, coalesced = True) ))
                    except (StopIteration, NetworkXError):
                        sources.append( Unconnected( len(sink_) ))
                        continue
                    
                    sources.append( cls._dereference(parent, node, coalesced = True) )
            return cls.concat(sources)
        else:
            sources = []
            for bit in sink:
                try:
                    node = next(parent._conn_graph.predecessors( cls._reference(bit) ))
                except (StopIteration, NetworkXError):
                    sources.append( Unconnected(1) )
                    continue

                sources.append( cls._dereference(parent, node) )
            return cls.concat(sources)

    @classmethod
    def get_multisource(cls, sink):
        """Get the sources connected to ``sink``. This method is for accessing connections in modules that allow
        multi-source connections."""
        if not sink.is_sink:
            raise PRGAInternalError("{} is not a sink".format(sink))
        elif len(sink) != 1:
            raise PRGAInternalError("{} is not 1-bit wide".format(sink))
        parent = sink.parent.parent if sink.net_type.is_pin else sink.parent
        try:
            return tuple( cls._dereference(parent, node) for node in
                    parent._conn_graph.predecessors( cls._reference(sink) ) )
        except NetworkXError:
            return tuple()

    @classmethod
    def get_connection(cls, source, sink, source_hierarchy = tuple(), sink_hierarchy = tuple(), coalesced = False):
        """Get an edittable :obj:`dict` for key-value attributes associated with the edge from ``source`` to
        ``sink``."""
        source_parent = (source_hierarchy[-1].parent if source_hierarchy else
                source.parent.parent if source.net_type.is_pin else source.parent)
        sink_parent = (sink_hierarchy[-1].parent if sink_hierarchy else
                sink.parent.parent if sink.net_type.is_pin else sink.parent)
        if source_parent is not sink_parent:
            raise PRGAInternalError("Source net '{}' (hierarchy : [{}]) and sink net '{}' (hierarchy: [{}]) "
                    .format(source, ', '.join(map(str, reversed(source_hierarchy))),
                        sink, ', '.join(map(str, reversed(sink_hierarchy)))) +
                    "are not in the same module")
        elif coalesced and not source_parent._coalesce_connections:
            raise PRGAInternalError("'{}' does not support coalesced connections".format(source_parent))
        return cls._get_connection_by_node(source_parent,
                cls._reference(source, source_hierarchy, coalesced = coalesced),
                cls._reference(sink, sink_hierarchy, coalesced = coalesced))

    @classmethod
    def verilog_str(cls, net, hierarchy = tuple()):
        """:obj:`str`: Generate the Verilog string for ``net`` in ``hierarchy``."""
        if hierarchy:
            return "/".join(i.name for i in reversed(hierarchy)) + "/" + net.name
        else:
            return net.name

# ----------------------------------------------------------------------------
# -- Slice Reference of a Bus ------------------------------------------------
# ----------------------------------------------------------------------------
class Slice(Object, AbstractInterfaceNet):
    """Reference to a consecutive subset of a port/pin/logic bus.

    Args:
        bus (`AbstractBus`): The referred bus
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
    def parent(self):
        return self.bus.parent

    @property
    def key(self):
        return self.bus.key, self.index

    @property
    def direction(self):
        try:
            return self.bus.direction
        except AttributeError:
            raise PRGAInternalError("{} is a logic wire without direction".format(self))

    def __len__(self):
        if isinstance(self.index, int):
            return 1
        else:
            return self.index.stop - self.index.start

    def __getitem__(self, index):
        if not isinstance(index, int) and not isinstance(index, slice):
            raise PRGATypeError("index", "int or slice")
        index = NetUtils._slice_intersect(self.index, index)
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

    Direct instantiation of this class is not recommended.
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
        # convert concatenation to a valid form
        return NetUtils.concat(items, True)
