# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import (ModuleClass, NetClass, Position, Orientation, Corner, Dimension, Direction, Subtile,
        SegmentType, SegmentID, BlockPinID, BlockFCValue)
from ..netlist.net.common import PortDirection
from ..netlist.net.util import NetUtils
from ..netlist.module.module import Module
from ..netlist.module.util import ModuleUtils
from ..util import Object, uno
from ..exception import PRGAAPIError

from abc import abstractmethod
from collections import OrderedDict, namedtuple
from copy import copy
from itertools import product

__all__ = ['PrimitiveBuilder', 'ClusterBuilder', 'IOBlockBuilder', 'LogicBlockBuilder',
        'ConnectionBoxBuilder', 'SwitchBoxBuilder', 'ArrayEdgeSettings', 'ArrayBuilder']

# ----------------------------------------------------------------------------
# -- Base Builder for All Modules --------------------------------------------
# ----------------------------------------------------------------------------
class _BaseBuilder(Object):
    """Base class for all module builders.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    __slots__ = ['_context', '_module']
    def __init__(self, context, module):
        self._context = context
        self._module = module

    @property
    def module(self):
        """`AbstractModule`: The module being built."""
        return self._module

    @property
    def ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Port` ]: Proxy to ``module.ports``."""
        return self._module.ports

    def commit(self):
        """Commit the module."""
        ModuleUtils.elaborate(self._module)
        return self._module

