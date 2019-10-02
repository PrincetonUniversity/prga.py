# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import BaseModule
from prga.arch.module.instance import AbstractInstance
from prga.arch.array.common import ChannelCoverage
from prga.arch.array.module import AbstractArrayElement
from prga.arch.array.instance import ArrayElementInstance, SwitchBoxInstance
from prga.util import Object, ReadonlyMappingProxy
from prga.exception import PRGAInternalError

from collections import OrderedDict
from itertools import product, chain

__all__ = ['Array']

# ----------------------------------------------------------------------------
# -- Grid Instances Proxy ----------------------------------------------------
# ----------------------------------------------------------------------------
class _GridInstancesProxy(Object, Mapping):
    """Helper class for `Array.element_instances` and `Array.sbox_instances` properties.
    
    We're abusing Python's list indexing mechanism here. When an array covers the routing channel to the south or west
    of itself, it may contain switch boxes whose positions are like \(-1, y\) or \(x, -1\). In Python, indexing a
    list with -1 returns the last element in the list. Therefore, we store the southmost row (westmost column) at the
    end of the list of switch box rows (columns).
    """

    __slots__ = ['array', 'module_class']
    def __init__(self, array, module_class):
        super(_GridInstancesProxy, self).__init__()
        self.array = array
        self.module_class = module_class

    def __getitem__(self, position):
        try:
            x, y = position
        except ValueError:
            raise KeyError(position)
        if not (isinstance(x, int) and isinstance(y, int) and
                self.module_class.case(switch_box = self.array.covers_sbox(position),
                    tile = self.array.covers_tile(position))):
            raise KeyError(position)
        instance = self.module_class.case(switch_box = self.array._sbox_grid,
                tile = self.array._element_grid)[x][y]
        if isinstance(instance, AbstractInstance):
            return instance
        else:
            raise KeyError(position)

    def __iter__(self):
        if self.module_class.is_switch_box:
            for x, y in product(range(-1, self.array.width), range(-1, self.array.height)):
                instance = self.array._sbox_grid[x][y]
                if isinstance(instance, AbstractInstance):
                    yield Position(x, y)
        else:
            for x, y in product(range(self.array.width), range(self.array.height)):
                instance = self.array._element_grid[x][y]
                if isinstance(instance, AbstractInstance):
                    yield Position(x, y)

    def __len__(self):
        return sum(1 for _ in self.__iter__())

# ----------------------------------------------------------------------------
# -- Array Instances Proxy ---------------------------------------------------
# ----------------------------------------------------------------------------
class _ArrayInstancesProxy(Object, MutableMapping):
    """Helper class for `Array._instances` property."""
    
    __slots__ = ['array']
    def __init__(self, array):
        super(_ArrayInstancesProxy, self).__init__()
        self.array = array

    def __getitem__(self, key):
        try:
            module_class, (x, y) = key
        except ValueError:
            try:
                return self.array.nongrid_instances[key]
            except KeyError:
                raise KeyError(key)
        try:
            if module_class is ModuleClass.switch_box:
                return self.array.sbox_instances[x, y]
            elif module_class is ModuleClass.tile:
                return self.array.element_instances[x, y]
            else:
                raise KeyError(key)
        except KeyError:
            raise KeyError(key)

    def __setitem__(self, key, value):
        self.array._nongrid_instances[key] = value

    def __delitem__(self, key):
        raise PRGAInternalError("Cannot delete from instance mapping")

    def __iter__(self):
        for x, y in product(range(-1, self.array.width), range(-1, self.array.height)):
            if (x, y) in self.array.element_instances:
                yield ModuleClass.tile, (x, y)
            if (x, y) in self.array.sbox_instances:
                yield ModuleClass.switch_box, (x, y)
        for key in self.array.nongrid_instances:
            yield key

    def __len__(self):
        return sum(1 for _ in self.__iter__())

