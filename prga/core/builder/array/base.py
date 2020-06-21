# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..base import BaseBuilder
from ...common import Dimension, Position, Orientation, Corner
from ....netlist.net.common import PortDirection
from ....netlist.net.util import NetUtils
from ....netlist.module.util import ModuleUtils
from ....netlist.module.instance import Instance
from ....exception import PRGAInternalError
from ....util import Object

from abc import abstractmethod, abstractproperty

__all__ = []

# ----------------------------------------------------------------------------
# -- Base Array Builder ------------------------------------------------------
# ----------------------------------------------------------------------------
class BaseArrayBuilder(BaseBuilder):
    """Base builder for tiles and arrays.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    @classmethod
    def _node_name(cls, node):
        """Generate the name for ``node``."""
        if node.node_type.is_block:
            return 'bp_{}{}{}{}i{}_{}'.format(
                'x' if node.position.x >= 0 else 'u', abs(node.position.x),
                'y' if node.position.y >= 0 else 'v', abs(node.position.y),
                node.subtile,
                node.prototype.name)
        elif node.node_type.is_bridge:
            prefix = node.bridge_type.case(
                    regular_input = 'bi',
                    regular_output = 'bo',
                    cboxout = 'cu',
                    cboxout2 = 'cv')
            return '{}_{}{}{}{}{}_{}'.format(prefix,
                'x' if node.position.x >= 0 else 'u', abs(node.position.x),
                'y' if node.position.y >= 0 else 'v', abs(node.position.y),
                node.orientation.name[0],
                node.prototype.name)
        elif node.node_type.is_segment:
            raise PRGAInternalError("No segment nodes expected in arrays") 
        else:
            raise PRGAInternalError("Unknown node type: {}".format(node))

    @classmethod
    def _no_channel(cls, module, position, ori):
        x, y = position
        if ori.dimension.is_x:
            if ((x <= 0 and module.edge.west) or
                    (x >= module.width - 1 and module.edge.west) or
                    (y >= module.height - 1 and module.edge.north) or
                    (y < 0 and module.edge.south)):
                return True
        elif ori.dimension.is_y:
            if ((y <= 0 and module.edge.south) or
                    (y >= module.height - 1 and module.edge.north) or
                    (x >= module.width - 1 and module.edge.east) or
                    (x < 0 and module.edge.west)):
                return True
        else:
            raise PRGAInternalError("Unkonwn orientation: {}".format(ori))
        if module.module_class.is_tile:
            if module.disallow_segments_passthru:
                return ori.dimension.case(
                        x = 0 <= x < module.width and 0 <= y < module.height - 1,
                        y = 0 <= x < module.width - 1 and 0 <= y < module.height)
            else:
                return False
        elif module.module_class.is_array:
            instance = module._instances.get_root(position)
            if instance is not None:
                if module.module_class.is_leaf_array:
                    return cls._no_channel(instance.model, position - instance.key[0], ori)
                else:
                    return cls._no_channel(instance.model, position - instance.key, ori)
            return False
        else:
            raise PRGAInternalError("Unknown module class: {}".format(module.module_class))

    @classmethod
    def _no_channel_for_switchbox(cls, module, position, corner, ori, output = False):
        x = ori.case(default = False, east = output, west = not output)
        if corner.dotx(Dimension.x).is_inc and x:
            corrected += (1, 0)
        elif corner.dotx(Dimension.x).is_dec and not x:
            corrected -= (1, 0)

        y = ori.case(default = False, north = output, south = not output)
        if corner.dotx(Dimension.y).is_inc and y:
            corrected += (0, 1)
        elif corner.dotx(Dimension.x).is_dec and not y:
            corrected -= (0, 1)

        return cls._no_channel(module, corrected, ori)

    @classmethod
    def _instance_position(cls, instance):
        return sum(iter(i.key[0] if i.parent.module_class.is_leaf_array else i.key
                for i in instance.hierarchy), Position(0, 0))

    @classmethod
    def _get_or_create_global_input(cls, module, global_):
        source = module.ports.get(global_.name)
        if source is not None:
            if not hasattr(source, 'global_') or source.global_ is not global_:
                raise PRGAInternalError("'{}' is not driving global wire '{}'"
                        .format(source, global_.name))
        else:
            source = ModuleUtils.create_port(array, global_.name, global_.width, PortDirection.input_,
                    is_clock = global_.is_clock, global_ = global_)
        return source

    @classmethod
    def _expose_routing_node(cls, pin, *, create_port = False):
        """Recursively expose a hierarchical routing node.

        Args:
            pin (`Pin`): A (hierarchical) pin of a routing node

        Keyword Args:
            create_port (:obj:`bool`): If set to ``True``, a port is create at the parent module of ``pin``

        Returns:
            `Pin` or `Port`:
        """
        port = pin.model
        for instance in pin.instance.hierarchy[:-1]:
            port = cls.__expose_routing_node(instance.pins[port.key])
        if create_port:
            return cls.__expose_routing_node(pin.instance.hierarchy[-1].pins[port.key])
        else:
            return pin.instance.hierarchy[-1].pins[port.key]

    # == low-level API =======================================================

    # == high-level API ======================================================
    def connect(self, sources, sinks):
        """Connect ``sources`` to ``sinks``."""
        NetUtils.connect(sources, sinks)

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
        """:obj:`Mapping` [:obj:`Hashable`, `Instance` ]: Proxy to ``module.instances``."""
        return self._module.instances

    @abstractmethod
    def auto_connect(self, *, is_top = False):
        """Automatically connect submodules.

        Keyword Args:
            is_top (:obj:`bool`): If set, the array is treated as the top-level array. This affects if ports for
                global wires are created. By default, the builder refers to the setting in the context in which it is
                created to see if this array is the top
        """
        raise NotImplementedError
