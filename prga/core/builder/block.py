# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseBuilder, MemOptUserConnGraph
from ..common import ModuleClass, NetClass, Position, Orientation, ModuleView
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...util import Object, uno
from ...exception import PRGAAPIError, PRGAInternalError

from collections import OrderedDict

__all__ = ['ClusterBuilder', 'LogicBlockBuilder', 'IOBlockBuilder']

# ----------------------------------------------------------------------------
# -- Base Builder for Cluster-like Modules -----------------------------------
# ----------------------------------------------------------------------------
class _BaseClusterLikeBuilder(BaseBuilder):
    """Base class for cluster-like module builders.

    Args:
        context (`Context`): The context of the builder
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

    def connect(self, sources, sinks, *, fully = False, pack_patterns = None, **kwargs):
        """Connect ``sources`` to ``sinks``."""
        if not pack_patterns:
            NetUtils.connect(sources, sinks, fully = fully, **kwargs)
        else:
            NetUtils.connect(sources, sinks, fully = fully, pack_patterns = pack_patterns, **kwargs)

    def instantiate(self, model, name, *, vpr_num_pb = 1, **kwargs):
        """Instantiate ``model`` and add it into the module."""
        if vpr_num_pb == 1:
            return ModuleUtils.instantiate(self._module, model, name, **kwargs)
        else:
            return tuple(ModuleUtils.instantiate(self._module, model, '{}_i{}'.format(name, i),
                key = (name, i), vpr_num_pb = vpr_num_pb, **kwargs) for i in range(vpr_num_pb))

# ----------------------------------------------------------------------------
# -- ClusterBuilder ----------------------------------------------------------
# ----------------------------------------------------------------------------
class ClusterBuilder(_BaseClusterLikeBuilder):
    """Cluster builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    def create_clock(self, name, **kwargs):
        """Create and add a clock input port to the cluster.

        Args:
            name (:obj:`str`): Name of this clock
        """
        return self._set_clock(ModuleUtils.create_port(self._module, name, 1, PortDirection.input_, is_clock = True,
            **kwargs))

    def create_input(self, name, width, **kwargs):
        """Create and add a non-clock input port to the cluster.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in the port
        """
        return ModuleUtils.create_port(self._module, name, width, PortDirection.input_, **kwargs)

    def create_output(self, name, width, **kwargs):
        """Create and add a non-clock output port to the cluster.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in the port
        """
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output, **kwargs)

    @classmethod
    def new(cls, name, **kwargs):
        """Create a new module for building."""
        return Module(name,
                view = ModuleView.user,
                conn_graph = MemOptUserConnGraph(),
                allow_multisource = True,
                module_class = ModuleClass.cluster,
                clock = None,
                **kwargs)

# ----------------------------------------------------------------------------
# -- IO Block Builder --------------------------------------------------------
# ----------------------------------------------------------------------------
class IOBlockBuilder(_BaseClusterLikeBuilder):
    """IO block builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    def create_global(self, global_, orientation = None, *, name = None, **kwargs):
        """Create and add an input port that is connected to a global wire ``global_``.

        Args:
            global_ (`Global`): The global wire this port is connected to
            orientation (`Orientation`): Orientation of this port

        Keyword Args:
            name (:obj:`str`): Name of this port. If not given, the name of the global wire is used
        """
        port = ModuleUtils.create_port(self._module, name or global_.name, global_.width, PortDirection.input_,
                is_clock = global_.is_clock, orientation = orientation, position = Position(0, 0), global_ = global_,
                **kwargs)
        if global_.is_clock:
            self._set_clock(port)
        return port
    
    def create_input(self, name, width, orientation = None, **kwargs):
        """Create and add a non-global input port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
        """
        return ModuleUtils.create_port(self._module, name, width, PortDirection.input_,
                position = Position(0, 0), orientation = orientation, **kwargs)
    
    def create_output(self, name, width, orientation = None, **kwargs):
        """Create and add a non-global output port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
        """
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output,
                position = Position(0, 0), orientation = orientation, **kwargs)

    @classmethod
    def new(cls, name, capacity, *, disallow_segments_passthru = False, **kwargs):
        """Create a new module for building."""
        return Module(name,
                view = ModuleView.user,
                conn_graph = MemOptUserConnGraph(),
                allow_multisource = True,
                module_class = ModuleClass.io_block,
                clock = None,
                capacity = capacity,
                width = 1,
                height = 1,
                disallow_segments_passthru = disallow_segments_passthru,
                **kwargs)

# ----------------------------------------------------------------------------
# -- Logic Block Builder -----------------------------------------------------
# ----------------------------------------------------------------------------
class LogicBlockBuilder(_BaseClusterLikeBuilder):
    """Logic block builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    @classmethod
    def _resolve_orientation_and_position(cls, block, orientation, position):
        """Resolve orientation and position."""
        if orientation is None:
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

    def create_global(self, global_, orientation, position = None, *, name = None, **kwargs):
        """Create and add an input port that is connected to a global wire ``global_``.

        Args:
            global_ (`Global`): The global wire this port is connected to
            orientation (`Orientation`): Orientation of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of this port

        Keyword Args:
            name (:obj:`str`): Name of this port. If not given, the name of the global wire is used
        """
        orientation, position = self._resolve_orientation_and_position(self._module, orientation, position)
        port = ModuleUtils.create_port(self._module, name or global_.name, global_.width, PortDirection.input_,
                is_clock = global_.is_clock, orientation = orientation, position = position, global_ = global_,
                **kwargs)
        if global_.is_clock:
            self._set_clock(port)
        return port
    
    def create_input(self, name, width, orientation, position = None, *, vpr_equivalent_pins = False, **kwargs):
        """Create and add a non-global input port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of this port
        """
        orientation, position = self._resolve_orientation_and_position(self._module, orientation, position)
        if vpr_equivalent_pins:
            return ModuleUtils.create_port(self._module, name, width, PortDirection.input_,
                    orientation = orientation, position = position, vpr_equivalent_pins = True, **kwargs)
        else:
            return ModuleUtils.create_port(self._module, name, width, PortDirection.input_,
                    orientation = orientation, position = position, **kwargs)
    
    def create_output(self, name, width, orientation, position = None, **kwargs):
        """Create and add a non-global output port to this block.

        Args:
            name (:obj:`str`): name of the created port
            width (:obj:`int`): width of the created port
            orientation (`Orientation`): orientation of this port
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of this port
        """
        orientation, position = self._resolve_orientation_and_position(self._module, orientation, position)
        return ModuleUtils.create_port(self._module, name, width, PortDirection.output,
                orientation = orientation, position = position, **kwargs)

    @classmethod
    def new(cls, name, width, height, *, disallow_segments_passthru = False, **kwargs):
        """Create a new module for building."""
        return Module(name,
                view = ModuleView.user,
                conn_graph = MemOptUserConnGraph(),
                allow_multisource = True,
                module_class = ModuleClass.logic_block,
                clock = None,
                capacity = 1,
                width = width,
                height = height,
                disallow_segments_passthru = disallow_segments_passthru,
                **kwargs)