# ----------------------------------------------------------------------------
# -- Array -------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Array(BaseModule, AbstractArrayElement):
    """An array.

    Args:
        name (:obj:`str`): Name of the array
        width (:obj:`int`): Width of the array
        height (:obj:`int`): Height of the array
        coverage (`ChannelCoverage`): Coverage of the adjacent channels surrouding this array
    """

    __slots__ = ['_width', '_height', '_coverage', '_ports', '_sbox_grid', '_element_grid', '_nongrid_instances']
    def __init__(self, name, width, height, coverage = ChannelCoverage()):
        super(Array, self).__init__(name)
        self._width = width
        self._height = height
        self._coverage = coverage
        self._ports = OrderedDict()
        self._sbox_grid = [[None for _0 in range(height + 1)] for _1 in range(width + 1)]
        self._element_grid = [[None for _0 in range(height)] for _1 in range(width)]
        self._nongrid_instances = OrderedDict()

    # == internal API ========================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def _instances(self):
        return _ArrayInstancesProxy(self)

    # == low-level API =======================================================
    @property
    def element_instances(self):
        """:obj:`Mapping` [:obj:`tuple` [:obj:`int`, :obj:`int` ], `ArrayElementInstance` ]: A mapping from tile
        positions to array element instances."""
        return _GridInstancesProxy(self, ModuleClass.tile)

    @property
    def sbox_instances(self):
        """:obj:`Mapping` [:obj:`tuple` [:obj:`int`, :obj:`int` ], `ArrayElementInstance` ]: A mapping from tile
        positions to switch box instances."""
        return _GridInstancesProxy(self, ModuleClass.switch_box)

    @property
    def nongrid_instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `AbstractInstance` ]: A mapping from some hashable key to instances
        not part of the grid."""
        return ReadonlyMappingProxy(self._nongrid_instances)

    def instantiate_element(self, element, position):
        """Instantiate tile or array ``element`` and anchor its \(0, 0\) position to ``position`` in this array.

        Args:
            element (`AbstractArrayElement`):
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
        """
        position = Position(*position)
        # 1. check if the placement fits in the array or conflicts with any existing placements
        for x, y in product(range(-1, element.width), range(-1, element.height)):
            pos_in_elem = Position(x, y)
            pos_in_array = position + pos_in_elem
            if element.covers_tile(pos_in_elem):
                if not self.covers_tile(pos_in_array):
                    raise PRGAInternalError("Array element '{}' does not fit in array '{}' at {}"
                            .format(element, self, position))
                elif self.get_root_element(pos_in_array) is not None:
                    raise PRGAInternalError("Conflicting tile at {} when instantiating array element '{}' at {}"
                            .format(pos_in_array, element, position))
            if element.covers_sbox(pos_in_elem):
                if not self.covers_sbox(pos_in_array):
                    raise PRGAInternalError("Array element '{}' does not fit in array '{}' at {}"
                            .format(element, self, position))
                elif (self.sbox_instances.get(pos_in_array, None) is not None or
                        self.get_root_element_for_sbox(pos_in_array) is not None):
                    raise PRGAInternalError("Conflicting switch box at {} when instantiating array element '{}' at {}"
                            .format(pos_in_array, element, position))
        # 2. instantiate and add placeholders
        instance = ArrayElementInstance(self, element, position)
        self._element_grid[position.x][position.y] = instance
        for x, y in product(range(-1, element.width), range(-1, element.height)):
            pos_in_elem = Position(x, y)
            pos_in_array = position + pos_in_elem
            if element.covers_tile(pos_in_elem) and (x != 0 or y != 0):
                self._element_grid[pos_in_array.x][pos_in_array.y] = pos_in_elem
            if element.covers_sbox(pos_in_elem):
                self._sbox_grid[pos_in_array.x][pos_in_array.y] = pos_in_elem
        return instance

    def instantiate_sbox(self, box, position):
        """Instantiate switch box ``box``at ``position`` in this array.
        
        Args:
            box (`SwitchBox`):
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
        """
        position = Position(*position)
        # 1. check if the placement fits in the array or conflicts with any existing placements
        if not self.covers_sbox(position):
            raise PRGAInternalError("Switch box '{}' does not fit in array '{}' at {}"
                    .format(box, self, position))
        elif position in self.sbox_instances:
            raise PRGAInternalError("Conflicting switch box at {} when instantiating switch box '{}' in array {}"
                    .format(position, box, self))
        elif self.get_root_element_for_sbox(position) is not None:
            raise PRGAInternalError("Conflicting tile at {} when instantiating switch box '{}' in array {}"
                    .format(position, box, self))
        # 2. instantiate
        instance = SwitchBoxInstance(self, box, position)
        self._sbox_grid[position.x][position.y] = instance
        return instance

    def get_root_element(self, position):
        """Get the root element that, occupies tile ``position`` even if not anchored at ``position``.
        
        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
        """
        if not self.covers_tile(position):
            return None
        x, y = position
        instance = self._element_grid[x][y]
        try:
            xx, yy = instance
        except (ValueError, TypeError):
            return instance
        return self._element_grid[x - xx][y - yy]

    def get_root_element_for_sbox(self, position):
        """Get the root element that occupies the switch box tile ``position``.
        
        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
        """
        if not self.covers_sbox(position):
            return None
        x, y = position
        instance = self._sbox_grid[x][y]
        try:
            xx, yy = instance
        except (ValueError, TypeError):
            return instance
        return self._element_grid[x - xx][y - yy]

    # -- implementing properties/methods required by superclass --------------
    @property
    def width(self):
        return self._width

    @property
    def height(self):
        return self._height

    @property
    def channel_coverage(self):
        return self._coverage

    @property
    def module_class(self):
        return ModuleClass.array