# ----------------------------------------------------------------------------
# -- Base Builder for Cluster-like Modules -----------------------------------
# ----------------------------------------------------------------------------
class _BaseClusterLikeBuilder(_BaseBuilder):
    """Base class for cluster-like module builders.

    Args:
        module (`AbstractModule`): The module to be built
    """

    def _set_clock(self, port):
        """Set ``port`` as the clock of the module."""
        if self._module.clock is not None:
            raise PRGAAPIError("Cluster '{}' already has a clock ('{}')"
                    .format(self._module, self._module.clock))
        self._module.clock = port
        return port

    @property
    def clock(self):
        """`Port`: Clock of the cluster."""
        return self._module.clock

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstances` ]: Proxy to ``module.instances``."""
        return self._module.instances

    def connect(self, sources, sinks, fully = False, pack_patterns = tuple()):
        """Connect ``sources`` to ``sinks``."""
        if not pack_patterns:
            NetUtils.connect(sources, sinks, fully)
        else:
            NetUtils.connect(sources, sinks, fully, pack_patterns = pack_patterns)

    def instantiate(self, model, name):
        """Instantiate ``model`` and add it into the module."""
        return ModuleUtils.instantiate(self._module, model, name)

# ----------------------------------------------------------------------------
# -- Cluster Builder ---------------------------------------------------------
# ----------------------------------------------------------------------------
class ClusterBuilder(_BaseClusterLikeBuilder):
    """Cluster builder.

    Args:
        module (`AbstractModule`): The module to be built
    """

    def create_clock(self, name):
        """Create and add a clock input port to the cluster.

        Args:
            name (:obj:`str`): Name of this clock
        """
        return self._set_clock(ModuleUtils.create_port(self._module, name, 1, PortDirection.input_, is_clock = True))

    def create_input(self, name, width):
        """Create and add a non-clock input port to the cluster.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in the port
        """
        return ModuleUtils.create_port(self._module, name, width, PortDirection.input_)

    def create_output(self, name, width):
        """Create and add a non-clock output port to the cluster.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in the port
        """
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output)

    @classmethod
    def new(cls, name):
        """Create a new module for building."""
        return Module(name,
                ports = OrderedDict(),
                instances = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.cluster,
                clock = None)

# ----------------------------------------------------------------------------
# -- IO Block Builder --------------------------------------------------------
# ----------------------------------------------------------------------------
class IOBlockBuilder(_BaseClusterLikeBuilder):
    """IO block builder.

    Args:
        module (`AbstractModule`): The module to be built
    """

    def create_global(self, global_, orientation = Orientation.auto, name = None):
        """Create and add an input port that is connected to a global wire ``global_``.

        Args:
            global_ (`Global`): The global wire this port is connected to
            orientation (`Orientation`): Orientation of this port
            name (:obj:`str`): Name of this port. If not given, the name of the global wire is used
        """
        port = ModuleUtils.create_port(self._module, name or global_.name, global_.width, PortDirection.input_,
                is_clock = global_.is_clock, orientation = orientation, position = Position(0, 0), global_ = global_)
        if global_.is_clock:
            self._set_clock(port)
        return port
    
    def create_input(self, name, width, orientation = Orientation.auto):
        """Create and add a non-global input port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
        """
        return ModuleUtils.create_port(self._module, name, width, PortDirection.input_,
                position = Position(0, 0), orientation = orientation)
    
    def create_output(self, name, width, orientation = Orientation.auto):
        """Create and add a non-global output port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
        """
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output,
                position = Position(0, 0), orientation = orientation)

    @classmethod
    def new(cls, name, capacity):
        """Create a new module for building."""
        return Module(name,
                ports = OrderedDict(),
                instances = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.io_block,
                clock = None,
                capacity = capacity)

# ----------------------------------------------------------------------------
# -- Logic Block Builder -----------------------------------------------------
# ----------------------------------------------------------------------------
class LogicBlockBuilder(_BaseClusterLikeBuilder):
    """Logic block builder.

    Args:
        module (`AbstractModule`): The module to be built
    """

    @classmethod
    def _resolve_orientation_and_position(cls, block, orientation, position):
        """Resolve orientation and position."""
        if orientation.is_auto:
            raise PRGAAPIError("Cannot resolve orientation based on position")
        # 1. try to resolve position based on orientation
        elif position is None:
            if orientation.is_north and block.width == 1:
                return orientation, Position(0, block.height - 1)
            elif orientation.is_east and block.height == 1:
                return orientation, Position(block.width - 1, 0)
            elif orientation.is_south and block.width == 1:
                return orientation, Position(0, 0)
            elif orientation.is_west and block.height == 1:
                return orientation, Position(0, 0)
            else:
                raise PRGAAPIError(("Cannot resolve position based on orientation because "
                    "there are multiple positions on the {} side of block {} ({}x{})")
                        .format(orientation.name, block.name, block.width, block.height))
        # 2. validate orientation and position
        else:
            position = Position(*position)
            if not (0 <= position.x < block.width and 0 <= position.y < block.height):
                raise PRGAInternalError("{} is not within block '{}'"
                        .format(position, block))
            elif orientation.case(north = position.y != block.height - 1,
                    east = position.x != block.width - 1,
                    south = position.y != 0,
                    west = position.x != 0):
                raise PRGAInternalError("{} is not on the {} edge of block '{}'"
                        .format(position, orientation.name, block))
            return orientation, position

    def create_global(self, global_, orientation, position = None, name = None):
        """Create and add an input port that is connected to a global wire ``global_``.

        Args:
            global_ (`Global`): The global wire this port is connected to
            orientation (`Orientation`): Orientation of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of this port
            name (:obj:`str`): Name of this port. If not given, the name of the global wire is used
        """
        orientation, position = self._resolve_orientation_and_position(self._module, orientation, position)
        port = ModuleUtils.create_port(self._module, name or global_.name, global_.width, PortDirection.input_,
                is_clock = global_.is_clock, orientation = orientation, position = position, global_ = global_)
        if global_.is_clock:
            self._set_clock(port)
        return port
    
    def create_input(self, name, width, orientation, position = None):
        """Create and add a non-global input port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of this port
        """
        orientation, position = self._resolve_orientation_and_position(self._module, orientation, position)
        return ModuleUtils.create_port(self._module, name, width, PortDirection.input_,
                orientation = orientation, position = position)
    
    def create_output(self, name, width, orientation, position = None):
        """Create and add a non-global output port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of this port
        """
        orientation, position = self._resolve_orientation_and_position(self._module, orientation, position)
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output,
                orientation = orientation, position = position)

    @classmethod
    def new(cls, name, width, height):
        """Create a new module for building."""
        return Module(name,
                ports = OrderedDict(),
                instances = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.logic_block,
                clock = None,
                width = width,
                height = height)

# ----------------------------------------------------------------------------
# -- Base Builder for Routing Boxes and Arrays -------------------------------
# ----------------------------------------------------------------------------
class _BaseRoutableBuilder(_BaseBuilder):
    """Base class for routing box and array builders.

    Args:
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
                    array_regular = 'as',
                    array_cboxout = 'co',
                    array_cboxout2 = 'co2')
            return '{}_{}_{}{}{}{}{}'.format(
                    prefix, node.prototype.name,
                    'x' if node.position.x >= 0 else 'u', abs(node.position.x),
                    'y' if node.position.y >= 0 else 'v', abs(node.position.y),
                    node.orientation.name[0])

    # == high-level API ======================================================
    def connect(self, sources, sinks, fully = False):
        """Connect ``sources`` to ``sinks``."""
        NetUtils.connect(sources, sinks, fully)

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
class ConnectionBoxBuilder(_BaseRoutableBuilder):
    """Connection box builder.

    Args:
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

    # == high-level API ======================================================
    def get_segment_input(self, segment, orientation, section = 0, dont_create = False):
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

    def get_segment_output(self, segment, orientation, dont_create = False):
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

    def get_blockpin(self, port, subblock = 0, dont_create = False):
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

    def fill(self, fc, segments = None, dont_create = False):
        """Add port-segment connections using FC values.

        Args:
            fc (`BlockFCValue`): A `BlockFCValue` or arguments that can be used to construct a `BlockFCValue`, for
                example, an :obj:`int`, or a :obj:`tuple` of :obj:`int` and overrides. Refer to `BlockFCValue` for
                more details
            segments (:obj:`Sequence` [:obj:`Segment` ] or :obj:`Mapping` [:obj:`Hashable`, :obj:`Segment` ]): If not
                set, segments from the context is used
            dont_create (:obj:`bool`): If set, connections are made only between already created nodes
        """
        fc = BlockFCValue._construct(fc)
        if segments is None:
            segments = tuple(itervalues(self._context.segments))
        elif isinstance(segments, Mapping):
            segments = tuple(itervalues(segments))
        block, orientation, position, _ = self._module.key
        # start generation
        iti = [0 for _ in segments]
        oti = [0 for _ in segments]
        for port in itervalues(block.ports):
            if not (port.position == position and port.orientation in (orientation, Orientation.auto)):
                continue
            for sgmt_idx, sgmt in enumerate(segments):
                nc = fc.port_fc(port, sgmt, port.direction.is_input)  # number of connections
                if nc == 0:
                    continue
                imax = port.direction.case(sgmt.length * sgmt.width, sgmt.width)
                istep = max(1, imax // nc)                  # index step
                for _, port_idx, subblock in product(range(nc), range(len(port)),
                        range(getattr(block, "capacity", 1))):
                    section = port.direction.case(iti[sgmt_idx] % sgmt.length, 0)
                    track_idx = port.direction.case(iti[sgmt_idx] // sgmt.length, oti[sgmt_idx])
                    for sgmt_dir in iter(Direction):
                        port_bus = self.get_blockpin(port.name, subblock, dont_create)
                        if port_bus is None:
                            continue
                        if port.direction.is_input:
                            sgmt_bus = self.get_segment_input(sgmt,
                                    Orientation.compose(orientation.dimension.perpendicular, sgmt_dir),
                                    section, dont_create)
                            if sgmt_bus is None:
                                continue
                            self.connect(sgmt_bus[track_idx], port_bus[port_idx])
                        else:
                            sgmt_bus = self.get_segment_output(sgmt,
                                    Orientation.compose(orientation.dimension.perpendicular, sgmt_dir),
                                    dont_create)
                            if sgmt_bus is None:
                                continue
                            self.connect(port_bus[port_idx], sgmt_bus[track_idx])
                    ni = port.direction.case(iti, oti)[sgmt_idx] + istep    # next index
                    if istep > 1 and ni >= imax:
                        ni += 1
                    port.direction.case(iti, oti)[sgmt_idx] = ni % imax
 
    @classmethod
    def new(cls, block, orientation, position = None, identifier = None, name = None):
        """Create a new module for building."""
        key = cls._cbox_key(block, orientation, position, identifier)
        _0, orientation, position, _1 = key
        name = name or 'cbox_{}_x{}y{}{}{}'.format(block.name, position.x, position.y, orientation.name[0],
                ('_' + identifier) if identifier is not None else '')
        return Module(name,
                ports = OrderedDict(),
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
class SwitchBoxBuilder(_BaseRoutableBuilder):
    """Connection box builder.

    Args:
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
        return x, y

    @classmethod
    def _sbox_key(cls, corner, identifier = None):
        return _SwitchBoxKey(corner, identifier)

    # == high-level API ======================================================
    def get_segment_input(self, segment, orientation, section = None, dont_create = False,
            segment_type = SegmentType.sboxin_regular):
        """Get the segment input to this switch box.

        Args:
            segment (`Segment`): Prototype of the segment
            orientation (`Orientation`): Orientation of the segment
            section (:obj:`int`): Section of the segment
            dont_create (:obj:`bool`): If set, return ``None`` when the requested segment input is not already created
                instead of create it
            segment_type (`SegmentType`): Which type of segment input needed. Valid types are:
                `SegmentType.sboxin_regular`, `SegmentType.sboxin_cboxout` and `SegmentType.sboxin_cboxout2`
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

    def get_segment_output(self, segment, orientation, section = 0, dont_create = False):
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

    def fill(self, output_orientation, segments = None, drive_at_crosspoints = False,
            crosspoints_only = False, exclude_input_orientations = tuple(), dont_create = False):
        """Create switches implementing a cycle-free variation of the Wilton switch box.

        Args:
            output_orientation (`Orientation`):
            segments (:obj:`Sequence` [:obj:`Segment` ] or :obj:`Mapping` [:obj:`Hashable`, :obj:`Segment` ]): If not
                set, segments from the context are used
            drive_at_crosspoints (:obj:`bool`): If set, outputs are generated driving non-zero sections of long
                segments
            crosspoints_only (:obj:`bool`): If set, outputs driving the first section of segments are not generated
            exclude_input_orientations (:obj:`Container` [`Orientation` ]): Exclude segments in the given orientations
            dont_create (:obj:`bool`): If set, connections are made only between already created nodes
        """
        # sort by length (descending order)
        if segments is None:
            segments = tuple(sorted(itervalues(self._context.segments), key = lambda x: x.length, reverse = True))
        elif isinstance(segments, Mapping):
            segments = tuple(sorted(itervalues(segments), key = lambda x: x.length, reverse = True))
        else:
            segments = tuple(sorted(segments, key = lambda x: x.length, reverse = True))
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
                    for section in range(1 if crosspoints_only else 0,
                            sgmt.length if drive_at_crosspoints else 1):
                        input_ = self.get_segment_input(sgmt, iori, sgmt.length - section, dont_create)
                        output = self.get_segment_output(sgmt, output_orientation, section, dont_create)
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
                    input_ = self.get_segment_input(isgmt, iori, isec + 1, dont_create)
                    if input_ is None:
                        continue
                    elif olc < ilc or (olc == ilc and cycle_break_turn):
                        continue
                    oti = (olc - lco[output_orientation] + len(tracks)) % len(tracks)       # output track index
                    osgmt, osi = tracks[oti]
                    for osec in range(1 if crosspoints_only else 0,
                            osgmt.length if drive_at_crosspoints else 1):
                        output = self.get_segment_output(osgmt, output_orientation, osec, dont_create)
                        if output is None:
                            continue
                        self.connect(input_[isi], output[osi])
                    olc = (olc + 1) % len(tracks)

    @classmethod
    def new(cls, corner, identifier = None, name = None):
        """Create a new module for building."""
        key = cls._sbox_key(corner, identifier)
        name = name or 'sbox_{}{}'.format(corner.case("ne", "nw", "se", "sw"),
                ('_' + identifier) if identifier is not None else '')
        return Module(name,
                ports = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.switch_box,
                key = key)

# ----------------------------------------------------------------------------
# -- Array Instance Mapping --------------------------------------------------
# ----------------------------------------------------------------------------
class _ArrayInstanceMapping(Object, MutableMapping):
    """Helper class for ``Array.instances`` property.

    Args:
        width (:obj:`int`): Width of the array
        height (:obj:`int`): Height of the array
    """

    __slots__ = ['grid']
    def __init__(self, width, height):
        self.grid = tuple(tuple([None] * len(Subtile) for y in range(height)) for x in range(width))

    def __getitem__(self, key):
        try:
            (x, y), subtile = key
        except (ValueError, TypeError):
            raise KeyError(key)
        try:
            tile = self.grid[x][y]
        except (IndexError, TypeError):
            raise KeyError(key)
        if subtile > len(tile) - len(Subtile):
            raise KeyError(key)
        try:
            obj = tile[subtile]
        except (IndexError, TypeError):
            raise KeyError(key)
        if obj is None or isinstance(obj, Position):
            raise KeyError(key)
        return obj

    def __setitem__(self, key, value):
        try:
            (x, y), subtile = key
        except (ValueError, TypeError):
            raise KeyError(key)
        try:
            tile = self.grid[x][y]
        except (IndexError, TypeError):
            raise PRGAInternalError("Unsupported key: {}".format(key))
        if subtile < 0:
            try:
                if tile[subtile] is not None:
                    raise PRGAInternalError("Subtile '{}' of '{}' already occupied"
                            .format(subtile.name, Position(x, y)))
                tile[subtile] = value
            except IndexError:
                raise PRGAInternalError("Unsupported key: {}".format(key))
        else:
            last_subblock = len(tile) - len(Subtile)
            if subtile == last_subblock:
                if tile[last_subblock] is not None:
                    raise PRGAInternalError("Subblock '{}' of '{}' already occupied"
                            .format(subtile, Position(x, y)))
                tile[last_subblock] = value
            elif subtile == last_subblock + 1:
                if tile[last_subblock] is None or isinstance(tile[last_subblock], Position):
                    raise PRGAInternalError("Invalid subblock '{}' placed at subblock {} of '{}'"
                            .format(value, subtile, Position(x, y)))
                tile.insert(last_subblock + 1, value)
            else:
                raise PRGAInternalError("Invalid subblock '{}' placed at subblock {} of '{}'"
                        .format(value, subtile, Position(x, y)))

    def __delitem__(self, key):
        raise PRGAInternalError("Deleting from an array instances mapping is not supported")

    def __len__(self):
        return sum(1 for _ in iter(self))

    def __iter__(self):
        for x, col in enumerate(self.grid):
            for y, tile in enumerate(col):
                pos = Position(x, y)
                for i, instance in enumerate(tile):
                    if instance is None or isinstance(instance, Position):
                        continue
                    if i > len(tile) - len(Subtile):
                        yield pos, Subtile(i - len(tile))
                    else:
                        yield pos, i

    def get_root(self, position, subtile):
        x, y = position
        try:
            tile = self.grid[x][y]
        except (IndexError, TypeError):
            raise PRGAInternalError("Invalid position '{}'".format(Position(x, y)))
        if subtile > len(tile) - len(Subtile):
            raise PRGAInternalError("Invalid subblock: {}".format(subtile))
        obj = tile[subtile]
        if isinstance(obj, Position):
            return self.grid[x - obj.x][y - obj.y][Subtile.center]
        return obj

# ----------------------------------------------------------------------------
# -- Array Edge Settings -----------------------------------------------------
# ----------------------------------------------------------------------------
class ArrayEdgeSettings(namedtuple('ArrayEdgeSettings', 'north east south west')):

    def __new__(cls, default = False, north = None, east = None, south = None, west = None):
        return super(ArrayEdgeSettings, cls).__new__(cls,
                north = north if north is not None else default,
                south = south if south is not None else default,
                east = east if east is not None else default,
                west = west if west is not None else default)

# ----------------------------------------------------------------------------
# -- Array Builder -----------------------------------------------------------
# ----------------------------------------------------------------------------
class ArrayBuilder(_BaseRoutableBuilder):
    """Array builder.

    Args:
        module (`AbstractModule`): The module to be built
    """

    # == low-level API =======================================================
    @classmethod
    def _checklist(cls, model, x, y, exclude_root = False):
        if model.module_class.is_array:
            for i in Subtile:
                if exclude_root and i.is_center and x == 0 and y == 0:
                    continue
                yield i
        elif model.module_class.is_logic_block:
            north = y < model.height - 1
            south = y > 0
            east = x < model.width - 1
            west = x > 0
            if not exclude_root or x != 0 or y != 0:
                yield Subtile.center
            if north:
                yield Subtile.north
                if east:
                    yield Subtile.northeast
                if west:
                    yield Subtile.northwest
            if south:
                yield Subtile.south
                if east:
                    yield Subtile.southeast
                if west:
                    yield Subtile.southwest
            if west:
                yield Subtile.west
            if east:
                yield Subtile.east
        else:
            raise PRGAInternalError("Unsupported module class '{}'".format(model.module_class.name))

    @classmethod
    def _no_channel(cls, model, position, corner, ori):
        # calculate position
        corrected = position
        if corner.dotx(Dimension.x).is_inc and ori.is_west:
            corrected += (1, 0)
        elif corner.dotx(Dimension.x).is_dec and not ori.is_west:
            corrected -= (1, 0)
        if corner.dotx(Dimension.y).is_inc and ori.is_south:
            corrected += (0, 1)
        elif corner.dotx(Dimension.y).is_dec and not ori.is_south:
            corrected -= (0, 1)
        x, y = corrected
        if model.module_class.is_logic_block:
            return ori.dimension.case(0 <= x < model.width and 0 <= y < model.height - 1,
                    0 <= x < model.width - 1 and 0 <= y < model.height)
        elif model.module_class.is_array:
            if 0 <= x < model.width and 0 <= y < model.height:
                instance = model._instances.get_root(corrected, Subtile.center)
                if instance is not None:
                    return cls._no_channel(instance.model, position - instance.key[0], corner, ori)
        return False

    # == high-level API ======================================================
    @property
    def width(self):
        """:obj:`int`: Width of the array."""
        return self._module.width

    @property
    def height(self):
        """:obj:`int`: Height of the array."""
        return self._module.height

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`tuple` [:obj:`tuple` [:obj:`int`, :obj:`int` ], :obj:`int` or `Subtile` ],
            `AbstractInstances` ]: Proxy to ``module.instances``.
            
        The key is composed of the position in the array and the subtile/subblock in the array.
        """
        return self._module.instances

    @classmethod
    def new(cls, name, width, height):
        """Create a new module for building."""
        return Module(name,
                ports = OrderedDict(),
                instances = _ArrayInstanceMapping(width, height),
                coalesce_connections = True,
                module_class = ModuleClass.array,
                width = width,
                height = height)

    def instantiate(self, model, position, name = None):
        """Instantiate ``model`` at the speicified position in the array.

        Args:
            model (`AbstractModule`): A logic/IO block, connection/switch box, or sub array
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position in the array
            name (:obj:`int`): Custom name of the instance
        """
        position = Position(*position)
        # 1. make sure all subtiles are not already occupied
        if model.module_class.is_logic_block or model.module_class.is_array:
            for x, y in product(range(model.width), range(model.height)):
                pos = position + (x, y)
                if pos.x >= self.width or pos.y >= self.height:
                    raise PRGAAPIError("'{}' is not in array '{}' ({} x {})"
                            .format(pos, self._module, self.width, self.height))
                for subtile in self._checklist(model, x, y):
                    root = self._module._instances.get_root(pos, subtile)
                    if root is not None:
                        raise PRGAAPIError("Subtile '{}' of '{}' in array '{}' already occupied by '{}'"
                                .format(subtile.name, pos, self._module, root))
        else:
            subtile = (Subtile.center if model.module_class.is_io_block else
                    model.key.orientation.to_subtile() if model.module_class.is_connection_box else
                    model.key.corner.to_subtile() if model.module_class.is_switch_box else None)
            if subtile is None:
                raise PRGAAPIError("Cannot instantiate '{}' in array '{}'. Unsupported module class: {}"
                        .format(model, self._module, model.module_class.name))
            root = self._module._instances.get_root(position, subtile)
            if root is not None:
                raise PRGAAPIError("Subtile '{}' of '{}' in array '{}' already occupied by '{}'"
                        .format(subtile.name, position, self._module, root))
            if model.module_class.is_connection_box:    # special check when instantiating a connection box
                root = self._module._instances.get_root(position, Subtile.center)
                if root is None:
                    raise PRGAAPIError("Connection box cannot be placed at '{}' in array '{}'"
                            .format(position, self._module))
                rootpos, _ = root.key
                offset = position - rootpos
                if root.model is not model.key.block or offset != model.key.position:
                    raise PRGAAPIError("Connection box cannot be placed at '{}' in array '{}'"
                            .format(position, self._module))
        # 2. instantiation
        if name is None:
            if model.module_class.is_io_block:
                name = "iob_x{}y{}".format(position.x, position.y)
            elif model.module_class.is_logic_block:
                name = "clb_x{}y{}".format(position.x, position.y)
            elif model.module_class.is_array:
                name = "subarray_x{}y{}".format(position.x, position.y)
            elif model.module_class.is_connection_box:
                name = "cb_x{}y{}{}".format(position.x, position.y, model.key.orientation.name[0])
            else:
                name = "sb_x{}y{}{}".format(position.x, position.y,
                        model.key.corner.case('ne', 'nw', 'se', 'sw'))
        if model.module_class.is_io_block:
            if model.capacity == 1:
                ModuleUtils.instantiate(self._module, model, name, key = (position, Subtile.center))
            else:
                for i in range(model.capacity):
                    ModuleUtils.instantiate(self._module, model, name + '_' + str(i), key = (position, i))
        elif model.module_class.is_logic_block or model.module_class.is_array:
            ModuleUtils.instantiate(self._module, model, name, key = (position, Subtile.center))
            for x, y in product(range(model.width), range(model.height)):
                for subtile in self._checklist(model, x, y, True):
                    self._module._instances.grid[x][y][subtile] = Position(x, y)
        elif model.module_class.is_connection_box:
            ModuleUtils.instantiate(self._module, model, name, key = (position, model.key.orientation.to_subtile()))
        elif model.module_class.is_switch_box:
            ModuleUtils.instantiate(self._module, model, name, key = (position, model.key.corner.to_subtile()))

    def connect(self, sources, sinks):
        """Connect ``sources`` to ``sinks``."""
        NetUtils.connect(sources, sinks, coalesced = self._module._coalesce_connections)

    def fill(self,
            default_fc,
            fc_override = None,
            channel_on_edge = ArrayEdgeSettings(True),
            closure_on_edge = ArrayEdgeSettings(False),
            identifier = None):
        """Fill routing boxes into the array being built."""
        fc_override = uno(fc_override, {})
        for x, y in product(range(self._module.width), range(self._module.height)):
            on_edge = ArrayEdgeSettings(
                    north = y == self._module.height - 1,
                    east = x == self._module.width - 1,
                    south = y == 0,
                    west = x == 0)
            next_to_edge = ArrayEdgeSettings(
                    north = y == self._module.height - 2,
                    east = x == self._module.width - 2,
                    south = y == 1,
                    west = x == 1)
            position = Position(x, y)
            # connection boxes
            for ori in Orientation:
                if ori.is_auto:
                    continue
                elif self._module._instances.get_root(position, ori.to_subtile()) is not None:
                    continue
                elif any(on_edge[ori2] and not channel_on_edge[ori2] for ori2 in Orientation
                        if ori2 not in (Orientation.auto, ori.opposite)):
                    continue
                block_instance = self._module._instances.get_root(position, Subtile.center)
                if block_instance is None:
                    continue
                fc = BlockFCValue._construct(fc_override.get(block_instance.model.name, default_fc))
                if block_instance.model.module_class.is_logic_block:
                    cbox_needed = False
                    for port in itervalues(block_instance.model.ports):
                        if port.position != position - block_instance.key[0] or port.orientation != ori:
                            continue
                        elif hasattr(port, 'global_'):
                            continue
                        elif any(fc.port_fc(port, segment) for segment in itervalues(self._context.segments)):
                            cbox_needed = True
                            break
                    if not cbox_needed:
                        continue
                cbox = self._context.get_connection_box(block_instance.model, ori, position - block_instance.key[0],
                        identifier)
                cbox.fill(fc_override.get(block_instance.model.name, default_fc))
                self.instantiate(cbox.commit(), position)
            # switch boxes
            for corner in Corner:
                if self._module._instances.get_root(position, corner.to_subtile()) is not None:
                    continue
                elif any(on_edge[ori] and not channel_on_edge[ori] for ori in corner.decompose()):
                    continue
                # analyze the environment of this switch box (output orientations, excluded inputs, crosspoints, etc.)
                outputs = []                        # orientation, drive_at_crosspoints, crosspoints_only
                sbox_identifier = [identifier] if identifier else []
                # 1. primary output
                primary_output = Orientation[corner.case("south", "east", "west", "north")]
                if not on_edge[primary_output] or channel_on_edge[primary_output]:
                    if on_edge[primary_output.opposite] and closure_on_edge[primary_output.opposite]:
                        outputs.append( (primary_output, True, False) )
                        sbox_identifier.append( "pc" )
                    else:
                        outputs.append( (primary_output, False, False) )
                        sbox_identifier.append( "p" )
                # 2. secondary output
                secondary_output = Orientation[corner.case("west", "south", "north", "east")]
                if (on_edge[primary_output.opposite] and not on_edge[secondary_output] and 
                        closure_on_edge[primary_output.opposite]):
                    if on_edge[secondary_output.opposite] and closure_on_edge[secondary_output.opposite]:
                        outputs.append( (secondary_output, True, False) )
                        sbox_identifier.append( "sc" )
                    else:
                        outputs.append( (secondary_output, False, False) )
                        sbox_identifier.append( "s" )
                # 3. tertiary output
                tertiary_output = primary_output.opposite
                if on_edge[tertiary_output.opposite] and not channel_on_edge[tertiary_output.opposite]:
                    outputs.append( (tertiary_output, True, True) )
                    sbox_identifier.append( "tc" )
                # 4. exclude inputs
                exclude_input_orientations = set(ori for ori in Orientation
                        if not ori.is_auto and self._no_channel(self._module, position, corner, ori))
                for ori in corner.decompose():
                    if next_to_edge[ori] and not channel_on_edge[ori]:
                        exclude_input_orientations.add( ori.opposite )
                    ori = ori.opposite
                    if on_edge[ori] and not channel_on_edge[ori]:
                        exclude_input_orientations.add( ori.opposite )
                if exclude_input_orientations:
                    sbox_identifier.append( "ex_" + "".join(o.name[0] for o in sorted(exclude_input_orientations)) )
                sbox_identifier = "_".join(sbox_identifier)
                sbox = self._context.get_switch_box(corner, sbox_identifier)
                for output, drivex, xo in outputs:
                    sbox.fill(output, drive_at_crosspoints = drivex, crosspoints_only = xo,
                            exclude_input_orientations = exclude_input_orientations)
                self.instantiate(sbox.commit(), position)

    def commit(self):
        return super(ArrayBuilder, self).commit()
