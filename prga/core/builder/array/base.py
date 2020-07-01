# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..base import BaseBuilder
from ....netlist.net.common import PortDirection
from ....netlist.net.util import NetUtils
from ....netlist.module.util import ModuleUtils
from ....exception import PRGAInternalError
from ....util import Object

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
    def _no_channel(cls, module, position, dim):
        x, y = position
        if dim.is_x:
            if ((x <= 0 and module.edge.west) or
                    (x >= module.width - 1 and module.edge.east) or
                    (y >= module.height - 1 and module.edge.north) or
                    (y < 0 and module.edge.south)):
                return True
        elif dim.is_y:
            if ((y <= 0 and module.edge.south) or
                    (y >= module.height - 1 and module.edge.north) or
                    (x >= module.width - 1 and module.edge.east) or
                    (x < 0 and module.edge.west)):
                return True
        else:
            raise PRGAInternalError("Unkonwn dimension: {}".format(dim))
        if module.module_class.is_tile:
            if module.disallow_segments_passthru:
                return dim.case(
                        x = 0 <= x < module.width and 0 <= y < module.height - 1,
                        y = 0 <= x < module.width - 1 and 0 <= y < module.height)
            else:
                return False
        elif module.module_class.is_array:
            instance = module._instances.get_root(position)
            if instance is not None:
                return cls._no_channel(instance.model, position - instance.key, dim)
            return False
        else:
            raise PRGAInternalError("Unknown module class: {}".format(module.module_class))

    @classmethod
    def _get_or_create_global_input(cls, module, global_):
        source = module.ports.get(global_.name)
        if source is not None:
            if getattr(source, "global_", None) is not global_:
                raise PRGAInternalError("'{}' is not driving global wire '{}'"
                        .format(source, global_.name))
        else:
            source = ModuleUtils.create_port(module, global_.name, global_.width, PortDirection.input_,
                    is_clock = global_.is_clock, global_ = global_)
        return source

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
