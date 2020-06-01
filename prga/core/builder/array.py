# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseBuilder, MemOptUserConnGraph
from .box import ConnectionBoxBuilder, SwitchBoxBuilder
from ..common import (ModuleClass, Subtile, Position, Orientation, Dimension, Corner, OrientationTuple, SegmentID,
        SegmentType, BlockPinID, BlockPortFCValue, BlockFCValue, Direction, SwitchBoxPattern, ModuleView)
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.util import ModuleUtils
from ...netlist.module.module import Module
from ...util import Object, uno
from ...exception import PRGAInternalError, PRGAAPIError

from collections import OrderedDict
from itertools import product
from abc import abstractproperty, abstractmethod
from copy import deepcopy

__all__ = ['LeafArrayBuilder', 'NonLeafArrayBuilder']

# ----------------------------------------------------------------------------
# -- Leaf Array Instance Mapping ---------------------------------------------
# ----------------------------------------------------------------------------
class _LeafArrayInstanceMapping(Object, MutableMapping):
    """Helper class for ``LeafArray.instances`` property.

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
            try:
                (x, y), subtile = key, Subtile.center
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

    def get_root(self, position, subtile = Subtile.center):
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
# -- Non-Leaf Array Instance Mapping -----------------------------------------
# ----------------------------------------------------------------------------
class NonLeafArrayInstanceMapping(Object, MutableMapping):
    """Helper class for ``NonLeafArray.instances`` property.

    Args:
        width (:obj:`int`): Width of the array
        height (:obj:`int`): Height of the array
    """

    __slots__ = ['grid']
    def __init__(self, width, height):
        self.grid = tuple(list(None for y in range(height)) for x in range(width))

    def __getitem__(self, key):
        try:
            x, y = key
        except (ValueError, TypeError):
            raise KeyError(key)
        try:
            tile = self.grid[x][y]
        except (IndexError, TypeError):
            raise KeyError(key)
        if tile is None or isinstance(tile, Position):
            raise KeyError(key)
        return tile

    def __setitem__(self, key, value):
        try:
            x, y = key
        except (ValueError, TypeError):
            raise KeyError(key)
        try:
            self.grid[x][y] = value
        except (IndexError, TypeError):
            raise PRGAInternalError("Grid location out of range: {}".format(key))

    def __delitem__(self, key):
        raise PRGAInternalError("Deleting from an array instances mapping is not supported")

    def __len__(self):
        return sum(1 for _ in iter(self))

    def __iter__(self):
        for x, col in enumerate(self.grid):
            for y, tile in enumerate(col):
                if tile is None or isinstance(tile, Position):
                    continue
                yield Position(x, y)

    def get_root(self, position):
        x, y = position
        try:
            tile = self.grid[x][y]
        except (IndexError, TypeError):
            raise PRGAInternalError("Invalid position '{}'".format(Position(x, y)))
        if isinstance(tile, Position):
            return self.grid[x - tile.x][y - tile.y]
        return tile

# ----------------------------------------------------------------------------
# -- Base Array Builder ------------------------------------------------------
# ----------------------------------------------------------------------------
class _BaseArrayBuilder(BaseBuilder):
    """Base builder for leaf arrays and non-leaf arrays.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    # == low-level API =======================================================
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
                    array_input = 'ai',
                    array_output = 'ao',
                    array_cboxout = 'xo',
                    array_cboxout2 = 'co2')
            return '{}_{}_{}{}{}{}{}'.format(
                    prefix, node.prototype.name,
                    'x' if node.position.x >= 0 else 'u', abs(node.position.x),
                    'y' if node.position.y >= 0 else 'v', abs(node.position.y),
                    node.orientation.name[0])

    @classmethod
    def _no_channel(cls, model, position, ori):
        x, y = position
        if model.module_class.is_logic_block:
            return ori.dimension.case(0 <= x < model.width and 0 <= y < model.height - 1,
                    0 <= x < model.width - 1 and 0 <= y < model.height)
        elif model.module_class.is_array:
            if ori.dimension.is_x:
                if ((x <= 0 and model.edge.west) or
                        (x >= model.width - 1 and model.edge.east) or
                        (y >= model.height - 1 and model.edge.north) or
                        (y < 0 and model.edge.south)):
                    return True
            else:
                if ((y <= 0 and model.edge.south) or
                        (y >= model.height - 1 and model.edge.north) or
                        (x >= model.width - 1 and model.edge.east) or
                        (x < 0 and model.edge.west)):
                    return True
            if 0 <= x < model.width and 0 <= y < model.height:
                instance = model._instances.get_root(position)
                if instance is not None:
                    if model.module_class.is_leaf_array:
                        return cls._no_channel(instance.model, position - instance.key[0], ori)
                    else:
                        return cls._no_channel(instance.model, position - instance.key, ori)
            return False

    @classmethod
    def _no_channel_for_switchbox(cls, model, position, subtile, ori, output = False):
        # calculate position
        corrected, corner = position, subtile.to_corner()
        if corner.dotx(Dimension.x).is_inc and ori.case(False, output, False, not output):
            corrected += (1, 0)
        elif corner.dotx(Dimension.x).is_dec and ori.case(True, not output, True, output):
            corrected -= (1, 0)
        if corner.dotx(Dimension.y).is_inc and ori.case(output, False, not output, False):
            corrected += (0, 1)
        elif corner.dotx(Dimension.y).is_dec and ori.case(not output, True, output, True):
            corrected -= (0, 1)
        return cls._no_channel(model, corrected, ori)

    @classmethod
    def _instance_position(cls, instance):
        return sum(iter(i.key[0] if i.parent.module_class.is_leaf_array else i.key
                for i in instance.hierarchy), Position(0, 0))

    @classmethod
    def _segment_searchlist(cls, node, position, subtile, width, height, *, forward = False):
        # 1. create a list of all possible position + corner where we may find the source
        searchlist = []
        # 1.1 initial search position
        skip = 0
        try:
            corner = Corner.compose(node.orientation.opposite, subtile.to_orientation())
        except PRGAInternalError:
            corner = subtile.to_corner()
            if not forward:
                if corner.dotx(node.orientation.dimension) is node.orientation.direction:
                    skip = 2
                else:
                    skip = 4
        # 1.2 constants
        paradim, perpdim = node.orientation.dimension, node.orientation.dimension.perpendicular
        sgmt_paradir, preferred_perpdir = node.orientation.direction, corner.dotx(perpdim)
        while True:
            # 1.3 check if the given position + corner is inside the boundary
            if skip:
                skip -= 1
            elif 0 <= position.x < width and 0 <= position.y < height:
                searchlist.append( (position, corner.to_subtile()) )
            # 1.4 check if we've done constructing the search list
            # 1.4.1 section check
            section = node.orientation.case(
                    east = position.x - node.position.x + corner.dotx(Dimension.x).case(1, 0),
                    north = position.y - node.position.y + corner.dotx(Dimension.y).case(1, 0),
                    west = node.position.x - position.x + corner.dotx(Dimension.x).case(0, 1),
                    south = node.position.y - position.y + corner.dotx(Dimension.y).case(1, 0))
            if ((not forward and section < 0) or (forward and section > node.prototype.length)):
                break
            # 1.4.2 boundary check
            if not forward:
                if node.orientation.case(east = position.x < 0, west = position.x >= width,
                        north = position.y < 0, south = position.y >= height):
                    break
            else:
                if node.orientation.case(west = position.x < 0, east = position.x >= width,
                        south = position.y < 0, north = position.y >= height):
                    break
            # 1.5 find the next position + corner where we may find the source
            paradir, perpdir = map(corner.dotx, (paradim, perpdim))
            if perpdir is preferred_perpdir:
                position += perpdim.case(x = (perpdir.case(1, -1), 0), y = (0, perpdir.case(1, -1)))
                corner = Corner.compose(Orientation.compose(paradim, paradir),
                        Orientation.compose(perpdim, perpdir.opposite))
            else:
                corner = Corner.compose(Orientation.compose(paradim, paradir.opposite),
                        Orientation.compose(perpdim, perpdir.opposite))
                if (paradir is sgmt_paradir) == forward:
                    position += paradim.case(x = (paradir.case(1, -1), perpdir.case(1, -1)),
                            y = (perpdir.case(1, -1), paradir.case(1, -1)))
                    corner = Corner.compose(Orientation.compose(paradim, paradir.opposite),
                            Orientation.compose(perpdim, perpdir.opposite))
                else:
                    position += paradim.case(x = (0, perpdir.case(1, -1)), y = (perpdir.case(1, -1), 0))
                    corner = Corner.compose(Orientation.compose(paradim, paradir.opposite),
                            Orientation.compose(perpdim, perpdir.opposite))
        return searchlist

    @classmethod
    def __expose_routable_pin(cls, pin):
        """Expose non-hierarchical ``pin`` as a port and connect them."""
        assert not pin.instance.is_hierarchical
        array = pin.parent
        # which type of pin is this?
        if isinstance(pin.model.key, SegmentID):  # SEGMENT
            port = None
            node = pin.model.key.convert(pin.model.key.segment_type.case(
                sboxout = SegmentType.array_output,
                sboxin_regular = SegmentType.array_input,
                sboxin_cboxout = SegmentType.array_cboxout,
                sboxin_cboxout2 = SegmentType.array_cboxout,
                cboxout = SegmentType.array_cboxout,
                cboxin = SegmentType.array_input,
                array_input = SegmentType.array_input,
                array_output = SegmentType.array_output,
                array_cboxout = SegmentType.array_cboxout,
                array_cboxout2 = SegmentType.array_cboxout,
                ), cls._instance_position(pin.instance))
            while True:
                port = array.ports.get(node)
                if port is None:
                    break
                elif port.direction is pin.model.direction:
                    source, sink = (pin, port) if port.direction.is_output else (port, pin)
                    cur_source = NetUtils.get_source(sink, return_none_if_unconnected = True)
                    if cur_source is None:
                        NetUtils.connect(source, sink)
                        break
                    elif cur_source == source:
                        break
                if port is not None and node.segment_type.is_array_cboxout:
                    node = node.convert(SegmentType.array_cboxout2)
                    continue
                raise PRGAInternalError("'{}' already exposed but not correctly connected".format(pin))
            new_box_key = (pin.instance.key if array.module_class.is_leaf_array else 
                    (pin.instance.key + pin.model.boxkey[0], pin.model.boxkey[1]))
            if port is None:
                port = ModuleUtils.create_port(array, cls._node_name(node),
                        len(pin), pin.model.direction, key = node,
                        boxkey = new_box_key)
                if pin.model.direction.is_input:
                    NetUtils.connect(port, pin)
                else:
                    NetUtils.connect(pin, port)
            elif array.module_class.is_leaf_array and pin.model.key.segment_type.is_sboxin_regular:
                try:
                    old_box_key = port.boxkey
                    oldcorner = old_box_key[1].to_corner()
                except PRGAInternalError:
                    return port
                if node.orientation.is_north:
                    if (old_box_key[0].y > new_box_key[0].y or (old_box_key[0].y == new_box_key[0].y and 
                        oldcorner.dotx(Dimension.y).is_inc)):
                        new_box_key = old_box_key
                elif node.orientation.is_east:
                    if (old_box_key[0].x > new_box_key[0].x or (old_box_key[0].x == new_box_key[0].x and 
                        oldcorner.dotx(Dimension.x).is_inc)):
                        new_box_key = old_box_key
                elif node.orientation.is_south:
                    if (old_box_key[0].y < new_box_key[0].y or (old_box_key[0].y == new_box_key[0].y and 
                        oldcorner.dotx(Dimension.y).is_dec)):
                        new_box_key = old_box_key
                else:
                    if (old_box_key[0].x < new_box_key[0].x or (old_box_key[0].x == new_box_key[0].x and 
                        oldcorner.dotx(Dimension.x).is_dec)):
                        new_box_key = old_box_key
                port.boxkey = new_box_key
            return port
        elif isinstance(pin.model.key, BlockPinID) or pin.model.parent.module_class.is_logic_block:    # BLOCK PIN 
            node = None
            if isinstance(pin.model.key, BlockPinID):
                node = pin.model.key.move(cls._instance_position(pin.instance))
            else:
                node = BlockPinID(cls._instance_position(pin.instance) + pin.model.position, pin.model)
            port = array.ports.get(node, None)
            if port is None:
                port = ModuleUtils.create_port(array, cls._node_name(node), len(pin),
                        pin.model.direction, key = node)
            source, sink = (pin, port) if port.direction.is_output else (port, pin)
            cur_source = NetUtils.get_source(sink, return_none_if_unconnected = True)
            if cur_source is None:
                NetUtils.connect(source, sink)
            elif cur_source != source:
                raise PRGAInternalError("'{}' already exposed but not correctly connected".format(pin))
            return port
        else:
            raise PRGAInternalError("Unknown routing pin: '{}'".format(pin))

    @classmethod
    def _expose_routable_pin(cls, pin, *, create_port = False):
        """Recursively expose a hierarchical ``pin``."""
        port = pin.model
        for instance in pin.instance.hierarchy[:-1]:
            port = cls.__expose_routable_pin(instance.pins[port.key])
        if create_port:
            return cls.__expose_routable_pin(pin.instance.hierarchy[-1].pins[port.key])
        else:
            return pin.instance.hierarchy[-1].pins[port.key]

    @classmethod
    def _get_or_create_global_input(cls, array, global_):
        source = array.ports.get(global_.name)
        if source is not None:
            if not hasattr(source, 'global_') or source.global_ is not global_:
                raise PRGAInternalError("'{}' is not driving global wire '{}'"
                        .format(source, global_.name))
        else:
            source = ModuleUtils.create_port(array, global_.name, global_.width, PortDirection.input_,
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

    @abstractmethod
    def auto_connect(self, *, is_top = False):
        """Automatically connect submodules.

        Keyword Args:
            is_top (:obj:`bool`): If set, the array is treated as the top-level array. This affects if ports for
                global wires are created. By default, the builder refers to the setting in the context in which it is
                created to see if this array is the top
        """
        raise NotImplementedError

    @abstractproperty
    def instances(self):
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Leaf Array Builder ------------------------------------------------------
# ----------------------------------------------------------------------------
class LeafArrayBuilder(_BaseArrayBuilder):
    """Leaf array builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    # == low-level API =======================================================
    @classmethod
    def _block_subtile_checklist(cls, model, x, y, exclude_root = False):
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

    # == high-level API ======================================================
    @classmethod
    def new(cls, name, width, height, *, edge = OrientationTuple(False)):
        """Create a new module for building."""
        return Module(name,
                view = ModuleView.user,
                instances = _LeafArrayInstanceMapping(width, height),
                coalesce_connections = True,
                module_class = ModuleClass.leaf_array,
                width = width,
                height = height,
                edge = edge)

    def instantiate(self, model, position, *, name = None):
        """Instantiate ``model`` at the speicified position in the array.

        Args:
            model (`AbstractModule`): A logic/IO block, or connection/switch box
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position in the array

        Keyword Args:
            name (:obj:`int`): Custom name of the instance
        """
        position = Position(*position)
        # 1. make sure all subtiles are not already occupied
        if model.module_class.is_logic_block:
            for x, y in product(range(model.width), range(model.height)):
                pos = position + (x, y)
                if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
                    raise PRGAAPIError("'{}' is not in leaf array '{}' ({} x {})"
                            .format(pos, self._module, self.width, self.height))
                if pos.x == 0 and self._module.edge.west:
                    raise PRGAAPIError("Logic block '{}' cannot be placed on the west edge of the FPGA"
                            .format(model))
                elif pos.x == self.width - 1 and self._module.edge.east:
                    raise PRGAAPIError("Logic block '{}' cannot be placed on the east east of the FPGA"
                            .format(model))
                if pos.y == 0 and self._module.edge.south:
                    raise PRGAAPIError("Logic block '{}' cannot be placed on the south edge of the FPGA"
                            .format(model))
                elif pos.y == self.height - 1 and self._module.edge.north:
                    raise PRGAAPIError("Logic block '{}' cannot be placed on the north east of the FPGA"
                            .format(model))
                for subtile in self._block_subtile_checklist(model, x, y):
                    root = self._module._instances.get_root(pos, subtile)
                    if root is not None:
                        raise PRGAAPIError("Subtile '{}' of '{}' in leaf array '{}' already occupied by '{}'"
                                .format(subtile.name, pos, self._module, root))
        elif model.module_class.is_io_block:
            if position == (0, 0) and self._module.edge.west and self._module.edge.south:
                raise PRGAAPIError("IO block '{}' cannot be placed on the southwest corner of the FPGA".format(model))
            elif position == (0, self.height - 1) and self._module.edge.west and self._module.edge.north:
                raise PRGAAPIError("IO block '{}' cannot be placed on the northwest corner of the FPGA".format(model))
            elif position == (self.width - 1, 0) and self._module.edge.east and self._module.edge.south:
                raise PRGAAPIError("IO block '{}' cannot be placed on the southeast corner of the FPGA".format(model))
            elif position == (self.width - 1, self.height - 1) and self._module.edge.east and self._module.edge.north:
                raise PRGAAPIError("IO block '{}' cannot be placed on the northeast corner of the FPGA".format(model))
            elif not ((position.x == 0 and self._module.edge.west) or
                    (position.x == self.width - 1 and self._module.edge.east) or
                    (position.y == 0 and self._module.edge.south) or
                    (position.y == self.height - 1 and self._module.edge.north)):
                raise PRGAAPIError("IO block '{}' must be placed on an edge of the FPGA".format(model))
            root = self._module._instances.get_root(position, Subtile.center)
            if root is not None:
                raise PRGAAPIError("Subtile '{}' of '{}' in leaf array '{}' already occupied by '{}'"
                        .format(subtile.name, position, self._module, root))
        else:
            subtile = (model.key.orientation.to_subtile() if model.module_class.is_connection_box else
                    model.key.corner.to_subtile() if model.module_class.is_switch_box else None)
            if subtile is None:
                raise PRGAAPIError("Cannot instantiate '{}' in leaf array '{}'. Unsupported module class: {}"
                        .format(model, self._module, model.module_class.name))
            elif (position.x == 0 and self._module.edge.west and
                    subtile not in (Subtile.northeast, Subtile.southeast, Subtile.east)):
                raise PRGAAPIError("Routing box '{}' cannot be placed on the west edge of the FPGA".format(model))
            elif (position.x == self.width - 1 and self._module.edge.east and
                    subtile not in (Subtile.northwest, Subtile.southwest, Subtile.west)):
                raise PRGAAPIError("Routing box '{}' cannot be placed on the east edge of the FPGA".format(model))
            elif (position.y == 0 and self._module.edge.south and
                    subtile not in (Subtile.northwest, Subtile.northeast, Subtile.north)):
                raise PRGAAPIError("Routing box '{}' cannot be placed on the south edge of the FPGA".format(model))
            elif (position.y == self.height - 1 and self._module.edge.north and
                    subtile not in (Subtile.southwest, Subtile.southeast, Subtile.south)):
                raise PRGAAPIError("Routing box '{}' cannot be placed on the north edge of the FPGA".format(model))
            root = self._module._instances.get_root(position, subtile)
            if root is not None:
                raise PRGAAPIError("Subtile '{}' of '{}' in leaf array '{}' already occupied by '{}'"
                        .format(subtile.name, position, self._module, root))
            if model.module_class.is_connection_box:    # special check when instantiating a connection box
                root = self._module._instances.get_root(position, Subtile.center)
                if root is None:
                    raise PRGAAPIError("Connection box cannot be placed at '{}' in leaf array '{}'"
                            .format(position, self._module))
                rootpos, _ = root.key
                offset = position - rootpos
                if root.model is not model.key.block or offset != model.key.position:
                    raise PRGAAPIError("Connection box cannot be placed at '{}' in leaf array '{}'"
                            .format(position, self._module))
        # 2. instantiation
        if name is None:
            if model.module_class.is_io_block:
                name = "iob_x{}y{}".format(position.x, position.y)
            elif model.module_class.is_logic_block:
                name = "lb_x{}y{}".format(position.x, position.y)
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
        elif model.module_class.is_logic_block:
            ModuleUtils.instantiate(self._module, model, name, key = (position, Subtile.center))
            for x, y in product(range(model.width), range(model.height)):
                for subtile in self._block_subtile_checklist(model, x, y, True):
                    self._module._instances.grid[position.x + x][position.y + y][subtile] = Position(x, y)
        elif model.module_class.is_connection_box:
            ModuleUtils.instantiate(self._module, model, name, key = (position, model.key.orientation.to_subtile()))
        elif model.module_class.is_switch_box:
            ModuleUtils.instantiate(self._module, model, name, key = (position, model.key.corner.to_subtile()))

    def fill(self,
            default_fc,
            *,
            fc_override = None,
            sbox_pattern = SwitchBoxPattern.wilton,
            identifier = None):
        """Fill routing boxes into the array being built."""
        fc_override = uno(fc_override, {})
        for tunnel in itervalues(self._context.tunnels):
            for port in (tunnel.source, tunnel.sink):
                fc = fc_override.setdefault(port.parent.key, BlockFCValue._construct(default_fc))
                fc.overrides[port.key] = BlockPortFCValue(0)
        processed_boxes = set()
        for x, y in product(range(self._module.width), range(self._module.height)):
            position = Position(x, y)
            # connection boxes
            on_edge = OrientationTuple(
                    north = y == self._module.height - 1,
                    east = x == self._module.width - 1,
                    south = y == 0,
                    west = x == 0)
            for ori in Orientation:
                if self._module._instances.get_root(position, ori.to_subtile()) is not None:
                    continue
                elif any(on_edge[ori2] and self._module.edge[ori2] for ori2 in Orientation
                        if ori2 is not ori.opposite):
                    continue
                block_instance = self._module._instances.get_root(position, Subtile.center)
                if block_instance is None:
                    continue
                fc = BlockFCValue._construct(fc_override.get(block_instance.model.key, default_fc))
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
                        identifier = identifier)
                if cbox.module.key not in processed_boxes:
                    cbox.fill(fc_override.get(block_instance.model.key, default_fc))
                    processed_boxes.add(cbox.commit().key)
                self.instantiate(cbox.module, position)
            # switch boxes
            for corner in sbox_pattern.fill_corners:
                if self._module._instances.get_root(position, corner.to_subtile()) is not None:
                    continue
                # analyze the environment of this switch box (output orientations, excluded inputs, crosspoints, etc.)
                outputs = {}    # orientation -> drive_at_crosspoints, crosspoints_only
                curpos, curcorner = position, corner
                while True:
                    # primary output
                    primary_output = Orientation[curcorner.case("south", "east", "west", "north")]
                    if not self._no_channel_for_switchbox(self._module, curpos, curcorner.to_subtile(),
                            primary_output, True):
                        drivex, _ = outputs.get(primary_output, (False, False))
                        drivex = drivex or self._no_channel_for_switchbox(self._module, curpos, curcorner.to_subtile(),
                                primary_output)
                        outputs[primary_output] = drivex, False
                    # secondary output: only effective on switch-boxes driving wire segments going out 
                    secondary_output = primary_output.opposite
                    if ( secondary_output.case( curpos.y == self._module.height - 1,
                        curpos.x == self._module.width - 1, curpos.y == 0, curpos.x == 0) and
                        self._no_channel_for_switchbox(self._module, curpos, curcorner.to_subtile(), secondary_output)
                        ):
                        _, xo = outputs.get(secondary_output, (True, True))
                        outputs[secondary_output] = True, xo
                    # go to the next corner
                    if curcorner.is_northeast:
                        curpos, curcorner = curpos + (0, 1), Corner.southeast
                    elif curcorner.is_southeast:
                        curpos, curcorner = curpos + (1, 0), Corner.southwest
                    elif curcorner.is_southwest:
                        curpos, curcorner = curpos - (0, 1), Corner.northwest
                    else:
                        assert curcorner.is_northwest
                        curpos, curcorner = curpos - (1, 0), Corner.northeast
                    # check if we've gone through all corners
                    if curcorner in sbox_pattern.fill_corners:
                        break
                if len(outputs) == 0:
                    continue
                # analyze excluded inputs
                excluded_inputs = set(ori for ori in Orientation
                        if self._no_channel_for_switchbox(self._module, position,
                            corner.to_subtile(), ori))
                if len(excluded_inputs) == 4:
                    continue
                # construct the identifier
                sbox_identifier = [identifier] if identifier is not None else []
                oid = ""
                for ori in Orientation:
                    settings = outputs.get(ori)
                    if settings is None:
                        continue
                    if settings[1]:
                        oid += ori.name[0]
                    elif settings[0]:
                        oid += ori.name[0].upper() + ori.name[0]
                    else:
                        oid += ori.name[0].upper()
                sbox_identifier.append(oid)
                if excluded_inputs:
                    exid = "".join(ori.name[0] for ori in Orientation if ori in excluded_inputs)
                    sbox_identifier.extend( ["ex", exid] )
                sbox_identifier = "_".join(sbox_identifier)
                # build switch box
                sbox = self._context.get_switch_box(corner, identifier = sbox_identifier)
                if sbox.module.key not in processed_boxes:
                    for output, (drivex, xo) in iteritems(outputs):
                        sbox.fill(output, drive_at_crosspoints = drivex, crosspoints_only = xo,
                                exclude_input_orientations = excluded_inputs, pattern = sbox_pattern)
                    processed_boxes.add(sbox.commit().key)
                self.instantiate(sbox.module, position)

    def auto_connect(self, *, is_top = None):
        is_top = self._module is self._context.top if is_top is None else is_top
        # connect routing nodes
        for x, y, subtile in product(range(self._module.width), range(self._module.height), Subtile):
            pos = Position(x, y)
            # 1. check out the instance
            instance = self._module.instances.get( (pos, subtile) )
            if instance is None:
                continue
            # 2. if the instance is a block, process global wires
            if instance.model.module_class.is_block:
                for subblock in range(instance.model.capacity):
                    instance = self._module.instances.get( (pos, subblock) )
                    for pin in itervalues(instance.pins):
                        if hasattr(pin.model, 'global_'):
                            self.connect(self._get_or_create_global_input(self._module, pin.model.global_), pin)
                continue
            # 3. connect segments and block pins
            for key, pin in iteritems(instance.pins):
                if isinstance(key, SegmentID):          # segment
                    if key.segment_type in (SegmentType.sboxin_regular, SegmentType.cboxin):
                        # 3.1 find the segment source 
                        node = key.convert(SegmentType.sboxout, pos)
                        source = None
                        # 3.1.1 try to find the pin
                        for src_sbox_key in self._segment_searchlist(node, pos, subtile,
                                self.width, self.height):
                            if self._no_channel_for_switchbox(self._module, *src_sbox_key, key.orientation, True):
                                break
                            sbox = self._module.instances.get( src_sbox_key )
                            if sbox is None:
                                continue
                            source = sbox.pins.get( node.convert(position_adjustment = -src_sbox_key[0]) )
                            if source is not None:
                                break
                        # 3.1.2 if found, connect them
                        if source is not None:
                            self.connect(source, pin)
                        # 3.1.3 if no pin is found, check if we need to expose the pin to the outside world
                        elif (not is_top and
                                node.orientation.case(
                                    north = node.position.y <= 0,
                                    east = node.position.x <= 0,
                                    south = node.position.y >= self._module.height - 1,
                                    west = node.position.x >= self._module.width - 1,
                                    ) and
                                node.orientation.dimension.case(
                                    x = -1 <= node.position.y < self._module.height,
                                    y = -1 <= node.position.x < self._module.width,
                                    )):
                            self._expose_routable_pin(pin, create_port = True)
                    elif key.segment_type.is_cboxout:
                        # 3.2 find the segment source so we can find the sbox to be connected
                        node = key.convert(SegmentType.sboxout, pos)
                        sbox, source = None, None
                        # 3.2.1 try to find the sbox pin driving the node
                        for src_sbox_key in self._segment_searchlist(node, pos, subtile,
                                self.width, self.height, forward = True):
                            if self._no_channel_for_switchbox(self._module, *src_sbox_key, key.orientation, True):
                                break
                            sbox = self._module.instances.get( src_sbox_key )
                            if sbox is None:
                                continue
                            source = sbox.pins.get( node.convert(position_adjustment = -src_sbox_key[0]) )
                            if source is not None:
                                break
                        # 3.2.2 if found, get or create the C-S bridge in the sbox and connect
                        if source is not None:
                            # is the bridge already there?
                            node = node.convert(SegmentType.sboxin_cboxout2, -sbox.key[0])
                            bridge = sbox.pins.get(node)
                            if bridge is not None:
                                source = NetUtils.get_source(bridge, return_none_if_unconnected = True)
                                if source is None:
                                    self.connect(pin, bridge)
                                    continue
                                elif source == pin:
                                    continue
                            # is the bridge already there in another form?
                            node = node.convert(SegmentType.sboxin_cboxout)
                            bridge = sbox.pins.get(node)
                            if bridge is not None:
                                source = NetUtils.get_source(bridge, return_none_if_unconnected = True)
                                if source is None:
                                    self.connect(pin, bridge)
                                    continue
                                elif source == pin:
                                    continue
                            bridge = SwitchBoxBuilder(self._context, sbox.model)._add_cboxout(node)
                            self.connect(pin, sbox.pins[bridge.key])
                        # 3.2.3 if no pin is found, check if we need to expose the pin to the outside world
                        elif (not is_top and
                                node.orientation.dimension.case(
                                    x = node.position.y in (-1, self.height - 1) and 0 <= node.position.x < self.width,
                                    y = node.position.x in (-1, self.width - 1) and 0 <= node.position.y < self.height,
                                    )):
                            self._expose_routable_pin(pin, create_port = True)
                elif isinstance(key, BlockPinID):       # block pin
                    # find the block and connect it
                    block_pos = pos + key.position - key.prototype.position
                    block_instance = self._module.instances[block_pos, key.subblock]
                    if pin.model.direction.is_input:
                        self.connect(block_instance.pins[key.prototype.key], pin)
                    else:
                        self.connect(pin, block_instance.pins[key.prototype.key])
                else:                                   # what is this?
                    raise PRGAInternalError("Unknown routing node: {}, pin: {}".format(key, pin))
        # do a second pass if there are direct inter-block tunnels
        for tunnel, (x, y) in product(itervalues(self._context.tunnels),
                product(range(self._module.width), range(self._module.height))):
            pos = Position(x, y)
            instance = self._module.instances.get( (pos, Subtile.center) )
            if instance is None:
                continue
            elif tunnel.sink.parent is not instance.model:
                continue
            assert instance.model.module_class.is_logic_block
            # 1. find the sink pin
            sink = instance.pins[tunnel.sink.key]
            # 2. check if the pin is driven by a connection block
            driver = NetUtils.get_source(sink, return_none_if_unconnected = True)
            if driver is None:
                pass
            elif driver.net_type.is_pin:
                assert driver.instance.model.module_class.is_connection_box
                bridge = driver.instance.model.ports.get(BlockPinID(tunnel.offset, tunnel.source), None)
                if bridge is None:
                    bridge = ConnectionBoxBuilder(self._context, driver.instance.model)._add_tunnel_bridge(tunnel)
                sink = driver.instance.pins[bridge.key]
            elif driver.net_type.is_port:
                assert driver.parent is self._module
                continue
            # 3. find the source pin
            block_pos = pos + tunnel.sink.position + tunnel.offset - tunnel.source.position
            if not (0 <= block_pos.x < self._module.width and 0 <= block_pos.y < self._module.height):
                # outside the array
                if is_top:
                    continue
                src_pos = block_pos + tunnel.source.position
                if (0 <= src_pos.x < self._module.width and 0 <= src_pos.y < self._module.height):
                    continue
                node = BlockPinID(src_pos, tunnel.source)
                port = self._module.ports.get(node, None)
                if port is None:
                    port = ModuleUtils.create_port(self._module, self._node_name(node), len(sink),
                            PortDirection.input_, key = node)
                NetUtils.connect(port, sink)
                continue
            # 3.1 find the source block
            instance = self._module.instances.get( (block_pos, Subtile.center) )
            if instance is None or instance.model is not tunnel.source.parent:
                continue
            # 3.2 find the source pin and connect them
            NetUtils.connect(instance.pins[tunnel.source.key], sink)

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`tuple` [:obj:`tuple` [:obj:`int`, :obj:`int` ], :obj:`int` or `Subtile` ],
            `AbstractInstances` ]: Proxy to ``module.instances``.
            
        The key is composed of the position in the array and the subtile/subblock in the array.
        """
        return self._module.instances

# ----------------------------------------------------------------------------
# -- Non Leaf Array Builder --------------------------------------------------
# ----------------------------------------------------------------------------
class NonLeafArrayBuilder(_BaseArrayBuilder):
    """Non-Leaf array builder.

    Args:
        context (`Context`): The context of the builder
        module (`AbstractModule`): The module to be built
    """

    # == low-level API =======================================================
    @classmethod
    def _get_hierarchical_root(cls, array, position, subtile):
        assert 0 <= position.x < array.width and 0 <= position.y < array.height
        if array.module_class.is_leaf_array:
            return array._instances.get_root(position, subtile)
        else:
            inst = array._instances.get_root(position)
            if inst is None:
                return None
            sub = cls._get_hierarchical_root(inst.model, position - inst.key, subtile)
            if sub is None:
                return None
            else:
                return inst.extend_hierarchy(below = sub)

    # == high-level API ======================================================
    @classmethod
    def new(cls, name, width, height, *, edge = OrientationTuple(False)):
        """Create a new module for building."""
        return Module(name,
                view = ModuleView.user,
                instances = NonLeafArrayInstanceMapping(width, height),
                coalesce_connections = True,
                module_class = ModuleClass.nonleaf_array,
                width = width,
                height = height, 
                edge = edge)

    def instantiate(self, model, position, *, name = None):
        """Instantiate ``model`` at the speicified position in the array.

        Args:
            model (`AbstractModule`): An array
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position in the array

        Keyword Args:
            name (:obj:`int`): Custom name of the instance
        """
        position = Position(*position)
        # 1. make sure all subtiles are not already occupied
        for x, y in product(range(model.width), range(model.height)):
            pos = position + (x, y)
            if pos.x >= self.width or pos.y >= self.height:
                raise PRGAAPIError("'{}' is not in non-leaf array '{}' ({} x {})"
                        .format(pos, self._module, self.width, self.height))
            sub_on_edge = OrientationTuple(
                    north = y == model.height - 1 and model.edge.north,
                    east = x == model.width - 1 and model.edge.east,
                    south = y == 0 and model.edge.south,
                    west = x == 0 and model.edge.west)
            self_on_edge = OrientationTuple(
                    north = pos.y == self.height - 1 and self._module.edge.north,
                    east = pos.x == self.width - 1 and self._module.edge.east,
                    south = pos.y == 0 and self._module.edge.south,
                    west = pos.x == 0 and self._module.edge.west)
            for ori in Orientation:
                if sub_on_edge[ori] and not self_on_edge[ori]:
                    raise PRGAAPIError("Subarray '{}' must be placed on the {} edge of the FPGA"
                            .format(model, ori.name))
                elif not sub_on_edge[ori] and self_on_edge[ori]:
                    raise PRGAAPIError("Subarray '{}' cannot be placed on the {} edge of the FPGA"
                            .format(model, ori.name))
            root = self._module._instances.get_root(pos)
            if root is not None:
                raise PRGAAPIError("'{}' in non-leaf array '{}' already occupied by '{}'"
                        .format(pos, self._module, root))
        # 2. instantiation
        name = uno(name, "subarray_x{}y{}".format(position.x, position.y))
        ModuleUtils.instantiate(self._module, model, name, key = position)
        for x, y in product(range(model.width), range(model.height)):
            if x == 0 and y == 0:
                continue
            self._module._instances.grid[position.x + x][position.y + y] = Position(x, y)

    def auto_connect(self, *, is_top = None):
        is_top = self._module is self._context.top if is_top is None else is_top
        # 1st pass: auto-connect all sub-arrays
        auto_connected = set()
        for pos in product(range(self._module.width), range(self._module.height)):
            # 1. check out the instance
            instance = self._module.instances.get( pos )
            if instance is None or instance.model.key in auto_connected:
                continue
            # 2. auto-connect
            if instance.model.module_class.is_leaf_array:
                LeafArrayBuilder(self._context, instance.model).auto_connect(is_top = False)
            else:
                NonLeafArrayBuilder(self._context, instance.model).auto_connect(is_top = False)
            auto_connected.add(instance.model.key)
        # 2nd pass: connect routing nodes
        for x, y in product(range(self._module.width), range(self._module.height)):
            pos = Position(x, y)
            # 1. check out the instance
            instance = self._module.instances.get( pos )
            if instance is None:
                continue
            assert instance.model.module_class.is_array
            # 2. make a snapshot of the pins (because it might change!)
            snapshot = tuple(iteritems(instance.pins))
            for key, pin in snapshot:
                if isinstance(key, SegmentID):                  # segment
                    box_position, box_subtile = pin.model.boxkey
                    node = key.convert(SegmentType.sboxout, pos)
                    if key.segment_type.is_array_input:         # try to find the source driving the input
                        source = None
                        for src_sbox_position, src_sbox_subtile in self._segment_searchlist(node, box_position + pos,
                                box_subtile, self.width, self.height):
                            if self._no_channel_for_switchbox(self._module, src_sbox_position, src_sbox_subtile,
                                    node.orientation, True):
                                break
                            sbox = self._get_hierarchical_root(self._module, src_sbox_position, src_sbox_subtile)
                            if sbox is None or not sbox.model.module_class.is_switch_box:
                                continue
                            sbox_node = node.convert(position_adjustment = -src_sbox_position)
                            source = sbox.pins.get(sbox_node)
                            if source is not None:
                                source = self._expose_routable_pin(source)
                                break
                        if source is not None:
                            self.connect(source, pin)
                        elif (not is_top and
                                node.orientation.case(
                                    north = node.position.y <= 0,
                                    east = node.position.x <= 0,
                                    south = node.position.y >= self.height - 1,
                                    west = node.position.x >= self.width - 1,
                                    ) and
                                node.orientation.dimension.case(
                                    x = -1 <= node.position.y < self.height,
                                    y = -1 <= node.position.x < self.width,
                                    )):
                            self._expose_routable_pin(pin, create_port = True)
                    elif (key.segment_type in (SegmentType.array_cboxout, SegmentType.array_cboxout2) and
                            pin.model.direction.is_output):     # try to find the segment driven by this
                        box_position, box_subtile = pin.model.boxkey
                        sbox, source = None, None
                        for src_sbox_position, src_sbox_subtile in self._segment_searchlist(node, box_position + pos,
                                box_subtile, self.width, self.height, forward = True):
                            if self._no_channel_for_switchbox(self._module, src_sbox_position, src_sbox_subtile,
                                    node.orientation, True):
                                break
                            sbox = self._get_hierarchical_root(self._module, src_sbox_position, src_sbox_subtile)
                            if sbox is None or not sbox.model.module_class.is_switch_box:
                                continue
                            sbox_node = node.convert(position_adjustment = -src_sbox_position)
                            source = sbox.pins.get(sbox_node)
                            if source is not None:
                                break
                        if source is not None:
                            # let's see if the bridge is already there in the switch box
                            done = False
                            for segment_type in (SegmentType.sboxin_cboxout, SegmentType.sboxin_cboxout2):
                                bridge = sbox.hierarchy[0].pins.get(source.model.key.convert(segment_type))
                                if bridge is not None:
                                    # There's one bridge over there! Trace up and see if it's usable
                                    for i, inst in enumerate(sbox.hierarchy[1:]):
                                        bridge_source = NetUtils.get_source(bridge, return_none_if_unconnected = True)
                                        if bridge_source is None:
                                            # cool! this one is unused
                                            bridge = bridge.instance.extend_hierarchy(
                                                    above = sbox.hierarchy[i + 1:]).pins[bridge.model.key]
                                            bridge = self._expose_routable_pin(bridge)
                                            break
                                        elif bridge_source.net_type.is_pin:
                                            # bad news. it's driven by another pin
                                            bridge = None
                                            break
                                        else: # we're not sure if this one is usable
                                            assert bridge_source.net_type.is_port
                                            bridge = inst.pins[bridge_source.key]
                                if bridge is not None:  # cool, we found a source that may be usable
                                    bridge_source = NetUtils.get_source(bridge, return_none_if_unconnected = True)
                                    if bridge_source is None:
                                        self.connect(pin, bridge)
                                    elif bridge_source != pin:
                                        continue
                                    done = True
                                    break
                            if done:
                                continue
                            # no bridge already available. create a new one
                            bridge = SwitchBoxBuilder(self._context, sbox.model)._add_cboxout(
                                    source.model.key.convert(SegmentType.sboxin_cboxout))
                            self.connect(pin, self._expose_routable_pin(sbox.pins[bridge.key]))
                        elif (not is_top and
                                node.orientation.dimension.case(
                                    x = node.position.y in (-1, self.height - 1) and 0 <= node.position.x < self.width,
                                    y = node.position.x in (-1, self.width - 1) and 0 <= node.position.y < self.height,
                                    )):
                            self._expose_routable_pin(pin, create_port = True)
                elif isinstance(key, BlockPinID):
                    # process sinks only
                    if pin.model.direction.is_output:
                        continue
                    block_pos = pos + key.position - key.prototype.position
                    # check if the source of the pin is in this array
                    if not (0 <= block_pos.x < self._module.width and 0 <= block_pos.y < self._module.height):
                        if is_top:
                            continue
                        src_pos = block_pos + key.prototype.position
                        if (0 <= src_pos.x < self._module.width and 0 <= src_pos.y < self._module.height):
                            continue
                        self.connect(self._expose_routable_pin(pin, create_port = True), pin)
                        continue
                    instance = self._get_hierarchical_root(self._module, block_pos, Subtile.center)
                    if instance is None or not (instance.model is key.prototype.parent and
                            self._instance_position(instance) == block_pos):
                        continue
                    self.connect(self._expose_routable_pin(instance.pins[key.prototype.key]), pin)
                elif hasattr(pin.model, 'global_'):
                    self.connect(self._get_or_create_global_input(self._module, pin.model.global_), pin)
                else:                                   # what is this?
                    raise PRGAInternalError("Unknown routing node: {}, pin: {}".format(key, pin))

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`tuple` [:obj:`int`, :obj:`int` ], `AbstractInstances` ]: Proxy to
        ``module.instances``."""
        return self._module.instances
