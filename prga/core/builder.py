# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import (ModuleClass, NetClass, Position, Orientation, Corner, Dimension,
        SegmentType, SegmentID, BlockPinID)
from ..netlist.net.common import PortDirection
from ..netlist.net.util import NetUtils
from ..netlist.module.module import Module
from ..netlist.module.util import ModuleUtils
from ..util import Object, uno
from ..exception import PRGAAPIError

from abc import abstractmethod
from collections import OrderedDict, namedtuple
from copy import copy

__all__ = ['PrimitiveBuilder', 'ClusterBuilder', 'IOBlockBuilder', 'LogicBlockBuilder',
        'ConnectionBoxBuilder', 'SwitchBoxBuilder', 'ArrayBuilder']

# ----------------------------------------------------------------------------
# -- Base Builder for All Modules --------------------------------------------
# ----------------------------------------------------------------------------
class _BaseBuilder(Object):
    """Base class for all module builders.

    Args:
        module (`AbstractModule`): The module to be built
    """

    __slots__ = ['_module']
    def __init__(self, module):
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
            elif segment_ori.is_west:
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
        return corner, identifier

    # == high-level API ======================================================
    def get_segment_input(self, segment, orientation, section = None, dont_create = False):
        """Get the segment input to this switch box.

        Args:
            segment (`Segment`): Prototype of the segment
            orientation (`Orientation`): Orientation of the segment
            section (:obj:`int`): Section of the segment
            dont_create (:obj:`bool`): If set, return ``None`` when the requested segment input is not already created
                instead of create it
        """
        section = uno(section, segment.length)
        corner, _ = self._module.key
        node = SegmentID(self._segment_relative_position(corner, segment, orientation, section),
                segment, orientation, SegmentType.sboxin_regular)
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
        corner, _ = self._module.key
        node = SegmentID(self._segment_relative_position(corner, segment, orientation, section),
                segment, orientation, SegmentType.sboxout)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        segment.width, PortDirection.output, key = node)

    @classmethod
    def new(cls, corner, identifier = None, name = None):
        """Create a new module for building."""
        key = cls._sbox_key(corner, identifier)
        name = name or 'sbox_{}{}'.format(corner, ('_' + identifier) if identifier is not None else '')
        return Module(name,
                ports = OrderedDict(),
                allow_multisource = True,
                module_class = ModuleClass.switch_box,
                key = key)
