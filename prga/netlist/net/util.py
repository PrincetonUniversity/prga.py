# -*- encoding: ascii -*-
"""Utility methods for accessing nets."""

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
        source (`AbstractNonReferenceNet`): The combinational source or clock of this timing arc
        sink (`AbstractNonReferenceNet`): The conbinational sink or sequential startpoint/endpoint of this timing
            arc

    Keyword Args:
        max_ (:obj:`list` [:obj:`float` ]): Maximum values for each ``source``-``sink`` pair if ``type_`` is
            `TimingArcType.comb_bitwise`, `TimingArcType.seq_start` or `TimingArcType.seq_end`. This is the setup
            value if ``type_`` is `TimingArcType.seq_end`
        max_ (:obj:`list` [:obj:`list` [:obj:`float` ]]): Maximum values for each ``source``-``sink`` pair if
            ``type_`` is `TimingArcType.comb_matrix`. The 2D array should be index-able by ``source`` index first,
            then ``sink`` index
        min_: The minimum counterpart for the above maximum values. If ``type_`` is `TimingArcType.seq_end`, this
            is the hold value
    """

    __slots__ = ['_type', '_source', '_sink', '_max', '_min']

    def __init__(self, type_, source, sink, *, max_ = None, min_ = None):
        self._type = type_
        self._source = source
        self._sink = sink

        self._max = max_
        self._min = min_

    def __repr__(self):
        return "TimingArc({}: {} -> {})".format(self.type_.name, self.source, self.sink)

    @property
    def type_(self):
        """`TimingArcType`: Type of this timing arc."""
        return self._type

    @property
    def source(self):
        """`AbstractNonReferenceNet`: The combinational source or clock of this timing arc."""
        return self._source

    @property
    def sink(self):
        """`AbstractNonReferenceNet`: The combinational sink or sequential startpoint/endpoint of this timing arc."""
        return self._sink

    @property
    def min_(self):
        """:obj:`list` [:obj:`float` ] or :obj:`list` [:obj:`list` [:obj:`float` ]]: The min/hold value(s) of this
        timing arc."""
        return self._min

    @min_.setter
    def min_(self, v):
        self._min = v

    @property
    def max_(self):
        """:obj:`list` [:obj:`float` ] or :obj:`list` [:obj:`list` [:obj:`float` ]]: The max/setup value(s) of this
        timing arc."""
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

    Direct instantiation of this class is not recommended. Use `NetUtils.connect` instead.
    """

    __slots__ = ["_source", "_sink", "_arc", "__dict__"]

    def __init__(self, source, sink, **kwargs):
        self._source = source
        self._sink = sink

        if source.net_type.is_const:
            self._arc = None
        else:
            self._arc = TimingArc(TimingArcType.comb_bitwise, source, sink)

        for k, v in kwargs.items():
            setattr(self, k, v)

    def __repr__(self):
        return "Connection({} -> {})".format(self.source, self.sink)

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
    def arc(self):
        """`TimingArc`: Timing arc associated with this connection."""
        return self._arc

