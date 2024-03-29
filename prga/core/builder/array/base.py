# -*- encoding: ascii -*-

from ..base import BaseBuilder
from ....netlist import PortDirection, ModuleUtils, NetUtils
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
            raise PRGAInternalError("Unknown dimension: {}".format(dim))
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
