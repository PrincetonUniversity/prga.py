# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Utility methods for accessing nets."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import NetType, Const, Slice, Concat
from ...util import Object, uno
from ...exception import PRGAInternalError, PRGATypeError, PRGAIndexError

from itertools import zip_longest, product

import logging
_logger = logging.getLogger(__name__)

__all__ = ['NetUtils']

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

    __slots__ = ["_source", "_sink", "__dict__"]

    def __init__(self, source, sink, **kwargs):
        self._source = source
        self._sink = sink
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

# ----------------------------------------------------------------------------
# -- Net Utilities -----------------------------------------------------------
# ----------------------------------------------------------------------------
class NetUtils(object):
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
    def _reference(cls, net, *, coalesced = False):
        """Get a hashable key for ``net``.

        Args:
            net (`AbstractNet`):

        Keyword Args:
            coalesced (:obj:`bool`): If not set (by default), ``net`` must be one-bit wide, and this method returns a
                reference to the bit. If set, ``net`` must be a `NetType.const`, `NetType.port`, `NetType.pin` or
                `NetType.hierarchical`, and this method returns a reference to the bus.
        """
        if net.net_type.is_const:
            return (NetType.const, net.value, net.width)
        elif coalesced:
            if net.net_type.is_port:
                return (net.key, )
            elif net.net_type.is_pin or net.net_type.is_hierarchical:
                return (net.model.key, ) + tuple(i.key for i in net.instance.hierarchy)
            else:
                raise PRGAInternalError("Cannot create coalesced reference for {}".format(net))
        elif len(net) != 1:
            raise PRGAInternalError("Cannot create reference for {}: width > 1".format(net))
        elif net.net_type.is_bit:
            return (net.index, cls._reference(net.bus, coalesced = True))
        elif net.net_type.is_slice:
            return (net.index.start, cls._reference(net.bus, coalesced = True))
        else:
            return (0, cls._reference(net, coalesced = True))

    @classmethod
    def _dereference(cls, module, ref, *, coalesced = False):
        """Dereference ``ref`` in ``module``.

        Args:
            module (`Module`):
            ref: Typically generated by `NetUtils._reference`

        Keyword Args:
            coalesced (:obj:`bool`): Set if ``ref`` is a reference to a bus

        Return:
            net (`AbstractNet`): 
        """
        if ref[0] is NetType.const:
            return Const(*ref[1:])
        index, ref = (None, ref) if coalesced else ref
        net_key, hierarchy = ref[0], ref[1:]
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
        if anchor.net_type.is_slice:
            anchor = anchor.bus
        if anchor.net_type in (NetType.const, NetType.hierarchical):
            raise PRGAInternalError("Cannot connect to {}".format(sinks))
        elif anchor.net_type not in (NetType.port, NetType.pin, NetType.bit):
            raise PRGAInternalError("Unsupported net type: {}".format(anchor.net_type))
        module = anchor.parent
        # 3. if module does not support bitwise connection
        if module._coalesce_connections:
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
            if not module._allow_multisource and len(sink._sources):
                raise PRGAInternalError(
                        "{} is already connected to {}. ({} does not support multi-connections)"
                        .format(sink, next(itervalues(sink._sources)), module))
            srcref, sinkref = map(lambda x: cls._reference(x, coalesced = module._coalesce_connections), (src, sink))
            if (conn := sink._sources.get(srcref)) is None:
                sink._sources[srcref] = src._sinks[sinkref] = NetConnection(src, sink, **kwargs)
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
            elif sink.parent._allow_multisource:
                raise PRGAInternalError(
                        "Module {} allows multi-source connections. Use `NetUtils.get_multisource` instead"
                        .format(sink.parent))
            elif sink.net_type.is_bit or sink.parent._coalesce_connections:
                it = itervalues(sink._sources)
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
        elif not sink.parent._allow_multisource:
            raise PRGAInternalError("{} does not allow multi-source connections".format(sink.parent))
        # convert to bit if this is a single-bit bus
        if sink.net_type in (NetType.port, NetType.pin):
            sink = sink[0]
        # get and return connections
        return cls.concat(iter(conn.source for conn in itervalues(sink._sources)))

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
            return sink._sources[cls._reference(source, coalesced = sink.parent._coalesce_connections)]
        # 1. get the parent module
        module = None
        if sink.net_type.is_reference:
            raise PRGAInternalError("{} is a reference".format(sink))
        elif not sink.is_sink:
            raise PRGAInternalError("{} is not a valid sink".format(sink))
        else:
            module = sink.parent
        # 2. validate sink
        if module._coalesce_connections and sink.net_type.is_bit:
            raise PRGAInternalError("{} does not support bitwise connections ({} is not a bus)"
                    .format(module, sink))
        elif not sink.net_type.is_bit:
            if len(sink) > 1:
                raise PRGAInternalError("{} is not 1-bit wide".format(sink))
            sink = sink[0]
        # 3. validate source
        if source.net_type.is_reference:
            raise PRGAInternalError("{} is a reference".format(source))
        elif not source.is_source:
            raise PRGAInternalError("{} is not a valid source".format(source))
        elif not source.net_type.is_const:
            if source.parent is not module:
                raise PRGAInternalError("Source = {} and Sink = {} are not in the same module"
                        .format(source, sink))
            elif module._coalesce_connections and source.net_type.is_bit:
                raise PRGAInternalError("{} does not support bitwise connections ({} is not a bus)"
                        .format(module, source))
            elif not source.net_type.is_bit:
                if len(source) > 1:
                    raise PRGAInternalError("{} is not 1-bit wide".format(source))
                source = source[0]
        # 4. get connection
        conn = sink._sources.get( cls._reference(source, coalesced = module._coalesce_connections) )
        if conn is not None or return_none_if_unconnected:
            return conn
        else:
            raise PRGAInternalError("{} and {} are not connected".format(source, sink))