# ----------------------------------------------------------------------------
# -- Net Utilities -----------------------------------------------------------
# ----------------------------------------------------------------------------
class NetUtils(Object):
    """A wrapper class for utility functions for nets."""

    @classmethod
    def __concat_same(cls, i, j):
        """Return the bus if ``i`` and ``j`` are the same. Otherwise return ``None``."""
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
            return (net.value, len(net), NetType.const)
        elif net.net_type.is_port:
            return (net.key, )
        elif net.net_type in (NetType.pin, NetType.hierarchical):
            return (net.model.key, ) + tuple(i.key for i in net.instance.hierarchy)
        elif net.net_type.is_bit or net.net_type.is_slice:
            return (net.index, cls._reference(net.bus))
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
        # special cases
        if len(ref) == 3 and ref[-1] is NetType.const:
            return Const(*ref[:2])
        elif len(ref) == 2 and (isinstance(ref[0], int) or isinstance(ref[0], slice)) and isinstance(ref[1], tuple):
            # try if this is a bit/slice
            try:
                return cls._dereference(module, ref[1])[ref[0]]
            except (KeyError, IndexError):
                pass
        instance = []
        for inst_key in reversed(ref[1:]):
            instance.append(instance[-1].model.instances[inst_key] if instance
                    else module.instances[inst_key])
        if len(instance) == 0:
            return module.ports[ref[0]]
        elif len(instance) == 1:
            return instance[0].pins[ref[0]]
        else:
            return instance[0]._extend_hierarchy(below = tuple(reversed(instance[1:]))).pins[ref[0]]

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
                    if item.net_type not in (NetType.port, NetType.pin, NetType.const):
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
            elif len(src) != len(sink):
                raise PRGAInternalError("Width mismatch: len({}) = {} != len({}) = {}"
                        .format(src, len(src), sink, len(sink)))
            srcref, sinkref = map(lambda x: cls._reference(x), (src, sink))
            if (conn := sink._connections.get(srcref)) is None:
                if not module.allow_multisource and len(sink._connections):
                    raise PRGAInternalError(
                            "{} is already connected to {}. ({} does not support multi-connections)"
                            .format(sink, next(iter(sink._connections.values())), module))
                conn = sink._connections[srcref] = NetConnection(src, sink, **kwargs)
                if not src.net_type.is_const:
                    src._connections[srcref] = conn
            else:
                for k, v in kwargs.items():
                    setattr(conn, k, v)

    @classmethod
    def get_source(cls, sink, *, return_const_if_unconnected = False):
        """Get the source connected to ``sink``. This method is only for accessing connections in modules that do not
        allow multi-source connections.
        
        Args:
            sink (`AbstractNet`):

        Keyword Args:
            return_const_if_unconnected (:obj:`bool`): If set, this method returns a `Const` object when ``sink`` is
                not connected to any sources. Otherwise this method returns ``None``.

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
                it = iter(sink._connections.values())
                try:
                    conn = next(it)
                except StopIteration:
                    if return_const_if_unconnected:
                        return Const(width = len(sink))
                    else:
                        return None
                try:
                    next(it)
                    raise PRGAInternalError( "{} is connected to more than one sources".format(sink))
                except StopIteration:
                    pass
                return conn.source
            else:
                source = cls.concat(iter(cls.get_source(bit, return_const_if_unconnected = True) for bit in sink))
                if source.net_type.is_const and source.value is None and not return_const_if_unconnected:
                    return None
                else:
                    return source
        elif sink.net_type.is_hierarchical:
            raise PRGAInternalError("{} is a hierarchical pin".format(sink))
        elif sink.net_type.is_slice:
            if (source := cls.get_source(sink.bus)) is None:
                if return_const_if_unconnected:
                    return Const(width = len(sink))
                else:
                    return None
            else:
                return source[sink.index]
        elif sink.net_type.is_concat:
            return cls.concat(iter(cls.get_source(i, return_const_if_unconnected = True) for i in sink.items))
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
        return cls.concat(iter(conn.source for conn in sink._connections.values()))

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
                return tuple(conn.sink for conn in source._connections.values())
        elif source.net_type.is_slice and source.parent.coalesce_connections:
            return tuple(sink[source.index] for sink in cls.get_sinks(source))
        bitwise = tuple(cls.get_sinks(bit) for bit in source)
        l = []
        for sinks in zip_longest(bitwise):
            l.append(cls.concat(uno(sink, Const(width = 1)) for sink in sinks))
        return tuple(l)

    @classmethod
    def get_connection(cls, source, sink, *, raise_error_if_unconnected = False, skip_validations = False):
        """Get the connection from ``source`` to ``sink``.
        
        Args:
            source (`AbstractNonReferenceNet`):
            sink (`AbstractNonReferenceNet`):

        Keyword Args:
            raise_error_if_unconnected (:obj:`bool`): If set, this method raises a `PRGAInternalError` if the
                specified nets are not connected. Otherwise, this method returns ``None``.
            skip_validations (:obj:`bool`): If set, this method skips all validations. This option saves runtime but
                should be used with care

        Returns:
            `NetConnection` or ``None``:
        """
        # 0. shortcut
        if skip_validations:
            if (conn := sink._connections.get( cls._reference(source) )) is None and raise_error_if_unconnected:
                raise PRGAInternalError("{} and {} are not connected".format(source, sink))
            else:
                return conn
        # 1. validate sink (first pass)
        if sink.net_type.is_reference:
            raise PRGAInternalError("{} is a reference".format(sink))
        elif not sink.is_sink:
            raise PRGAInternalError("{} is not a valid sink".format(sink))
        # 2. get the parent module
        module = sink.parent
        if module.is_cell:
            raise PRGAInternalError(
                    "{} is a cell module. Get timing arcs with `NetUtils.get_timing_arc` instead"
                    .format(module))
        # 3. validate sink (second pass)
        if module.coalesce_connections:
            if sink.net_type not in (NetType.port, NetType.pin):
                raise PRGAInternalError("{} does not support bitwise connections ({} is not a bus)"
                        .format(module, sink))
        elif len(sink) != 1:
            raise PRGAInternalError("{} is not 1-bit wide".format(sink))
        # 4. validate source
        if source.net_type.is_reference:
            raise PRGAInternalError("{} is a reference".format(source))
        elif not source.is_source:
            raise PRGAInternalError("{} is not a valid source".format(source))
        elif not source.net_type.is_const:
            if source.parent is not module:
                raise PRGAInternalError("Source = {} and Sink = {} are not in the same module"
                        .format(source, sink))
            elif module.coalesce_connections:
                if source.net_type not in (NetType.port, NetType.pin):
                    raise PRGAInternalError("{} does not support bitwise connections ({} is not a bus)"
                            .format(module, source))
            elif len(source) != 1:
                raise PRGAInternalError("{} is not 1-bit wide".format(source))
        # 5. get connection
        if (conn := sink._connections.get( cls._reference(source) )) is None and raise_error_if_unconnected:
            raise PRGAInternalError("{} and {} are not connected".format(source, sink))
        else:
            return conn

    @classmethod
    def create_timing_arc(cls, type_, source, sink, *, max_ = None, min_ = None):
        """Create a ``type_``-typed timing arc from ``source`` to ``sink``.

        Args:
            types (`TimingArcType`): Type of the timing arc
            source (`Port`): An input port or a clock in a cell module
            sink (`Port`): A port in the same cell module

        Keyword Args:
            max_, min_: Refer to `TimingArc` for more information

        Returns:
            `TimingArc`: The created timing arc
        """
        # 1. validate arguments
        if not (source.net_type.is_port and source.parent.is_cell):
            raise PRGAInternalError("{} is not a port in a cell module".format(source))
        elif not (sink.net_type.is_port and sink.parent.is_cell):
            raise PRGAInternalError("{} is not a port in a cell module".format(sink))
        elif source.parent is not sink.parent:
            raise PRGAInternalError("{} and {} are not in the same module".format(source, sink))
        # 2. further validate arguments
        if type_.is_comb_bitwise or type_.is_comb_matrix:
            if not source.is_source:
                raise PRGAInternalError("{} is not a valid combinational source".format(source))
            elif not sink.is_sink:
                raise PRGAInternalError("{} is not a valid combinational sink".format(sink))
            elif type_.is_comb_bitwise and len(source) != len(sink):
                raise PRGAInternalError("Cannot create bitwise timing arc from {} ({} bits) to {} ({} bits)"
                        .format(source, len(source), sink, len(sink)))
        elif type_.is_seq_start or type_.is_seq_end:
            if not source.is_clock:
                raise PRGAInternalError("{} is not a clock".format(source))
        # 3. create timing arc
        srcref, sinkref = map(lambda x: cls._reference(x), (source, sink))
        if (oldarc := sink._connections.get( (type_, srcref) )) is not None:
            raise PRGAInternalError("{} already exists".format(oldarc))
        elif (type_.is_comb_bitwise and
                (oldarc := sink._connections.get( (TimingArcType.comb_matrix, srcref) )) is not None):
            raise PRGAInternalError("{} already exists".format(oldarc))
        elif (type_.is_comb_matrix and
                (oldarc := sink._connections.get( (TimingArcType.comb_bitwise, srcref) )) is not None):
            raise PRGAInternalError("{} already exists".format(oldarc))
        arc = TimingArc(type_, source, sink, max_ = max_, min_ = min_)
        sink._connections[type_, srcref] = source._connections[type_, sinkref] = arc
        return arc

    @classmethod
    def get_timing_arcs(cls, *, source = None, sink = None, types = TimingArcType):
        """Get the timing arc(s) of the specified ``types`` from ``source`` to ``sink``.

        Keyword Args:
            source (`AbstractNet`): If not specified, all timing arcs to ``sink`` are returned
            sink (`AbstractNet`): If not specified, all timing arcs from ``source`` are returned
            types (`TimingArcType` or :obj:`Container` [`TimingArcType` ]): Only return the specified type\(s\) of
                timing arcs

        Returns:
            :obj:`Sequence` [`TimingArc`]: 
        """

        # quick check
        if isinstance(types, TimingArcType):
            types = (types, )
        elif len(types) == 0:
            return tuple()

        # get parent module
        module = None

        # validate ``source``
        if source is not None:
            if source.net_type not in (NetType.port, NetType.pin, NetType.bit):
                raise PRGAInternalError("Invalid source: {}".format(source))
            module = source.parent
            if module.coalesce_connections and source.net_type.is_bit:
                raise PRGAInternalError(
                        "Cannot get single-bit timing arc for {}. {} does not support bitwise connections"
                        .format(source, module))
            elif not module.coalesce_connections and len(source) != 1:
                raise PRGAInternalError(
                        "{} is not a single-bit net. {} supports bitwise connections"
                        .format(source, module))

        # validate ``sink``
        if sink is not None:
            if sink.net_type not in (NetType.port, NetType.pin, NetType.bit):
                raise PRGAInternalError("Invalid sink: {}".format(sink))
            if module is None:
                module = sink.parent
            elif sink.parent is not module:
                raise PRGAInternalError("Source = {} and Sink = {} are not in the same module"
                        .format(source, sink))
            if module.coalesce_connections and sink.net_type.is_bit:
                raise PRGAInternalError(
                        "Cannot get single-bit timing arc for {}. {} does not support bitwise connections"
                        .format(sink, module))
            elif not module.coalesce_connections and len(sink) != 1:
                raise PRGAInternalError(
                        "{} is not a single-bit net. {} supports bitwise connections"
                        .format(sink, module))

        if module is None:
            raise PRGAInternalError("At least one of 'source' and 'sink' must be specified")

        # get timing arcs
        if module.is_cell:
            return tuple(arc for arc in uno(source, sink)._connections.values()
                    if arc.type_ in types and source in (None, arc.source) and sink in (None, arc.sink))
        elif module.coalesce_connections:
            if TimingArcType.comb_bitwise not in types:
                return tuple()
            return tuple(conn.arc for conn in uno(source, sink)._connections.values()
                    if conn.arc is not None and source in (None, conn.source) and sink in (None, conn.sink))
