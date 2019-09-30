# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.module.common import ModuleClass
from prga.arch.module.instance import BaseInstance
from prga.arch.routing.module import BaseRoutingInstance

__all__ = ['BlockInstance', 'ConnectionBoxInstance', 'SwitchBoxInstance', 'ArrayElementInstance']

# ----------------------------------------------------------------------------
# -- Block Instance ----------------------------------------------------------
# ----------------------------------------------------------------------------
class BlockInstance(BaseInstance):
    """Block instances in a tile.

    Args:
        parent (`Tile`): Parent tile of this instance
        model (`AbstractBlock`): Model of this instance
        subblock (:obj:`int`): Sub-block ID of this instance in the tile
    """

    __slots__ = ['_subblock']
    def __init__(self, parent, model, subblock = 0):
        super(BlockInstance, self).__init__(parent, model)
        self._subblock = subblock

    # == low-level API =======================================================
    @property
    def subblock(self):
        """:obj:`int`: Sub-block ID of this instance."""
        return self._subblock

    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return 'blkinst' + ('' if self.model.capacity == 1 else ('_' + str(self.subblock)))

    @property
    def key(self):
        return self.subblock

# ----------------------------------------------------------------------------
# -- Connection Box Instance -------------------------------------------------
# ----------------------------------------------------------------------------
class ConnectionBoxInstance(BaseRoutingInstance):
    """Instance of connection boxes.

    Args:
        parent (`Tile`): Parent module of this instance
        model (`ConnectionBox`): Model of this instance
        position (`Position`): Position of this instance in the parent module
        orientation (`Orientation`): On which side of a tile is this instance
    """

    __slots__ = ['_orientation']
    def __init__(self, parent, model, position, orientation):
        super(ConnectionBoxInstance, self).__init__(parent, model, position)
        self._orientation = orientation

    # == low-level API =======================================================
    @property
    def orientation(self):
        """`Orientation`: On which side of a tile is this instance."""
        return self._orientation

    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return 'cbinst_{}{}{}{}{}'.format(
                    'x' if self.position.x >= 0 else 'u', self.position.x,
                    'y' if self.position.y >= 0 else 'v', self.position.y,
                    self.orientation.name[0])

    @property
    def key(self):
        return (self.position, self.orientation)

# ----------------------------------------------------------------------------
# -- Switch Box Instance -----------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchBoxInstance(BaseRoutingInstance):
    """Instance of switch boxes.

    Args:
        parent (`Array`): Parent module of this instance
        model (`SwitchBox`): Model of this instance
        position (`Position`): Position of this instance in the parent module
    """

    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return 'sbinst_{}{}{}{}'.format(
                    'x' if self.position.x >= 0 else 'u', self.position.x,
                    'y' if self.position.y >= 0 else 'v', self.position.y)

    @property
    def key(self):
        return (ModuleClass.switch_box, self.position)

# ----------------------------------------------------------------------------
# -- Array Element Instance --------------------------------------------------
# ----------------------------------------------------------------------------
class ArrayElementInstance(BaseRoutingInstance):
    """Instance of array elements.

    Args:
        parent (`Array`): Parent module of this instance
        model (`AbstractArrayElement`): Model of this instance
        position (`Position`): Position of this instance in the parent module
    """

    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return 'tileinst_{}{}{}{}'.format(
                    'x' if self.position.x >= 0 else 'u', self.position.x,
                    'y' if self.position.y >= 0 else 'v', self.position.y)

    @property
    def key(self):
        return (ModuleClass.tile, self.position)
