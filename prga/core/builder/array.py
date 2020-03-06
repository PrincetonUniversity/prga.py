# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseBuilder, MemOptUserConnGraph
from .box import SwitchBoxBuilder
from ..common import (ModuleClass, Subtile, Position, Orientation, Dimension, Corner, OrientationTuple, SegmentID,
        SegmentType, BlockPinID, BlockFCValue)
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.util import ModuleUtils
from ...netlist.module.module import Module
from ...util import Object, uno
from ...exception import PRGAInternalError, PRGAAPIError

from collections import OrderedDict
from itertools import product
from abc import abstractproperty, abstractmethod

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
                    # sboxout = 'so',
                    # cboxout = 'co',
                    # sboxin_regular = 'si',
                    # sboxin_cboxout = 'co',
                    # sboxin_cboxout2 = 'co2',
                    # cboxin = 'ci',
                    array_input = 'ai',
                    array_output = 'ao',
                    array_cboxout = 'co',
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
                if ((x == 0 and model.edge.west) or
                        (x == model.width - 1 and model.edge.east) or
                        (y == model.height - 1 and model.edge.north)):
                    return True
            else:
                if ((y == 0 and model.edge.south) or
                        (y == model.height - 1 and model.edge.north) or
                        (x == model.width - 1 and model.edge.east)):
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
        elif corner.dotx(Dimension.y).is_dec and not ori.case(not output, True, output, True):
            corrected -= (0, 1)
        return cls._no_channel(model, position, ori)

    @classmethod
    def _segment_searchlist(cls, node, position, subtile, width, height, *, forward = False):
        # 1. create a list of all possible position + corner where we may find the source
        searchlist = []
        # 1.1 initial search position
        try:
            corner = Corner.compose(node.orientation.opposite, subtile.to_orientation())
            skip = False
        except PRGAInternalError:
            corner = subtile.to_corner()
            skip = not forward
        # 1.2 constants
        paradim, perpdim = node.orientation.dimension, node.orientation.dimension.perpendicular
        sgmt_paradir, preferred_perpdir = node.orientation.direction, corner.dotx(perpdim)
        while True:
            # 1.3 check if the given position + corner is inside the boundary
            if skip:
                skip = False
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
    def _expose_routable_pin(cls, array, key, pin):
        """Expose ``pin`` as a port, and connect them."""
        node = None
        if key.node_type.is_segment:
            node = key.convert(key.segment_type.case(
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
                ))
            while True:
                port = array.ports.get(node)
                if port is None:
                    break
                elif port.direction is pin.model.direction:
                    # assert array._coalesce_connections
                    source, sink = (pin, port) if port.direction.is_output else (port, pin)
                    cur_source = NetUtils.get_source(sink)
                    if cur_source.net_type.is_unconnected:
                        NetUtils.connect(source, sink)
                        return port
                    elif cur_source == source:
                        return port
                if port is not None and node.segment_type.is_array_cboxout:
                    node = node.convert(SegmentType.array_cboxout2)
                    continue
                raise PRGAInternalError("'{}' already exposed but not correctly connected".format(pin))
        if array.module_class.is_leaf_array:
            port = ModuleUtils.create_port(array, cls._node_name(node),
                    len(pin), pin.model.direction, key = node,
                    boxkey = pin.hierarchy[-1].key)
        else:
            port = ModuleUtils.create_port(array, cls._node_name(node),
                    len(pin), pin.model.direction, key = node,
                    boxkey = (pin.hierarchy[-1].key + pin.model.boxkey[0], pin.model.boxkey[1]))
        if pin.model.direction.is_input:
            NetUtils.connect(port, pin)
        else:
            NetUtils.connect(pin, port)
        return port

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
        # if model.module_class.is_leaf_array:
        #     for i in Subtile:
        #         if exclude_root and i.is_center and x == 0 and y == 0:
        #             continue
        #         yield i
        # elif model.module_class.is_logic_block:
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
        # else:
        #     raise PRGAInternalError("Unsupported module class '{}'".format(model.module_class.name))

    # == high-level API ======================================================
    @classmethod
    def new(cls, name, width, height, *, edge = OrientationTuple(False)):
        """Create a new module for building."""
        return Module(name,
                ports = OrderedDict(),
                instances = _LeafArrayInstanceMapping(width, height),
                conn_graph = MemOptUserConnGraph(),
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
                name = "clb_x{}y{}".format(position.x, position.y)
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
                    self._module._instances.grid[position.x][position.y][subtile] = Position(x, y)
        elif model.module_class.is_connection_box:
            ModuleUtils.instantiate(self._module, model, name, key = (position, model.key.orientation.to_subtile()))
        elif model.module_class.is_switch_box:
            ModuleUtils.instantiate(self._module, model, name, key = (position, model.key.corner.to_subtile()))

    def fill(self,
            default_fc,
            *,
            fc_override = None,
            closure_on_edge = OrientationTuple(False),
            identifier = None):
        """Fill routing boxes into the array being built."""
        fc_override = uno(fc_override, {})
        for x, y in product(range(self._module.width), range(self._module.height)):
            on_edge = OrientationTuple(
                    north = y == self._module.height - 1,
                    east = x == self._module.width - 1,
                    south = y == 0,
                    west = x == 0)
            next_to_edge = OrientationTuple(
                    north = y == self._module.height - 2,
                    east = x == self._module.width - 2,
                    south = y == 1,
                    west = x == 1)
            position = Position(x, y)
            # connection boxes
            for ori in Orientation:
                if ori.is_auto:
                    continue
                elif self._module._instances.get_root(position, ori.to_subtile()) is not None:
                    continue
                elif any(on_edge[ori2] and self._module.edge[ori2] for ori2 in Orientation
                        if ori2 not in (Orientation.auto, ori.opposite)):
                    continue
                block_instance = self._module._instances.get_root(position, Subtile.center)
                if block_instance is None:
                    continue
                fc = BlockFCValue._construct(fc_override.get(block_instance.model.name, default_fc))
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
                cbox.fill(fc_override.get(block_instance.model.name, default_fc))
                self.instantiate(cbox.commit(), position)
            # switch boxes
            for corner in Corner:
                if self._module._instances.get_root(position, corner.to_subtile()) is not None:
                    continue
                elif any(on_edge[ori] and self._module.edge[ori] for ori in corner.decompose()):
                    continue
                # analyze the environment of this switch box (output orientations, excluded inputs, crosspoints, etc.)
                outputs = []                        # orientation, drive_at_crosspoints, crosspoints_only
                sbox_identifier = [identifier] if identifier else []
                # 1. primary output
                primary_output = Orientation[corner.case("south", "east", "west", "north")]
                if not on_edge[primary_output] or not self._module.edge[primary_output]:
                    if on_edge[primary_output.opposite] and closure_on_edge[primary_output.opposite]:
                        outputs.append( (primary_output, True, False) )
                        sbox_identifier.append( "pc" )
                    else:
                        outputs.append( (primary_output, False, False) )
                        sbox_identifier.append( "p" )
                # 2. secondary output
                secondary_output = Orientation[corner.case("west", "south", "north", "east")]
                if (on_edge[primary_output.opposite] and not on_edge[secondary_output] and 
                        closure_on_edge[primary_output.opposite]):
                    if on_edge[secondary_output.opposite] and closure_on_edge[secondary_output.opposite]:
                        outputs.append( (secondary_output, True, False) )
                        sbox_identifier.append( "sc" )
                    else:
                        outputs.append( (secondary_output, False, False) )
                        sbox_identifier.append( "s" )
                # 3. tertiary output
                tertiary_output = primary_output.opposite
                if on_edge[tertiary_output.opposite] and self._module.edge[tertiary_output.opposite]:
                    outputs.append( (tertiary_output, True, True) )
                    sbox_identifier.append( "tc" )
                # 4. exclude inputs
                exclude_input_orientations = set(ori for ori in Orientation
                        if not ori.is_auto and self._no_channel_for_switchbox(self._module, position,
                            corner.to_subtile(), ori))
                for ori in corner.decompose():
                    if next_to_edge[ori] and self._module.edge[ori]:
                        exclude_input_orientations.add( ori.opposite )
                    ori = ori.opposite
                    if on_edge[ori] and self._module.edge[ori]:
                        exclude_input_orientations.add( ori.opposite )
                if exclude_input_orientations:
                    sbox_identifier.append( "ex_" + "".join(o.name[0] for o in sorted(exclude_input_orientations)) )
                sbox_identifier = "_".join(sbox_identifier)
                sbox = self._context.get_switch_box(corner, identifier = sbox_identifier)
                for output, drivex, xo in outputs:
                    sbox.fill(output, drive_at_crosspoints = drivex, crosspoints_only = xo,
                            exclude_input_orientations = exclude_input_orientations)
                self.instantiate(sbox.commit(), position)

    def auto_connect(self, *, is_top = False):
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
                for pin in itervalues(instance.pins):
                    if hasattr(pin.model, 'global_'):
                        self.connect(self._get_or_create_global_input(self._module, pin.model.global_), pin)
                continue
            elif instance.model.module_class.is_io_block:
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
                        elif not is_top:
                            self._expose_routable_pin(self._module, key.convert(position_adjustment = pos), pin)
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
                                source = NetUtils.get_source(bridge)
                                if source.net_type.is_unconnected:
                                    self.connect(pin, bridge)
                                    continue
                                elif source == pin:
                                    continue
                            # is the bridge already there in another form?
                            node = node.convert(SegmentType.sboxin_cboxout)
                            bridge = sbox.pins.get(node)
                            if bridge is not None:
                                source = NetUtils.get_source(bridge)
                                if source.net_type.is_unconnected:
                                    self.connect(pin, bridge)
                                    continue
                                elif source == pin:
                                    continue
                            bridge = SwitchBoxBuilder(self._context, sbox.model)._add_cboxout(node)
                            self.connect(pin, sbox.pins[bridge.key])
                        # 3.2.3 if no pin is found, check if we need to expose the pin to the outside world
                        elif not is_top:
                            self._expose_routable_pin(self._module, key.convert(position_adjustment = pos), pin)
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
            inst = array._instances.get_root(position, subtile)
            if inst is None:
                return None
            else:
                return (inst, )
        else:
            inst = array._instances.get_root(position)
            if inst is None:
                return None
            hierarchy = cls._get_hierarchical_root(inst.model, position - inst.key, subtile)
            if hierarchy is None:
                return None
            else:
                return hierarchy + (inst, )

    # == high-level API ======================================================
    @classmethod
    def new(cls, name, width, height, *, edge = OrientationTuple(False)):
        """Create a new module for building."""
        return Module(name,
                ports = OrderedDict(),
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
                if ori.is_auto:
                    continue
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
                            if sbox is None or not sbox[0].model.module_class.is_switch_box:
                                continue
                            sbox_node = node.convert(position_adjustment = -src_sbox_position)
                            source = sbox[0].pins.get(sbox_node)
                            if source is None:
                                continue
                            else:
                                sbox_node = sbox_node.convert(position_adjustment = sbox[0].key[0])
                                for instance in sbox[1:]:
                                    source = self._expose_routable_pin(instance.model, sbox_node, source)
                                    source = instance.pins[source.key]
                                    sbox_node = sbox_node.convert(position_adjustment = instance.key)
                                break
                        if source is not None:
                            self.connect(source, pin)
                        elif not is_top:
                            self._expose_routable_pin(self._module, node, pin)
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
                            if sbox is None or not sbox[0].model.module_class.is_switch_box:
                                continue
                            sbox_node = node.convert(position_adjustment = -src_sbox_position)
                            source = sbox[0].pins.get(sbox_node)
                            if source is not None:
                                break
                        if source is not None:
                            # let's see if the bridge is already there in the switch box
                            done = False
                            for segment_type in (SegmentType.sboxin_cboxout, SegmentType.sboxin_cboxout2):
                                bridge_node = source.model.key.convert(segment_type)
                                bridge = sbox[0].pins.get(bridge_node)
                                bridge_node = bridge_node.convert(position_adjustment = sbox[0].key[0])
                                if bridge is not None:
                                    # There's one bridge over there! Trace up and see if it's usable
                                    for inst in sbox[1:]:
                                        bridge_source = NetUtils.get_source(bridge)
                                        if bridge_source.net_type.is_pin: # bad news. it's driven by another pin
                                            bridge = None
                                            break
                                        elif bridge_source.net_type.is_unconnected: # cool! this one is unused
                                            bridge = self._expose_routable_pin(inst.model, bridge_node, bridge)
                                            bridge = inst.pins[bridge.key]
                                        else: # we're not sure if this one is usable
                                            assert bridge_source.net_type.is_port
                                            bridge = inst.pins[bridge_source.key]
                                        bridge_node = bridge_node.convert(position_adjustment = inst.key)
                                if bridge is not None:  # cool, we found a source that may be usable
                                    bridge_source = NetUtils.get_source(bridge)
                                    if bridge_source.net_type.is_unconnected:
                                        self.connect(pin, bridge)
                                        done = True
                                        break
                                    elif bridge_source == pin:
                                        done = True
                                        break
                            if done:
                                continue
                            # no bridge already available. create a new one
                            bridge_node = source.model.key.convert(SegmentType.sboxin_cboxout)
                            bridge = SwitchBoxBuilder(self._context, sbox[0].model)._add_cboxout(bridge_node)
                            bridge = sbox[0].pins[bridge.key]
                            bridge_node = bridge_node.convert(position_adjustment = sbox[0].key[0])
                            for inst in sbox[1:]:
                                bridge = self._expose_routable_pin(inst.model, bridge_node, bridge)
                                bridge_node = bridge_node.convert(position_adjustment = inst.key)
                                bridge = inst.pins[bridge.key]
                            self.connect(pin, bridge)
                        elif not is_top:
                            self._expose_routable_pin(self._module, key.convert(position_adjustment = pos), pin)
                elif isinstance(key, BlockPinID):
                    pass
                elif hasattr(pin.model, 'global_'):
                    self.connect(self._get_or_create_global_input(self._module, pin.model.global_), pin)
                else:                                   # what is this?
                    raise PRGAInternalError("Unknown routing node: {}, pin: {}".format(key, pin))

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`tuple` [:obj:`int`, :obj:`int` ], `AbstractInstances` ]: Proxy to
        ``module.instances``."""
        return self._module.instances
