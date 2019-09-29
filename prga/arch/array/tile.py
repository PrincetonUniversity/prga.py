# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Dimension
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import BaseModule
from prga.arch.block.block import AbstractBlock
from prga.arch.array.common import ChannelCoverage
from prga.arch.array.module import AbstractArrayElement
from prga.arch.array.instance import BlockInstance, ConnectionBoxInstance
from prga.util import ReadonlyMappingProxy
from prga.exception import PRGAInternalError

from collections import OrderedDict

__all__ = ['Tile']

# ----------------------------------------------------------------------------
# -- Tile --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Tile(BaseModule, AbstractArrayElement):
    """A tile in an array.

    Args:
        name (:obj:`str`): Name of the tile
        block (`AbstractBlock`): The block to be instantiated in this tile
    """

    __slots__ = ['_ports', '_instances']
    def __init__(self, name, block):
        super(Tile, self).__init__(name)
        self._ports = OrderedDict()
        self._instances = OrderedDict()
        for subblock in range(block.capacity):
            self._add_instance(BlockInstance(self, block, subblock))

    # == low-level API =======================================================
    @property
    def block_instances(self):
        """:obj:`Mapping` [:obj:`int`, `BlockInstance` ]: A mapping from sub-block IDs to block instances."""
        return ReadonlyMappingProxy(self.all_instances,
                lambda kv: kv[1].module_class.is_io_block or kv[1].module_class.is_logic_block)

    @property
    def cbox_instances(self):
        """:obj:`Mapping` [:obj:`tuple` [`Position`, `Dimension` ], `ConnectionBoxInstance` ]: A mapping from position
        and the orientation of the channel relative to the position, to connection box instances."""
        return ReadonlyMappingProxy(self.all_instances, lambda kv: kv[1].module_class.is_connection_box)

    @property
    def block(self):
        """`AbstractBlock`: The block instantiated in this tile."""
        return self.all_instances[0].model

    def instantiate_cbox(self, box, orientation, position = None):
        """Instantiate connection box in this tile."""
        orientation, position = self.block._validate_orientation_and_position(orientation, position)
        dim = orientation.switch(Dimension.x, Dimension.y, Dimension.x, Dimension.y)
        if box.dimension is not dim:
            raise PRGAInternalError("Connection box '{}' is not {}, conflicting with orientation '{}'"
                    .format(box, dim.switch('horizontal', 'vertical'), orientation.name))
        return self._add_instance(ConnectionBoxInstance(self, box, position, orientation))

    # -- implementing properties/methods required by superclass --------------
    @property
    def width(self):
        return self.block.width

    @property
    def height(self):
        return self.block.height

    @property
    def channel_coverage(self):
        return ChannelCoverage()

    @property
    def module_class(self):
        return ModuleClass.tile
