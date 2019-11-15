# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Orientation, Position
from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import RegularInstance
from prga.arch.primitive.common import PrimitiveClass
from prga.arch.block.port import (IOBlockGlobalInputPort, IOBlockInputPort, IOBlockOutputPort,
        IOBlockExternalInputPort, IOBlockExternalOutputPort,
        LogicBlockGlobalInputPort, LogicBlockInputPort, LogicBlockOutputPort)
from prga.arch.block.cluster import ClusterLike
from prga.exception import PRGAInternalError
from prga.util import uno

from collections import OrderedDict

__all__ = ['IOBlock', 'LogicBlock']

# ----------------------------------------------------------------------------
# -- Base Class for Blocks ---------------------------------------------------
# ----------------------------------------------------------------------------
class BaseBlock(ClusterLike):
    """Base class for blocks."""

    __slots__ = ['_ports', '_instances']
    def __init__(self, name):
        super(BaseBlock, self).__init__(name)
        self._ports = OrderedDict()
        self._instances = OrderedDict()

    # == internal API ========================================================
    def _validate_orientation_and_position(self, orientation, position):
        """Validate if the given ``orientation`` and ``position`` is on the edge of a block."""
        if position is None and not (self.width == 1 and self.height == 1):
            raise PRGAInternalError("Argument 'position' is required because the size of block '{}' is {}x{}"
                    .format(self, self.width, self.height))
        position = Position(*uno(position, (0, 0)))
        if position.x < 0 or position.x >= self.width or position.y < 0 or position.y >= self.height:
            raise PRGAInternalError("{} is not within block '{}'"
                    .format(position, self))
        elif orientation is Orientation.auto:
            if self.module_class.is_io_block:
                return orientation, position
            else:
                raise PRGAInternalError("'Orientation.auto' can only ued on IO blocks")
        elif orientation.case(north = position.y != self.height - 1,
                east = position.x != self.width - 1,
                south = position.y != 0,
                west = position.x != 0):
            raise PRGAInternalError("{} is not on the {} edge of block '{}'"
                    .format(position, orientation.name, self))
        return orientation, position

    # == high-level API ======================================================
    @property
    def width(self):
        """:obj:`int`: Width of this block in the number of tiles."""
        return 1

    @property
    def height(self):
        """:obj:`int`: Height of this block in the number of tiles."""
        return 1

    @property
    def capacity(self):
        """:obj:`int`: Number of block instances in the same tile."""
        return 1

# ----------------------------------------------------------------------------
# -- IO Block ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class IOBlock(BaseBlock):
    """IO block.

    Args:
        name (:obj:`str`): Name of this IO block
        io_primitive (`Inpad`, `Outpad` or `Iopad`): IO primitive to instantiate in this block
        capacity (:obj:`int`): Number of IO blocks per tile
    """

    __slots__ = ['_capacity']
    def __init__(self, name, io_primitive, capacity):
        super(IOBlock, self).__init__(name)
        instance = RegularInstance(self, io_primitive, 'io')
        self._add_instance(instance)
        if io_primitive.primitive_class in (PrimitiveClass.inpad, PrimitiveClass.iopad):
            i = IOBlockExternalInputPort(self, 'exti', 1)
            self._add_port(i)
            instance.pins['inpad'].physical_cp = i
        if io_primitive.primitive_class in (PrimitiveClass.outpad, PrimitiveClass.iopad):
            o = IOBlockExternalOutputPort(self, 'exto', 1)
            self._add_port(o)
            instance.pins['outpad'].physical_cp = o
        if io_primitive.primitive_class.is_iopad:
            oe = IOBlockExternalOutputPort(self, 'extoe', 1)
            self._add_port(oe)
            instance.logical_pins['cfg_d'].physical_cp = oe
        self._capacity = capacity

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.io_block

    # == high-level API ======================================================
    @property
    def capacity(self):
        return self._capacity

    def create_global(self, global_, orientation = Orientation.auto, name = None):
        """Create and add a global input port to this block.

        Args:
            global_ (`Global`): The global wire this port is connected to
            orientation (`Orientation`): Orientation of this port
            name (:obj:`str`): Name of this port
        """
        orientation, _ = self._validate_orientation_and_position(orientation, Position(0, 0))
        port = IOBlockGlobalInputPort(self, global_, orientation, name)
        return self._add_port(port)

    def create_input(self, name, width, orientation = Orientation.auto):
        """Create and add a non-global input port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
        """
        orientation, _ = self._validate_orientation_and_position(orientation, Position(0, 0))
        port = IOBlockInputPort(self, name, width, orientation)
        return self._add_port(port)

    def create_output(self, name, width, orientation = Orientation.auto):
        """Create and add an output port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
        """
        orientation, _ = self._validate_orientation_and_position(orientation, Position(0, 0))
        port = IOBlockOutputPort(self, name, width, orientation)
        return self._add_port(port)

# ----------------------------------------------------------------------------
# -- Logic Block -------------------------------------------------------------
# ----------------------------------------------------------------------------
class LogicBlock(BaseBlock):
    """Logic block.

    Args:
        name (:obj:`str`): Name of this logic block
        width (:obj:`int`): Width of this block
        height (:obj:`int`): Height of this block
    """

    __slots__ = ['_width', '_height']
    def __init__(self, name, width = 1, height = 1):
        super(LogicBlock, self).__init__(name)
        self._width = width
        self._height = height

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.logic_block

    # == high-level API ======================================================
    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    def create_global(self, global_, orientation, name = None, position = None):
        """Create and add a global input port to this block.

        Args:
            global_ (`Global`): The global wire this port is connected to
            orientation (`Orientation`): Orientation of this port
            name (:obj:`str`): Name of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of the port in the block. Omittable if the
                size of the block is 1x1
        """
        orientation, position = self._validate_orientation_and_position(orientation, position)
        port = LogicBlockGlobalInputPort(self, global_, orientation, name, position)
        return self._add_port(port)

    def create_input(self, name, width, orientation, position = None):
        """Create and add a non-global input port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of the port in the block. Omittable if the
                size of the block is 1x1
        """
        orientation, position = self._validate_orientation_and_position(orientation, position)
        port = LogicBlockInputPort(self, name, width, orientation, position)
        return self._add_port(port)

    def create_output(self, name, width, orientation, position = None):
        """Create and add an output port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of the port in the block. Omittable if the
                size of the block is 1x1
        """
        orientation, position = self._validate_orientation_and_position(orientation, position)
        port = LogicBlockOutputPort(self, name, width, orientation, position)
        return self._add_port(port)
