# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseBuilder, MemOptUserConnGraph
from .block import LogicBlockBuilder
from ..common import (Orientation, Direction, Dimension, Position, ModuleClass, SegmentID, BlockPinID, SegmentType,
        BlockPortFCValue, BlockFCValue, SwitchBoxPattern)
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...exception import PRGAAPIError, PRGAInternalError
from ...util import uno

from collections import namedtuple, OrderedDict
from itertools import product

import logging
_logger = logging.getLogger(__name__)

__all__ = ['ConnectionBoxBuilder', 'SwitchBoxBuilder']

# ----------------------------------------------------------------------------
# -- Base Builder for Routing Boxes ------------------------------------------
# ----------------------------------------------------------------------------
class _BaseRoutingBoxBuilder(BaseBuilder):
    """Base class for routing box builders.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    # == internal API ========================================================
    # -- properties/methods to be overriden by subclasses --------------------
    @classmethod
    def _node_name(cls, node):
        """Generate the name for ``node``."""
        if node.node_type.is_blockpin:
            return 'bp_{}_{}{}{}{}_{}{}'.format(
                node.prototype.parent.name,
                'x' if node.position.x >= 0 else 'u', abs(node.position.x),
                'y' if node.position.y >= 0 else 'v', abs(node.position.y),
                ('{}_'.format(node.subblock) if node.prototype.parent.module_class.is_io_block else ''),
                node.prototype.name)
        else:
            prefix = node.segment_type.case(
                    sboxout = 'so',
                    cboxout = 'co',
                    sboxin_regular = 'si',
                    sboxin_cboxout = 'co',
                    sboxin_cboxout2 = 'co2',
                    cboxin = 'ci',
                    )
            return '{}_{}_{}{}{}{}{}'.format(
                    prefix, node.prototype.name,
                    'x' if node.position.x >= 0 else 'u', abs(node.position.x),
                    'y' if node.position.y >= 0 else 'v', abs(node.position.y),
                    node.orientation.name[0])

    # == high-level API ======================================================
    def connect(self, sources, sinks, *, fully = False):
        """Connect ``sources`` to ``sinks``."""
        NetUtils.connect(sources, sinks, fully = fully)

# ----------------------------------------------------------------------------
# -- Connection Box Key ------------------------------------------------------
# ----------------------------------------------------------------------------
class _ConnectionBoxKey(namedtuple('_ConnectionBoxKey', 'block orientation position identifier')):
    """Connection box key.

    Args:
        block (`AbstractModule`): The logic/io block connected by the connection box
        orientation (`Orientation`): On which side of the logic/io block is the connection box
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): At which position in the logic/io block is the connection
            box
        identifier (:obj:`str`): Unique identifier to differentiate connection boxes for the same location of the same
            block
    """

    def __hash__(self):
        return hash( (self.block.key, self.orientation, self.position, self.identifier) )

# ----------------------------------------------------------------------------
# -- Connection Box Builder --------------------------------------------------
# ----------------------------------------------------------------------------
class ConnectionBoxBuilder(_BaseRoutingBoxBuilder):
    """Connection box builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    # == internal API ========================================================
    @classmethod
    def _segment_relative_position(self, cbox_ori, segment, segment_ori, section = 0):
        if not (0 <= section < segment.length):
            raise PRGAAPIError("Section '{}' does not exist in segment '{}'"
                    .format(section, segment))
        if cbox_ori.dimension.is_y:
            if segment_ori.is_east:
                return (-section, cbox_ori.case(north = 0, south = -1))
            elif segment_ori.is_west:
                return ( section, cbox_ori.case(north = 0, south = -1))
        else:
            if segment_ori.is_north:
                return (cbox_ori.case(west = -1, east = 0), -section)
            elif segment_ori.is_south:
                return (cbox_ori.case(west = -1, east = 0),  section)
        raise PRGAAPIError("Section {} of segment '{}' going {} does not go through cbox '{}'"
                .format(section, segment, segment_ori.name, self._module))

    @classmethod
    def _cbox_key(cls, block, orientation, position = None, identifier = None):
        if block.module_class.is_io_block:
            position = Position(0, 0)
        elif block.module_class.is_logic_block:
            orientation, position = LogicBlockBuilder._resolve_orientation_and_position(block, orientation, position)
        else:
            raise PRGAAPIError("'{}' is not a block".format(block))
        return _ConnectionBoxKey(block, orientation, position, identifier)

    def _add_tunnel_bridge(self, tunnel):
        """Add a bridge for a direct inter-block tunnel.

        Args:
            tunnel (`DirectTunnel`):
        """
        sink = self.get_blockpin(tunnel.sink.key)
        src_node = BlockPinID(tunnel.offset, tunnel.source)
        if src_node in self.ports:
            raise PRGAInternalError("'{}' already added to {}".format(src_node, self._module))
        source = ModuleUtils.create_port(self._module, self._node_name(src_node), len(tunnel.source),
                tunnel.source.direction.opposite, key = src_node)
        NetUtils.connect(source, sink)
        return source

    # == high-level API ======================================================
    def get_segment_input(self, segment, orientation, section = 0, *, dont_create = False):
        """Get the segment input to this connection box.

        Args:
            segment (`Segment`): Prototype of the segment
            orientation (`Orientation`): Orientation of the segment
            section (:obj:`int`): Section of the segment
            dont_create (:obj:`bool`): If set, return ``None`` when the requested segment input is not already created
                instead of create it
        """
        node = SegmentID(self._segment_relative_position(self._module.key.orientation, segment, orientation, section),
                segment, orientation, SegmentType.cboxin)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        segment.width, PortDirection.input_, key = node)

    def get_segment_output(self, segment, orientation, *, dont_create = False):
        """Get or create the segment output from this connection box.

        Args:
            segment (`Segment`): Prototype of the segment
            orientation (`Orientation`): Orientation of the segment
            dont_create (:obj:`bool`): If set, return ``None`` when the requested segment output is not already created
                instead of create it
        """
        node = SegmentID(self._segment_relative_position(self._module.key.orientation, segment, orientation, 0),
                segment, orientation, SegmentType.cboxout)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        segment.width, PortDirection.output, key = node)

    def get_blockpin(self, port, subblock = 0, *, dont_create = False):
        """Get or create the blockpin input/output in this connection box.

        Args:
            port (:obj:`str`): Name of the block port to be connected to this blockpin
            subblock (:obj:`int`): sub-block in a tile
            dont_create (:obj:`bool`): If set, return ``None`` when the requested block pin is not already created
                instead of create it
        """
        block, orientation, position, _1 = self._module.key
        try:
            port = block.ports[port]
        except KeyError:
            raise PRGAAPIError("No port '{}' found in block '{}'".format(port, block))
        if port.orientation not in (Orientation.auto, orientation):
            raise PRGAAPIError("'{}' faces {} but connection box '{}' is on the {} side of '{}'"
                    .format(port, port.orientation.name, self._module, orientation.name, block))
        elif port.position != position:
            raise PRGAAPIError("'{}' is at {} but connection box '{}' is at {} of '{}'"
                    .format(port, port.position, self._module, position, block))
        node = BlockPinID(Position(0, 0), port, subblock)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        len(port), port.direction.opposite, key = node)

    def fill(self, fc, *, segments = None, dont_create = False):
        """Add port-segment connections using FC values.

        Args:
            fc (`BlockFCValue`): A `BlockFCValue` or arguments that can be used to construct a `BlockFCValue`, for
                example, an :obj:`int`, or a :obj:`tuple` of :obj:`int` and overrides. Refer to `BlockFCValue` for
                more details
            segments (:obj:`Sequence` [:obj:`Segment` ] or :obj:`Mapping` [:obj:`Hashable`, :obj:`Segment` ]): If not
                set, segments from the context is used
            dont_create (:obj:`bool`): If set, connections are made only between already created nodes
        """
        block, orientation, position, _ = self._module.key
        # FC value
        fc = BlockFCValue._construct(fc)
        for tunnel in itervalues(self._context.tunnels):
            for port in (tunnel.source, tunnel.sink):
                if port.parent is block:
                    fc.overrides[port.key] = BlockPortFCValue(0)
        # segments
        if segments is None:
            segments = tuple(itervalues(self._context.segments))
        elif isinstance(segments, Mapping):
            segments = tuple(itervalues(segments))
        # start generation
        iti = [0 for _ in segments]
        oti = [0 for _ in segments]
        for port in itervalues(block.ports):
            if not (port.position == position and port.orientation in (orientation, Orientation.auto)):
                continue
            elif hasattr(port, 'global_'):
                continue
            for sgmt_idx, sgmt in enumerate(segments):
                nc = fc.port_fc(port, sgmt, port.direction.is_input)  # number of connections
                if nc == 0:
                    continue
                imax = port.direction.case(sgmt.length * sgmt.width, sgmt.width)
                istep = max(1, imax // nc)                  # index step
                for _, port_idx, subblock in product(range(nc), range(len(port)), range(block.capacity)):
                    section = port.direction.case(iti[sgmt_idx] % sgmt.length, 0)
                    track_idx = port.direction.case(iti[sgmt_idx] // sgmt.length, oti[sgmt_idx])
                    for sgmt_dir in iter(Direction):
                        port_bus = self.get_blockpin(port.name, subblock, dont_create = dont_create)
                        if port_bus is None:
                            continue
                        if port.direction.is_input:
                            sgmt_bus = self.get_segment_input(sgmt,
                                    Orientation.compose(orientation.dimension.perpendicular, sgmt_dir),
                                    section, dont_create = dont_create)
                            if sgmt_bus is None:
                                continue
                            self.connect(sgmt_bus[track_idx], port_bus[port_idx])
                        else:
                            sgmt_bus = self.get_segment_output(sgmt,
                                    Orientation.compose(orientation.dimension.perpendicular, sgmt_dir),
                                    dont_create = dont_create)
                            if sgmt_bus is None:
                                continue
                            self.connect(port_bus[port_idx], sgmt_bus[track_idx])
                    ni = port.direction.case(iti, oti)[sgmt_idx] + istep    # next index
                    if istep > 1 and ni >= imax:
                        ni += 1
                    port.direction.case(iti, oti)[sgmt_idx] = ni % imax
 
    @classmethod
    def new(cls, block, orientation, position = None, *, identifier = None, name = None):
        """Create a new module for building."""
        key = cls._cbox_key(block, orientation, position, identifier)
        _0, orientation, position, _1 = key
        name = name or 'cbox_{}_x{}y{}{}{}'.format(block.name, position.x, position.y, orientation.name[0],
                ('_' + identifier) if identifier is not None else '')
        return Module(name,
                ports = OrderedDict(),
                conn_graph = MemOptUserConnGraph(),
                allow_multisource = True,
                module_class = ModuleClass.connection_box,
                key = key)

# ----------------------------------------------------------------------------
# -- Switch Box Key ----------------------------------------------------------
# ----------------------------------------------------------------------------
class _SwitchBoxKey(namedtuple('_SwitchBoxKey', 'corner identifier')):
    """Connection box key.

    Args:
        corner (`Corner`): 
        identifier (:obj:`str`): Unique identifier to differentiate switch boxes for the same corner
    """
    pass

# ----------------------------------------------------------------------------
# -- Switch Box Builder ------------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchBoxBuilder(_BaseRoutingBoxBuilder):
    """Switch box builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    # == internal API ========================================================
    @classmethod
    def _segment_relative_position(self, sbox_corner, segment, segment_ori, section = 0):
        if not (0 <= section <= segment.length):
            raise PRGAAPIError("Section '{}' does not exist in segment '{}'"
                    .format(section, segment))
        x, y = None, None
        if segment_ori.is_east:
            x = -section + sbox_corner.dotx(Dimension.x).case(1, 0)
            y = sbox_corner.dotx(Dimension.y).case(0, -1)
        elif segment_ori.is_west:
            x = section + sbox_corner.dotx(Dimension.x).case(0, -1)
            y = sbox_corner.dotx(Dimension.y).case(0, -1)
        elif segment_ori.is_north:
            x = sbox_corner.dotx(Dimension.x).case(0, -1)
            y = -section + sbox_corner.dotx(Dimension.y).case(1, 0)
        elif segment_ori.is_south:
            x = sbox_corner.dotx(Dimension.x).case(0, -1)
            y = section + sbox_corner.dotx(Dimension.y).case(0, -1)
        if x is None:
            raise PRGAAPIError("Invalid segment orientation: {}".format(segment_ori))
        return Position(x, y)

    @classmethod
    def _sbox_key(cls, corner, identifier = None):
        return _SwitchBoxKey(corner, identifier)

    def _add_cboxout(self, node):
        """Add and connect a cboxout input."""
        if node.segment_type.is_sboxin_cboxout and node in self.ports:
            node = node.convert(SegmentType.sboxin_cboxout2)
        if node in self.ports:
            raise PRGAInternalError("'{}' already added to {}".format(node, self._module))
        sboxout = node.convert(SegmentType.sboxout)
        sink = self.ports.get(sboxout)
        if sink is None:
            raise PRGAInternalError("{} does not have output '{}'".format(self._module, sboxout))
        port = ModuleUtils.create_port(self._module, self._node_name(node), node.prototype.width,
                PortDirection.input_, key = node)
        self.connect(port, sink)
        return port

    def _connect_tracks(self,
            isgmt, iori, isec, idx,
            osgmt, oori, osec, odx,
            dont_create = False):
        input_ = self.get_segment_input(isgmt, iori, isec, dont_create = dont_create)
        output = self.get_segment_output(osgmt, oori, osec, dont_create = dont_create)
        if input_ is not None and output is not None:
            self.connect(input_[idx], output[odx])

    def _fill_wilton(self, output_orientation, segments,
            drive_at_crosspoints, crosspoints_only, exclude_input_orientations, dont_create):
        # 1. normal output tracks
        if not crosspoints_only:
            # output tracks
            tracks = [(sgmt, i) for sgmt in segments for i in range(sgmt.width)]
            o_balanced = 0
            # generate connections
            for iori in iter(Orientation):  # input orientation
                if iori in (output_orientation.opposite, Orientation.auto):     # no U-turn
                    continue
                elif iori in exclude_input_orientations:                        # manually excluded orientations
                    continue
                elif iori is output_orientation:                                # straight connections
                    for sgmt in segments:
                        input_ = self.get_segment_input(sgmt, iori, sgmt.length, dont_create = dont_create)
                        output = self.get_segment_output(sgmt, output_orientation, 0, dont_create = dont_create)
                        if input_ is not None and output is not None:
                            self.connect(input_, output)
                    continue
                # input tracks
                # ending wires: do rotation
                rotation = 1
                if (iori, output_orientation) in ((Orientation.west, Orientation.north),
                        (Orientation.south, Orientation.east)):
                    rotation = -1
                # enumerate connections
                for i, (isgmt, idx) in enumerate(tracks):
                    osgmt, odx = tracks[(i + rotation + len(tracks)) % len(tracks)]
                    self._connect_tracks(isgmt, iori, isgmt.length, idx,
                            osgmt, output_orientation, 0, odx, dont_create)
                # passing wires: do balance
                for isgmt in segments:
                    for isec, idx in product(range(1, isgmt.length), range(isgmt.width)):
                        osgmt, odx = tracks[o_balanced]
                        o_balanced = (o_balanced + 1) % len(tracks)
                        self._connect_tracks(isgmt, iori, isec, idx,
                                osgmt, output_orientation, 0, odx, dont_create)
        # 2. crosspoints
        if drive_at_crosspoints:
            # output tracks
            tracks = [(sgmt, section, i) for sgmt in segments for section in range(1, sgmt.length)
                    for i in range(sgmt.width)]
            o = 0
            # generate connections
            for iori in iter(Orientation):  # input orientation
                if iori in (output_orientation, output_orientation.opposite, Orientation.auto):
                    continue
                elif iori in exclude_input_orientations:
                    continue
                # input tracks: ending wires first
                for isgmt in segments:
                    for idx in range(isgmt.width):
                        osgmt, osec, odx = tracks[o]
                        o = (o + 1) % len(tracks)
                        self._connect_tracks(isgmt, iori, isgmt.length, idx,
                                osgmt, output_orientation, osec, odx, dont_create)
                # passing wires next
                for isgmt in segments:
                    for isec, idx in product(range(1, isgmt.length), range(isgmt.width)):
                        osgmt, osec, odx = tracks[o]
                        o = (o + 1) % len(tracks)
                        self._connect_tracks(isgmt, iori, isec, idx,
                                osgmt, output_orientation, osec, odx, dont_create)

    def _fill_cycle_free(self, output_orientation, segments, 
            drive_at_crosspoints, crosspoints_only, exclude_input_orientations, dont_create):
        # tracks
        tracks = []
        for sgmt_idx, sgmt in enumerate(segments):
            tracks.extend( (sgmt, i) for i in range(sgmt.width) )
        # logical class offsets
        lco = {
                Orientation.east: 0,
                Orientation.south: -1,
                Orientation.west: -2,
                Orientation.north: -3,
                }
        # generate connections
        for iori in iter(Orientation):  # input orientation
            if iori in (output_orientation.opposite, Orientation.auto):     # no U-turn
                continue
            elif iori in exclude_input_orientations:                        # exclude some orientations manually
                continue
            elif iori is output_orientation:                                # straight connections
                for sgmt in segments:
                    input_ = self.get_segment_input(sgmt, iori, sgmt.length, dont_create = dont_create)
                    output = self.get_segment_output(sgmt, output_orientation, 0, dont_create = dont_create)
                    if input_ is not None and output is not None:
                        self.connect(input_, output)
                continue
            # turns
            cycle_break_turn = ((output_orientation.is_east and iori.is_north) or
                    (output_orientation.is_south and iori.is_west))
            # iti: input track index
            # isgmt: input segment
            # isi: index in the input segment
            for iti, (isgmt, isi) in enumerate(tracks):
                ilc = (iti + lco[iori] + len(tracks)) % len(tracks)                         # input logical class
                olc = (ilc + (1 if cycle_break_turn else 0) + len(tracks)) % len(tracks)    # output logical class
                for isec in range(isgmt.length):
                    input_ = self.get_segment_input(isgmt, iori, isec + 1, dont_create = dont_create)
                    if input_ is None:
                        continue
                    elif olc < ilc or (olc == ilc and cycle_break_turn):
                        continue
                    oti = (olc - lco[output_orientation] + len(tracks)) % len(tracks)       # output track index
                    osgmt, osi = tracks[oti]
                    for osec in range(1 if crosspoints_only else 0,
                            osgmt.length if drive_at_crosspoints else 1):
                        output = self.get_segment_output(osgmt, output_orientation, osec, dont_create = dont_create)
                        if output is None:
                            continue
                        self.connect(input_[isi], output[osi])
                    olc = (olc + 1) % len(tracks)

    def _fill_span_limited(self, output_orientation, segments,
            drive_at_crosspoints, crosspoints_only, exclude_input_orientations, dont_create, max_span):
        _logger.info("Filling switch box '{}' with pattern: span_limited. max_span = {}"
                .format(self._module, max_span))
        oori = output_orientation       # short alias
        # tracks: sgmt, i, section
        tracks = []
        for sgmt in segments:
            for i, section in product(range(sgmt.width), range(sgmt.length)):
                tracks.append( (sgmt, i, section) )
        channel_width = len(tracks)
        # generate connections
        for iori in iter(Orientation):  # input orientation
            if iori in (oori.opposite, Orientation.auto):     # no U-turn
                continue
            elif iori in exclude_input_orientations:                        # exclude user-chosen input orientations
                continue
            for i in range(channel_width - 1):
                # i = iori.direction.case(i, channel_width - 1 - i)
                # o = oori.direction.case(i + 1, channel_width - 2 - i)
                o = i + 1
                isgmt, idx, isection = tracks[i]
                osgmt, odx, osection = tracks[o]
                # validate that the current track won't break our span limitation
                if i // max_span != (i + isgmt.length - 1 - isection) // max_span:
                    raise PRGAInternalError("Unable to limit span because track #{} ({}[{}]) reaches beyond limit"
                            .format(i, isgmt.name, idx))
                # make sure we don't hop on a long track that may break our span limitation
                if i // max_span != (o + osgmt.length - 1 - osection) // max_span:
                    continue
                if (osection == 0 and crosspoints_only) or (osection > 0 and not drive_at_crosspoints):
                    continue
                self._connect_tracks(isgmt, iori, isection + 1, idx,
                        osgmt, oori, osection, odx, dont_create)

    # == high-level API ======================================================
    def get_segment_input(self, segment, orientation, section = None, *,
            dont_create = False, segment_type = SegmentType.sboxin_regular):
        """Get the segment input to this switch box.

        Args:
            segment (`Segment`): Prototype of the segment
            orientation (`Orientation`): Orientation of the segment
            section (:obj:`int`): Section of the segment
            dont_create (:obj:`bool`): If set, return ``None`` when the requested segment input is not already created
                instead of create it
            segment_type (`SegmentType`): For internal use only
        """
        section = uno(section, segment.length)
        node = SegmentID(self._segment_relative_position(self._module.key.corner, segment, orientation, section),
                segment, orientation, segment_type)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        segment.width, PortDirection.input_, key = node)

    def get_segment_output(self, segment, orientation, section = 0, *, dont_create = False):
        """Get or create the segment output from this switch box.

        Args:
            segment (`Segment`): Prototype of the segment
            orientation (`Orientation`): Orientation of the segment
            section (:obj:`int`): Section of the segment
            dont_create (:obj:`bool`): If set, return ``None`` when the requested segment output is not already created
                instead of create it
        """
        node = SegmentID(self._segment_relative_position(self._module.key.corner, segment, orientation, section),
                segment, orientation, SegmentType.sboxout)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        segment.width, PortDirection.output, key = node)

    def fill(self, output_orientation, *,
            segments = None, drive_at_crosspoints = False, crosspoints_only = False,
            exclude_input_orientations = tuple(), dont_create = False,
            pattern = SwitchBoxPattern.span_limited):
        """Create switches implementing a cycle-free variation of the Wilton switch box.

        Args:
            output_orientation (`Orientation`):

        Keyword Arguments:
            segments (:obj:`Sequence` [:obj:`Segment` ] or :obj:`Mapping` [:obj:`Hashable`, :obj:`Segment` ]): If not
                set, segments from the context are used
            drive_at_crosspoints (:obj:`bool`): If set, outputs are generated driving non-zero sections of long
                segments
            crosspoints_only (:obj:`bool`): If set, outputs driving the first section of segments are not generated
            exclude_input_orientations (:obj:`Container` [`Orientation` ]): Exclude segments in the given orientations
            dont_create (:obj:`bool`): If set, connections are made only between already created nodes
            pattern (`SwitchBoxPattern`): Switch box pattern
        """
        # sort by length (descending order)
        if segments is None:
            segments = tuple(itervalues(self._context.segments))
        elif isinstance(segments, Mapping):
            segments = tuple(itervalues(segments))
        # implement switch box pattern
        if pattern.is_wilton:
            self._fill_wilton(output_orientation, segments, drive_at_crosspoints, crosspoints_only,
                    exclude_input_orientations, dont_create)
        elif pattern.is_cycle_free:
            self._fill_cycle_free(output_orientation, segments, drive_at_crosspoints, crosspoints_only,
                    exclude_input_orientations, dont_create)
        elif pattern.is_span_limited:
            channel_width = sum(sgmt.width * sgmt.length for sgmt in segments)
            max_span = pattern.max_span
            if max_span is None:
                max_span = channel_width
            elif not 0 < max_span <= channel_width:
                raise PRGAInternalError("Invalid max span: {}".format(max_span))
            self._fill_span_limited(output_orientation, segments, drive_at_crosspoints, crosspoints_only,
                    exclude_input_orientations, dont_create, max_span) 
        else:
            raise NotImplementedError("Unsupported/Unimplemented switch box pattern: {}".format(pattern))

    @classmethod
    def new(cls, corner, identifier = None, name = None):
        """Create a new module for building."""
        key = cls._sbox_key(corner, identifier)
        name = name or 'sbox_{}{}'.format(corner.case("ne", "nw", "se", "sw"),
                ('_' + identifier) if identifier is not None else '')
        return Module(name,
                ports = OrderedDict(),
                conn_graph = MemOptUserConnGraph(),
                allow_multisource = True,
                module_class = ModuleClass.switch_box,
                key = key)
