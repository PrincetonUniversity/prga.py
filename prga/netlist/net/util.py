# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Utility methods for accessing nets."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import NetType, Const, Slice, Concat, TimingArcType
from ...util import Object, uno
from ...exception import PRGAInternalError, PRGATypeError, PRGAIndexError

from itertools import zip_longest, product

import logging
_logger = logging.getLogger(__name__)

__all__ = ['NetUtils']

# ----------------------------------------------------------------------------
# -- Timing Arc --------------------------------------------------------------
# ----------------------------------------------------------------------------
class TimingArc(Object):
    """Timing arcs.

    Args:
        type_ (`TimingArcType`): Type of this timing arc
        source (`AbstractNonReferenceNet`): The startpoint or clock of this timing arc
        sink (`AbstractNonReferenceNet`): The endpoint of this timing arc
        min_ (:obj:`float`): Min value of this arc
        max_ (:obj:`float`): Max value of this arc
    """

    __slots__ = ['_type', '_source', '_sink', '_min', '_max']

    def __init__(self, type_, source, sink, min_ = None, max_ = None):
        self._type = type_
        self._source = source
        self._sink = sink
        self._min = min_
        self._max = max_

    @property
    def type_(self):
        """`TimingArcType`: Type of this timing arc."""
        return self._type

    @property
    def source(self):
        """`AbstractNonReferenceNet`: The startpoint of clock of this timing arc."""
        return self._source

    @property
    def sink(self):
        """`AbstractNonReferenceNet`: The endpoint of this timing arc."""
        return self._sink

    @property
    def min_(self):
        """:obj:`float`: The min value of this timing arc."""
        return self._min

    @min_.setter
    def min_(self, v):
        self._min = v

    @property
    def max_(self):
        """:obj:`float`: The max value of this timing arc."""
        return self._max

    @max_.setter
    def max_(self, v):
        self._max = v

# ----------------------------------------------------------------------------
# -- Net Connection ----------------------------------------------------------
# ----------------------------------------------------------------------------
class NetConnection(Object):
    """Connection between non-reference nets.

    Args:
        source (`AbstractNonReferenceNet`): The driver of this connection
        sink (`AbstractNonReferenceNet`): The drivee of this connection

    Keyword Args:
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes

    Direct instantiation of this class is not recommended. Use `NetUtils.connect` or `NetUtils.create_timing_arc` instead.
    """

    __slots__ = ["_source", "_sink", "_arc", "__dict__"]

    def __init__(self, source, sink, **kwargs):
        self._source = source
        self._sink = sink
        self._arc = TimingArc(TimingArcType.delay, source, sink)

        for k, v in kwargs.items():
            setattr(self, k, v)

    # == low-level API =======================================================
    @property
    def source(self):
        """`AbstractNonReferenceNet`: The driver of this connection."""
        return self._source

    @property
    def sink(self):
        """`AbstractNonReferenceNet`: The drivee of this connection."""
        return self._sink

    @property
    def arc(Self):
        """`TimingArc`: Timing arc associated with this connection."""
        return self._arc

# ----------------------------------------------------------------------------
# -- Net Utilities -----------------------------------------------------------
# ----------------------------------------------------------------------------
class NetUtils(Object):
    """A wrapper class for utility functions for nets."""

    @classmethod
    def __concat_same(cls, i, j):
        """Return the bus ``i`` and ``j`` are the same. Otherwise return ``None``."""
        if i.net_type is not j.net_type:
            return None
        elif i.net_type in (NetType.port, NetType.pin):
            if i is j:
                return i
            else:
                return None
        elif i.net_type.is_hierarchical:
            if i.model is j.model and all(inst_i is inst_j for (inst_i, inst_j) in
                    zip_longest(i.instance.hierarchy, j.instance.hierarchy)):
                return i
            else:
                return None
        else:
            raise PRGAInternalError("Unsupported net type: {}".format(i.net_type))

    @classmethod
    def __concat_append(cls, l, i):
        if len(i) == 0:
            return
        elif len(l) == 0 or i.net_type in (NetType.port, NetType.pin, NetType.hierarchical):
            l.append( i )
        elif i.net_type.is_const:
            if l[-1].net_type.is_const and (i.value is None) == (l[-1].value is None):
                if i.value is None:
                    l[-1] = Const(width = len(l[-1]) + len(i))
                else:
                    l[-1] = Const((i.value << len(l[-1])) + l[-1].value, len(l[-1]) + len(i))
            else:
                l.append( i )
        elif i.net_type.is_bit:
            if (l[-1].net_type.is_bit and (bus := cls.__concat_same(i.bus, l[-1].bus)) and
                    i.index == l[-1].index + 1):
                l[-1] = cls._slice(bus, slice(l[-1].index, i.index + 1))
            elif (l[-1].net_type.is_slice and (bus := cls.__concat_same(i.bus, l[-1].bus)) and
                    i.index == l[-1].index.stop):
                l[-1] = cls._slice(bus, slice(l[-1].index.start, i.index + 1))
            else:
                l.append( i )
        elif i.net_type.is_slice:
            if (l[-1].net_type.is_bit and (bus := cls.__concat_same(i.bus, l[-1].bus)) and
                    i.index.start == l[-1].index + 1):
                l[-1] = cls._slice(bus, slice(l[-1].index, i.index.stop))
            elif (l[-1].net_type.is_slice and (bus := cls.__concat_same(i.bus, l[-1].bus)) and
                    i.index.start == l[-1].index.stop):
                l[-1] = cls._slice(bus, slice(l[-1].index.start, i.index.stop))
            else:
                l.append( i )
        elif i.net_type.is_concat:
            for ii in i.items:
                cls.__concat_append(l, ii)
        else:
            raise PRGAInternalError("Unsupported net type: {}".format(i.net_type))

    @classmethod
    def _slice(cls, bus, index):
        """`Slice` or `AbstractNet`: Create a slice of ``bus``.

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
    def _reference(cls, net):
        """Get a hashable key for ``net``.

        Args:
            net (`AbstractNet`):
        """
        if net.net_type.is_const:
            return (net.value, net.width, NetType.const)
        elif net.net_type.is_port:
            return (net.key, )
        elif net.net_type in (NetType.pin, NetType.hierarchical):
            return (net.model.key, ) + tuple(i.key for i in net.instance.hierarchy)
        elif net.net_type.is_bit or net.net_type.is_slice:
            return (net.index, ) + cls._reference(net.bus)
        else:
            raise PRGAInternalError("Cannot create reference for {}".format(net))

    @classmethod
    def _dereference(cls, module, ref):
        """Dereference ``ref`` in ``module``.

        Args:
            module (`Module`):
            ref: Typically generated by `NetUtils._reference`

        Return:
            net (`AbstractNet`): 
        """
        if ref[-1] is NetType.const:
            return Const(*ref[:2])
        instance = []
        for inst_key in reversed(ref[2:]):
            instance.append(instance[-1].model.instances[inst_key] if len(instance)
                    else module.instances[inst_key])
        if len(instance) == 0:
            instance = None
        elif len(instance) == 1:
            instance = instance[0]
        else:
            instance = instance[0]._extend_hierarchy(below = tuple(reversed(instance[1:])))
        if len(ref) > 1:
            # Take an educated guess if this reference is a bit/slice
            if isinstance(ref[0], int) or isinstance(ref[0], slice):
                try:
                    if instance is None:
                        return module.ports[ref[1]][ref[0]]
                    else:
                        return instance.pins[ref[1]][ref[0]]
                except KeyError:
                    pass
            if instance is None:
                instance = module.instances[ref[1]]
            else:
                instance = instance._extend_hierarchy(below = instance.model.instances[ref[1]])
        if instance is None:
            return module.ports[ref[0]]
        else:
            return instance.pins[ref[0]]

    @classmethod
    def concat(cls, items):
        """`Slice`, `Concat` or other nets: Concatenate the provided iterable of nets."""
        # concatenating
        l = []
        for i in items:
            cls.__concat_append(l, i)
        # emitting final result
        if len(l) == 0:
            return Const()
        elif len(l) == 1:
            return l[0]
        else:
            return Concat(tuple(iter(l)))

    @classmethod
    def connect(cls, sources, sinks, *, fully = False, **kwargs):
        """Connect ``sources`` and ``sinks``.

        Args:
            sources: a bus, a slice of a bus, a bit of a bus, or an iterable of the items listed above
            sink: a bus, a slice of a bus, a bit of a bus, or an iterable of the items listed above

        Keyword Args:
            fully (:obj:`bool`): If set, every bit in ``sources`` is connected to all bits in ``sinks``.
            **kwargs: Custom attibutes assigned to all connections
        """
        # 1. concat the sources & sinks
        sources, sinks = map(cls.concat, (sources, sinks))
        # 2. get the parent module
        anchor = sinks
        if anchor.net_type.is_concat:
            anchor = anchor.items[0]
        if anchor.net_type in (NetType.slice_, NetType.bit):
            anchor = anchor.bus
        if anchor.net_type in (NetType.const, NetType.hierarchical):
            raise PRGAInternalError("Cannot connect to {}".format(sinks))
        elif anchor.net_type not in (NetType.port, NetType.pin):
            raise PRGAInternalError("Unsupported net type: {}".format(anchor.net_type))
        module = anchor.parent
        if module.is_cell:
            raise PRGAInternalError(
                    "{} is a cell module. Create timing arcs with `NetUtils.create_timing_arc` instead"
                    .format(module))
        # 3. if module does not support bitwise connection
        if module.coalesce_connections:
            if fully:
                raise PRGAInternalError("{} does not support bitwise connections (invalid 'fully' flag)"
                        .format(module))
            for concat, list_ in ( (sources, (source_list := [])), (sinks, (sink_list := [])) ):
                for item in (concat.items if concat.net_type.is_concat else [concat]):
                    if item.net_type not in (NetType.port, NetType.pin):
                        raise PRGAInternalError("{} does not support bitwise connections ({} is not a bus)"
                            .format(item))
                    list_.append(item)
            sources, sinks = source_list, sink_list
        # 4. connect!
        if not fully and len(sources) != len(sinks):
            _logger.warning("Width mismatch: len({}) = {} != len({}) = {}"
                    .format(sources, len(sources), sinks, len(sinks)))
        pairs = product(sources, sinks) if fully else zip(sources, sinks)
        for src, sink in pairs:
            if src.net_type.is_reference or not src.is_source:
                raise PRGAInternalError("{} is not a valid source".format(src))
            elif not src.net_type.is_const and src.parent is not module:
                raise PRGAInternalError("Cannot connect {}: different parent module".format(src))
            elif sink.net_type.is_reference or not sink.is_sink:
                raise PRGAInternalError("{} is not a valid sink".format(sink))
            elif sink.parent is not module:
                raise PRGAInternalError("Cannot connect {}: different parent module".format(sink))
            elif src.net_type.is_const and src.value is None:
                continue
            elif not module.allow_multisource and len(sink._connections):
                raise PRGAInternalError(
                        "{} is already connected to {}. ({} does not support multi-connections)"
                        .format(sink, next(itervalues(sink._connections)), module))
            srcref, sinkref = map(lambda x: cls._reference(x), (src, sink))
            if (conn := sink._connections.get(srcref)) is None:
                sink._connections[srcref] = src._connections[sinkref] = NetConnection(src, sink, **kwargs)
            else:
                for k, v in iteritems(kwargs):
                    setattr(conn, k, v)

    @classmethod
    def get_source(cls, sink, *, return_none_if_unconnected = False):
        """Get the source connected to ``sink``. This method is only for accessing connections in modules that do not
        allow multi-source connections only.
        
        Args:
            sink (`AbstractNet`):

        Keyword Args:
            return_none_if_unconnected (:obj:`bool`): If set, this method returns ``None`` when ``sink`` is not
                connected to any sources. Otherwise this method returns a `Const` object.

        Returns:
            ``AbstractNet`` or ``None``:
        """
        if sink.net_type.is_const:
            raise PRGAInternalError("{} is not a valid sink".format(sink))
        elif sink.net_type in (NetType.port, NetType.pin, NetType.bit):
            if not sink.is_sink:
                raise PRGAInternalError("{} is not a valid sink".format(sink))
            elif sink.parent.is_cell:
                raise PRGAInternalError(
                        "{} is a cell module. Get timing arcs with `NetUtils.get_timing_arc` instead"
                        .format(sink.parent))
            elif sink.parent.allow_multisource:
                raise PRGAInternalError(
                        "{} allows multi-source connections. Use `NetUtils.get_multisource` instead"
                        .format(sink.parent))
            elif len(sink) == 1 or sink.parent.coalesce_connections:
                it = iter(itervalues(sink._connections))
                try:
                    conn = next(it)
                except StopIteration:
                    if return_none_if_unconnected:
                        return None
                    else:
                        return Const(width = len(sink))
                try:
                    next(it)
                    raise PRGAInternalError( "{} is connected to more than one sources".format(sink))
                except StopIteration:
                    pass
                return conn.source
            else:
                source = cls.concat(iter(cls.get_source(bit) for bit in sink))
                if return_none_if_unconnected and source.net_type.is_const and source.value is None:
                    return None
                else:
                    return source
        elif sink.net_type.is_hierarchical:
            raise PRGAInternalError("{} is a hierarchical pin".format(sink))
        elif sink.net_type.is_slice:
            if (source := cls.get_source(sink.bus, return_none_if_unconnected = True)) is None:
                if return_none_if_unconnected:
                    return None
                else:
                    return Const(width = len(sink))
            else:
                return source[sink.index]
        elif sink.net_type.is_concat:
            return cls.concat(iter(cls.get_source(i) for i in sink.items))
        else:
            raise PRGAInternalError("Unrecognized NetType: {}".format(sink.net_type))

    @classmethod
    def get_multisource(cls, sink):
        """Get the sources connected to ``sink``. This method is for accessing connections in modules that allow
        multi-source connections."""
        # validate argument
        if sink.net_type.is_reference:
            raise PRGAInternalError("{} is a reference".format(sink))
        elif not sink.is_sink:
            raise PRGAInternalError("{} is not a sink".format(sink))
        elif len(sink) != 1:
            raise PRGAInternalError("{} is not 1-bit wide".format(sink))
        elif sink.parent.is_cell:
            raise PRGAInternalError(
                    "{} is a cell module. Get timing arcs with `NetUtils.get_timing_arc` instead"
                    .format(sink.parent))
        elif not sink.parent.allow_multisource:
            raise PRGAInternalError("{} does not allow multi-source connections".format(sink.parent))
        # get and return connections
        return cls.concat(iter(conn.source for conn in itervalues(sink._connections)))

    @classmethod
    def get_sinks(cls, source):
        """Get the sinks connected to ``source``. This method can be used whether the parent module allows
        multi-source connections or not, and whether the parent module supports bit-wise connections or not.

        Args:
            source (`AbstractNet`):

        Returns:
            :obj:`Sequence` [`AbstractNet` ]:

        This method returns a sequence of nets. Each element in the sequence has the same number of bits as
        ``source``, and each bit is a sink driven by the corresponding bit in ``source``. The element may contain
        ``unconnected`` \(refer to `Const` for more information\) placeholders.

        Examples:
            1. Suppose module ``m`` does not support bit-wise connections \(i.e. ``m.coalesce_connections = True``\),
               and port ``m.ports['i']`` drives ``m.ports['o']`` and ``m.instances['sth'].pins['i']``. Then,
               ``NetUtils.get_sinks(m.ports['i'])`` returns ``tuple(m.ports['o'], m.instances['sth'].pins['i'])``.
               ``NetUtils.get_sinks(m.ports['i'][0])`` returns ``tuple(m.ports['o'][0],
               m.instances['sth'].pins['i'][0])``.
            2. Suppose module ``m`` supports bit-wise connections \(i.e. ``m.coalesce_connections = False``\), and the
               following connections exist: ``m.ports['i'][0] -> m.ports['o'][0]``, ``m.ports['i'][1] ->
               m.ports['o'][1]``, ``m.ports['i'][1] -> m.instances['sth'].pins['i'][0]``. Then,
               ``NetUtils.get_sinks(m.ports['i'])`` returns ``tuple(m.ports['o'], Concat(Unconnected(1),
               m.instances['sth'].pins['i'][0]))``.
        """
        if source.net_type.is_const:
            raise PRGAInternalError("{} is a constant value".format(source))
        elif source.net_type.is_hierarchical:
            raise PRGAInternalError("{} is a hierarchical pin".format(source))
        elif source.net_type in (NetType.port, NetType.pin, NetType.bit):
            if not source.is_source:
                raise PRGAInternalError("{} is not a valid source".format(source))
            elif source.parent.is_cell:
                raise PRGAInternalError(
                        "{} is a cell module. Get timing arcs with `NetUtils.get_timing_arc` instead"
                        .format(source.parent))
            elif len(source) == 1 or source.parent.coalesce_connections:
                return tuple(conn.sink for conn in itervalues(source._connections))
        elif source.net_type.is_slice and source.parent.coalesce_connections:
            return tuple(sink[source.index] for sink in cls.get_sinks(source))
        bitwise = tuple(cls.get_sinks(bit) for bit in source)
        l = []
        for sinks in zip_longest(bitwise):
            l.append(cls.concat(uno(sink, Const(width = 1)) for sink in sinks))
        return tuple(l)

    @classmethod
    def get_connection(cls, source, sink, *, return_none_if_unconnected = False, skip_validations = False):
        """Get the connection from ``source`` to ``sink``.
        
        Args:
            source (`AbstractNonReferenceNet`):
            sink (`AbstractNonReferenceNet`):

        Keyword Args:
            return_none_if_unconnected (:obj:`bool`): If set, this method returns ``None`` if the specified nets are
                not connected. Otherwise, this method throws a `PRGAInternalError`.
            skip_validations (:obj:`bool`): If set, this method skips all validations. This option saves runtime but
                should be used with care

        Returns:
            `NetConnection`:
        """
        # 0. shortcut
        if skip_validations:
            return sink._connections[cls._reference(source)]
        # 1. get the parent module
        module = None
        if sink.net_type.is_reference:
            raise PRGAInternalError("{} is a reference".format(sink))
        elif not sink.is_sink:
            raise PRGAInternalError("{} is not a valid sink".format(sink))
        else:
            module = sink.parent
        if module.is_cell:
            raise PRGAInternalError(
                    "{} is a cell module. Get timing arcs with `NetUtils.get_timing_arc` instead"
                    .format(module))
        # 2. validate sink
        if module.coalesce_connections and sink.net_type.is_bit:
            raise PRGAInternalError("{} does not support bitwise connections ({} is not a bus)"
                    .format(module, sink))
        elif not sink.net_type.is_bit and len(sink) != 1:
            raise PRGAInternalError("{} is not 1-bit wide".format(sink))
        # 3. validate source
        if source.net_type.is_reference:
            raise PRGAInternalError("{} is a reference".format(source))
        elif not source.is_source:
            raise PRGAInternalError("{} is not a valid source".format(source))
        elif not source.net_type.is_const:
            if source.parent is not module:
                raise PRGAInternalError("Source = {} and Sink = {} are not in the same module"
                        .format(source, sink))
            elif module.coalesce_connections and source.net_type.is_bit:
                raise PRGAInternalError("{} does not support bitwise connections ({} is not a bus)"
                        .format(module, source))
            elif not source.net_type.is_bit and len(source) != 1:
                raise PRGAInternalError("{} is not 1-bit wide".format(source))
        # 4. get connection
        conn = sink._connections.get( cls._reference(source) )
        if conn is not None or return_none_if_unconnected:
            return conn
        else:
            raise PRGAInternalError("{} and {} are not connected".format(source, sink))

    @classmethod
    def create_timing_arc(cls, types, sources, sinks, *, fully = False, **kwargs):
        """Create a timing arc from ``sources`` to ``sinks``.

        Args:
            types (`TimingArcType` or :obj:`Sequence` [`TimingArcType` ]): Type(s) of the timing arcs
            sources: a port, a slice of a port, a bit of a port, or an iterable of the items listed above
            sinks: a port, a slice of a port, a bit of a port, or an iterable of the items listed above

        Keyword Args:
            fully (:obj:`bool`): If set, timing arc is created from every bit in ``sources`` to all bits in ``sinks``
            min_ (:obj:`float`): Min value of this arc
            max_ (:obj:`float`): Max value of this arc
        """
        if isinstance(types, TimingArcType):
            types = (types, )
        # 1. concat the sources & sinks
        sources, sinks = map(cls.concat, (sources, sinks))
        # 2. get the parent module
        anchor = sinks
        if anchor.net_type.is_concat:
            anchor = anchor.items[0]
        if anchor.net_type in (NetType.slice_, NetType.bit):
            anchor = anchor.bus
        if not anchor.net_type.is_port:
            raise PRGAInternalError("Cannot create timing arc to {}".format(sinks))
        module = anchor.parent
        if not module.is_cell:
            raise PRGAInternalError(
                    "{} is not a cell module. Create connections with `NetUtils.connect` instead"
                    .format(module))
        # 3. create timing arcs!
        if not fully and len(sources) != len(sinks):
            _logger.warning("Width mismatch: len({}) = {} != len({}) = {}"
                    .format(sources, len(sources), sinks, len(sinks)))
        pairs = product(sources, sinks) if fully else zip(sources, sinks)
        for type_, (src, sink) in product(types, pairs):
            if type_ in (TimingArcType.setup, TimingArcType.clk2q, TimingArcType.hold) and not src.is_clock:
                raise PRGAInternalError("Cannot create sequential timing arc from non-clock net: {}".format(src))
            srcref, sinkref = map(lambda x: cls._reference(x), (src, sink))
            if (arc := sink._connections.get( (type_, srcref) )) is None:
                sink._connections[type_, srcref] = src._connections[type_, sinkref] = TimingArc(
                        type_, src, sink, **kwargs)
            else:
                for k, v in iteritems(kwargs):
                    setattr(arc, k, v)

    @classmethod
    def get_timing_arc(cls, sources = None, sinks = None, types = TimingArcType, *, skip_validations = False):
        """Get the timing arc(s) of the specified ``types`` from ``sources`` to ``sinks``.

        Args:
            sources: 
            sinks:
            types (:obj:`Container` [`TimingArcType` ]):

        Keyword Args:
            skip_validations (:obj:`bool`):
        """
        raise NotImplementedError

    # @classmethod
    # def get_timing_arc(cls, source, sink, *, skip_validations = False):
    #     """Get the timing arc from ``source`` to ``sink``.
    #     
    #     Args:
    #         source (`AbstractNonReferenceNet`):
    #         sink (`AbstractNonReferenceNet`):

    #     Keyword Args:
    #         skip_validations (:obj:`bool`): If set, this method skips all validations. This option saves runtime but
    #             should be used with care

    #     Returns:
    #         `TimingArc`:
    #     """
    #     # 0. shortcut
    #     if skip_validations:
    #         return sink._connections.get( cls._reference(source) )
    #     # 1. get the parent module
    #     module = None
    #     if sink.net_type.is_reference:
    #         raise PRGAInternalError("{} is a reference".format(sink))
    #     elif sink.net_type.is_const:
    #         raise PRGAInternalError("{} is a const net".format(sink))
    #     elif sink.net_type.is_pin:
    #         raise PRGAInternalError("{} is a pin".format(sink))
    #     else:
    #         module = sink.parent
    #     if not module.is_cell:
    #         raise PRGAInternalError(
    #                 "{} is a not cell module. Get connections with `NetUtils.get_connection` instead"
    #                 .format(module))
    #     # 2. validate sink
    #     if len(sink) > 1:
    #         raise PRGAInternalError("{} is not 1-bit wide".format(sink))
    #     elif sink.net_type.is_port:
    #         sink = sink[0]
    #     # 3. validate source
    #     if source.net_type.is_reference:
    #         raise PRGAInternalError("{} is a reference".format(source))
    #     elif source.net_type.is_const:
    #         raise PRGAInternalError("{} is a const net".format(source))
    #     elif source.net_type.is_pin:
    #         raise PRGAInternalError("{} is a pin".format(source))
    #     elif source.parent is not module:
    #         raise PRGAInternalError("Source = {} and Sink = {} are not in the same module"
    #                 .format(source, sink))
    #     elif len(source) > 1:
    #         raise PRGAInternalError("{} is not 1-bit wide".format(source))
    #     elif source.net_type.is_port:
    #         source = source[0]
    #     # 4. get timing arc
    #     return sink._connections.get( cls._reference(source) )
