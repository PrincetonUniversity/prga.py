# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseArrayBuilder
from .tile import TileBuilder
from ..box.sbox import SwitchBoxBuilder
from ...common import (Corner, Position, OrientationTuple, SwitchBoxPattern, ModuleView, ModuleClass, Orientation,
        BridgeID, Dimension, BridgeType, BlockPinID)
from ....netlist.net.util import NetUtils
from ....netlist.module.instance import Instance
from ....netlist.module.module import Module
from ....netlist.module.util import ModuleUtils
from ....util import Object, uno
from ....exception import PRGAInternalError, PRGAAPIError

from itertools import product

__all__ = ['ArrayBuilder']

# ----------------------------------------------------------------------------
# -- Array Instance Mapping --------------------------------------------------
# ----------------------------------------------------------------------------
class _ArrayInstancesMapping(Object, MutableMapping):
    """Helper class for ``Array.instances`` property.

    Args:
        width (:obj:`int`): Width of the tile/array
        height (:obj:`int`): Height of the tile/array

    Supported key types:
        :obj:`tuple` [:obj:`int`, :obj:`int` ]: Root position of a tile. If a tile is larger than 1x1, the position of
            its bottom-left corner is the root position
        :obj:`tuple` [:obj:`tuple` [:obj:`int`, :obj:`int` ], `Corner` ]: Position of a switch box. The first element
            is the position, and the second element is the corner in that position
    """

    __slots__ = ["sboxes", "tiles"]
    def __init__(self, width, height):
        self.sboxes = [[[None for _ in Corner] for _ in range(height)] for _ in range(width)]
        self.tiles = [[None for _ in range(height)] for _ in range(width)]

    def __validate_position(self, x, y):
        return 0 <= x < len(self.tiles) and 0 <= y < len(self.tiles[0])

    def __getitem__(self, key):
        try:
            (x, y), corner = key
        except TypeError:
            try:
                (x, y), corner = key, None
            except TypeError:
                raise KeyError(key)
        if self.__validate_position(x, y):
            if corner is not None and isinstance((i := self.sboxes[x][y][corner]), Instance):
                return i
            elif corner is None and isinstance((i := self.tiles[x][y]), Instance):
                return i
        raise KeyError(key)

    def __setitem__(self, key, value):
        try:
            (x, y), corner = key
        except TypeError:
            try:
                (x, y), corner = key, None
            except TypeError:
                raise PRGAInternalError("Invalid key: {:r}".format(key))
        if not self.__validate_position(x, y):
            raise PRGAInternalError("Invalid position: {:r}".format(key))
        if corner is None:
            if self.tiles[x][y] is None:
                self.tiles[x][y] = value
            else:
                raise PRGAInternalError("Tile position ({}, {}) already occupied".format(x, y))
        else:
            if self.sboxes[x][y][corner] is None:
                self.sboxes[x][y][corner] = value
            else:
                raise PRGAInternalError("Switch box position ({}, {}, {:r}) already occupied"
                        .format(x, y, corner))

    def __delitem__(self, key):
        raise PRGAInternalError("Deleting from an array instances mapping is not supported")

    def __len__(self):
        cnt = 0
        for x, col in enumerate(self.tiles):
            for y, t in enumerate(col):
                if isinstance(t, Instance):
                    cnt += 1
                for sbox in self.sboxes[x][y]:
                    if isinstance(sbox, Instance):
                        cnt += 1
        return cnt

    def __iter__(self):
        for x, col in enumerate(self.tiles):
            for y, t in enumerate(col):
                if isinstance(t, Instance):
                    yield Position(x, y)
                for corner in Corner:
                    if isinstance(self.sboxes[x][y][corner], Instance):
                        yield Position(x, y), corner

    def get_root(self, position, corner = None):
        x, y = position
        if not self.__validate_position(x, y):
            return None
        if corner is None:
            try:
                if isinstance((i := self.tiles[x][y]), Instance):
                    return i
                elif isinstance(i, Position):
                    return self.tiles[x - i.x][y - i.y]
                else:
                    return None
            except IndexError:
                return None
        else:
            try:
                if isinstance((i := self.sboxes[x][y][corner]), Instance):
                    return i
                elif isinstance(i, Position):
                    return self.tiles[x - i.x][y - i.y]
                else:
                    return None
            except IndexError:
                return None

# ----------------------------------------------------------------------------
# -- Array Builder -----------------------------------------------------------
# ----------------------------------------------------------------------------
class ArrayBuilder(BaseArrayBuilder):
    """Array builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    @classmethod
    def _no_channel_for_switchbox(cls, module, position, corner, ori, output = False):
        x = ori.case(default = False, east = output, west = not output)
        if corner.dotx(Dimension.x).is_inc and x:
            position += (1, 0)
        elif corner.dotx(Dimension.x).is_dec and not x:
            position -= (1, 0)

        y = ori.case(default = False, north = output, south = not output)
        if corner.dotx(Dimension.y).is_inc and y:
            position += (0, 1)
        elif corner.dotx(Dimension.y).is_dec and not y:
            position -= (0, 1)

        return cls._no_channel(module, position, ori.dimension)

    @classmethod
    def _equiv_sbox_position(cls, position, from_corner, to_corner = None):
        if to_corner is None:
            to_corner = from_corner.case(Corner.southeast, Corner.northeast, Corner.southwest, Corner.northwest)
        from_x, from_y = map(lambda o: from_corner.dotx(o), Dimension)
        to_x, to_y = map(lambda o: to_corner.dotx(o), Dimension)
        return (position + (to_x.case(from_x.case(0, -1), from_x.case(1, 0)),
            to_y.case(from_y.case(0, -1), from_y.case(1, 0))), to_corner)

    @classmethod
    def __expose_node(cls, pin):
        assert not pin.instance.is_hierarchical
        array = pin.parent
        pos = pin.instance.key[0] if pin.instance.model.module_class.is_switch_box else pin.instance.key
        node = pin.model.key.move(pos)
        if node.node_type.is_block:    # BLOCK PIN
            if (port := array.ports.get(node)) is None:
                port = ModuleUtils.create_port(array, cls._node_name(node), len(pin),
                        pin.model.direction, key = node)
            source, sink = (pin, port) if port.direction.is_output else (port, pin)
            if (cur_source := NetUtils.get_source(sink, return_none_if_unconnected = True)) is None:
                NetUtils.connect(source, sink)
            elif cur_source != source:
                raise PRGAInternalError("{} already exposed but not correctly connected".format(pin))
            return port
        if node.node_type.is_segment:  # SEGMENT
            node = node.convert(BridgeType.regular_output)
        elif node.node_type.is_bridge:
            if node.bridge_type.is_cboxout2:
                node = node.convert(BridgeType.cboxout)
        else:
            raise PRGAInternalError("Unknown node type: {:r}".format(pin.model.key.node_type))
        while (port := array.ports.get(node)) is not None:
            if port.direction.is_output:
                if pin.model.direction.is_output:
                    if (cur_source := NetUtils.get_source(port, return_none_if_unconnected = True)) is None:
                        NetUtils.connect(pin, port)
                        break
                    elif cur_source == pin:
                        break
            elif port.direction.is_input:
                if pin.model.direction.is_input:
                    if (cur_source := NetUtils.get_source(pin, return_none_if_unconnected = True)) is None:
                        if node.bridge_type not in (BridgeType.cboxout, BridgeType.cboxout2):
                            NetUtils.connect(port, pin)
                            break
                    elif cur_source == port:
                        break
            if node.bridge_type.is_cboxout:
                node = node.convert(BridgeType.cboxout2)
                continue
            elif node.bridge_type.is_cboxout2:
                raise PRGAInternalError("All cboxout bridges are used up in {}".format(array))
            raise PRGAInternalError("{} already exposed but not correctly connected".format(pin))
        boxpos, boxcorner = None, None
        if pin.instance.model.module_class.is_switch_box:
            boxpos, boxcorner = pin.instance.key
        else:
            boxpos, boxcorner = pin.model.boxpos[0] + pos, pin.model.boxpos[1]
        if port is None:
            port = ModuleUtils.create_port(array, cls._node_name(node), len(pin), pin.model.direction,
                    key = node, boxpos = (boxpos, boxcorner))
            if pin.model.direction.is_input:
                NetUtils.connect(port, pin)
            else:
                NetUtils.connect(pin, port)
        elif node.bridge_type.is_regular_input:
            oldpos, oldcorner = port.boxpos
            if node.orientation.is_north:
                if oldpos.y > boxpos.y or (oldpos.y == boxpos.y and oldcorner.dotx(Dimension.y).is_inc):
                    boxpos, boxcorner = oldpos, oldcorner
            elif node.orientation.is_east:
                if oldpos.x > boxpos.x or (oldpos.x == boxpos.x and oldcorner.dotx(Dimension.x).is_inc):
                    boxpos, boxcorner = oldpos, oldcorner
            elif node.orientation.is_south:
                if oldpos.y < boxpos.y or (oldpos.y == boxpos.y and oldcorner.dotx(Dimension.y).is_dec):
                    boxpos, boxcorner = oldpos, oldcorner
            elif node.orientation.is_west:
                if oldpos.x < boxpos.x or (oldpos.x == boxpos.x and oldcorner.dotx(Dimension.x).is_dec):
                    boxpos, boxcorner = oldpos, oldcorner
            else:
                raise PRGAInternalError("Unknown orientation: {:r}".format(node.orientation))
            port.boxpos = boxpos, boxcorner
        return port

    @classmethod
    def _expose_node(cls, pin, *, create_port = False):
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
            port = cls.__expose_node(instance.pins[port.key])
        if create_port:
            return cls.__expose_node(pin.instance.hierarchy[-1].pins[port.key])
        else:
            return pin.instance.hierarchy[-1].pins[port.key]

    @classmethod
    def _prepare_segment_driver_search(cls, drivee):
        # 1. calculate the absolute ending position
        node, pos, corner = None, None, None
        if drivee.instance.model.module_class.is_switch_box:
            pos, corner = drivee.instance.key
            node = drivee.model.key.move(pos).convert()
        else:
            pos, corner = drivee.model.boxpos
            pos += drivee.instance.key
            node = drivee.model.key.move(drivee.instance.key).convert()
        # 2. determine ordering
        ori = node.orientation
        ordering = (
                Corner.compose(ori.opposite, corner.decompose()[ori.dimension.perpendicular]),
                Corner.compose(ori.opposite, corner.decompose()[ori.dimension.perpendicular].opposite),
                Corner.compose(ori,          corner.decompose()[ori.dimension.perpendicular]),
                Corner.compose(ori,          corner.decompose()[ori.dimension.perpendicular].opposite),
                )
        # adjust pos and corner
        if corner.dotx(ori.dimension) is not ori.direction:
            pos += ori.case( (0, -1), (-1, 0), (0, 1), (1, 0) )
        # 3. final touch-up before we return
        if drivee.instance.model.module_class.is_switch_box or drivee.instance.model.module_class.is_tile:
            return node, pos, ordering, 0
        array = drivee.instance.model
        bound = OrientationTuple(
                north = drivee.instance.key.y + array.height - 1,
                east  = drivee.instance.key.x + array.width - 1,
                south = drivee.instance.key.y,
                west  = drivee.instance.key.x)
        if ori.dimension.is_y:
            if (ori.case(north = pos.y < bound.south, south = pos.y > bound.north)
                    or pos.x < bound.west or pos.x > bound.east):
                return node, pos, ordering, 0
            elif pos.x == bound.west and corner.dotx(Dimension.x).is_dec:
                return node, Position(bound.west - 1, pos.y), ordering, 1
            elif pos.x == bound.east and corner.dotx(Dimension.x).is_inc:
                return node, Position(bound.east + 1, pos.y), ordering, 1
            elif ori.is_north:
                return node, Position(pos.x, bound.south - 1), ordering, 2
            else:
                return node, Position(pos.x, bound.north + 1), ordering, 2
        elif ori.dimension.is_x:
            if (ori.case(east = pos.x < bound.west, west = pos.x > bound.east)
                    or pos.y < bound.south or pos.y > bound.north):
                return node, pos, ordering, 0
            elif pos.y == bound.south and corner.dotx(Dimension.y).is_dec:
                return node, Position(pos.x, bound.south - 1), ordering, 1
            elif pos.y == bound.north and corner.dotx(Dimension.y).is_inc:
                return node, Position(pos.x, bound.north + 1), ordering, 1
            elif ori.is_east:
                return node, Position(bound.west - 1, pos.y), ordering, 2
            else:
                return node, Position(bound.east + 1, pos.y), ordering, 2

    @classmethod
    def _find_segment_drivers(cls, module, node, pos, ordering, corner_idx):
        """Find the best segment driver."""
        # search backwards
        instances_visited = set()
        corner = ordering[corner_idx]
        while not cls._no_channel_for_switchbox(module, pos, corner, node.orientation, True):
            # using `while` only for easier flow contorl. This loop only executes once
            while (instance := module._instances.get_root(pos, corner)) is not None:
                # check if we've visited this instance
                if instance.key in instances_visited:
                    break
                instances_visited.add( instance.key )
                # if this instance is a switch box instance, check if it drives the segment
                if instance.model.module_class.is_switch_box:
                    if (pin := instance.pins.get(node.move(-instance.key[0]))) is not None:
                        yield pin
                    break
                # else if this instance is an array instance
                if instance.model.module_class.is_array:
                    # check if there is an output from the array that may drive the segment
                    if ((pin := instance.pins.get(node.convert(BridgeType.regular_output).move(-instance.key)))
                            is not None):
                        yield pin
                        break
                    for subdriver in cls._find_segment_drivers(instance.model, node.move(-instance.key),
                            pos - instance.key, ordering, corner_idx):
                        yield subdriver.instance.extend_hierarchy(above = instance).pins[subdriver.model.key]
                # end of code block
                break
            corner_idx = (corner_idx + 1) % 4
            pos, corner = cls._equiv_sbox_position(pos, corner, ordering[corner_idx])
            if corner_idx == 0:
                pos += node.orientation.case( (0, -1), (-1, 0), (0, 1), (1, 0) )
                # section check
                section = node.orientation.case(
                        north = pos.y - node.position.y + corner.dotx(Dimension.y).case(1, 0),
                        east  = pos.x - node.position.x + corner.dotx(Dimension.x).case(1, 0),
                        south = node.position.y - pos.y + corner.dotx(Dimension.y).case(0, 1),
                        west  = node.position.x - pos.x + corner.dotx(Dimension.x).case(0, 1) )
                if section < 0:
                    break
                # boundary check
                if node.orientation.case(
                        north = pos.y < 0,
                        east  = pos.x < 0,
                        south = pos.y >= module.height,
                        west  = pos.x >= module.width):
                    break

    @classmethod
    def _connect_cboxout(cls, module, pin, *, create_port = False):
        pos, corner = pin.model.boxpos
        pos += pin.instance.key
        node = pin.model.key.move(pin.instance.key)
        ori = node.orientation
        it_corner = iter((
            Corner.compose(ori.opposite, corner.decompose()[ori.dimension.perpendicular].opposite),
            Corner.compose(ori,          corner.decompose()[ori.dimension.perpendicular]),
            Corner.compose(ori,          corner.decompose()[ori.dimension.perpendicular].opposite),
            ))
        while True:
            # using `while` only for easier flow control. this loop executes only once
            while (sbox := cls.get_hierarchical_root(module, pos, corner)) is not None:
                sgmt_drv_node = node.move(-cls.hierarchical_position(sbox)).convert()
                if sgmt_drv_node not in sbox.pins:
                    break
                # does the bridge exist already?
                for brg_type in (BridgeType.cboxout, BridgeType.cboxout2):
                    if (bridge := sbox.hierarchy[0].pins.get(sgmt_drv_node.convert(brg_type))) is not None:
                        # check across hierarchy to see if this bridge is usable
                        for i, inst in enumerate(sbox.hierarchy[1:]):
                            if (brg_drv := NetUtils.get_source(bridge, return_none_if_unconnected = True)) is None:
                                # cool! this one is unused!
                                bridge = bridge.instance.extend_hierarchy(
                                        above = sbox.hierarchy[i + 1:]).pins[bridge.model.key]
                                bridge = cls._expose_node(bridge)
                                break
                            elif brg_drv.net_type.is_pin:
                                # bad news. this bridge is used by some other pins
                                bridge = None
                                break
                            else:
                                # we're not sure if this one is usable yet. Keep going up the hierarchy
                                assert brg_drv.net_type.is_port
                                bridge = inst.pins[brg_drv.key]
                        if bridge is not None:
                            # this bridge might be usable
                            if (brg_drv := NetUtils.get_source(bridge, return_none_if_unconnected = True)) is None:
                                NetUtils.connect(pin, bridge)
                                return
                            elif brg_drv == pin:
                                return
                # no bridge already available. create a new one
                bridge = SwitchBoxBuilder._add_cboxout(sbox.model, sgmt_drv_node.convert(BridgeType.cboxout))
                NetUtils.connect(pin, cls._expose_node(sbox.pins[bridge.key]))
                return
            # go to the next corner
            try:
                pos, corner = cls._equiv_sbox_position(pos, corner, next(it_corner))
            except StopIteration:
                break
        if create_port:
            cls._expose_node(pin, create_port = create_port)

    # == low-level API =======================================================
    @classmethod
    def get_hierarchical_root(cls, array, position, corner = None):
        """Get the hierarchical root instance occupying the given position

        Args:
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of the tile
            corner (`Corner`): If specified, get the switch box instance

        Returns:
            `Module`: If ``corner`` is not specified, return a hierarhical instance of a tile; otherwise a switch box
        """
        if array.module_class.is_array:
            if (i := array._instances.get_root(position, corner)) is None:
                return None
            elif corner is None and i.model.module_class.is_tile:
                return i
            elif corner is not None and i.model.module_class.is_switch_box:
                return i
            elif (i.model.module_class.is_array and
                    (sub := cls.get_hierarchical_root(i.model, position - i.key, corner)) is not None):
                return sub.extend_hierarchy(above = i)
            else:
                return None
        else:
            raise PRGAInternalError("Unsupported module class: {:r}".format(array.module_class))

    @classmethod
    def hierarchical_position(cls, instance):
        if instance.model.module_class.is_block:
            return sum( iter(i.key for i in instance.hierarchy[1:]), Position(0, 0) )
        elif instance.model.module_class.is_connection_box:
            return sum( iter(i.key for i in instance.hierarchy[1:]), instance.model.key.position )
        elif instance.model.module_class.is_switch_box:
            return sum( iter(i.key for i in instance.hierarchy[1:]), instance.hierarchy[0].key[0] )
        else:
            return sum( iter(i.key for i in instance.hierarchy), Position(0, 0) )

    # == high-level API ======================================================
    @classmethod
    def new(cls, name, width, height, *, edge = OrientationTuple(False), **kwargs):
        """Create a new array.
        
        Args:
            name (:obj:`str`): Name of the array
            width (:obj:`int`): Width of the array
            height (:obj:`int`): Height of the array

        Keyword Args:
            edge (`OrientationTuple` [:obj:`bool` ]): Marks this array to be on the specified edges of the top-level
                array. This affects segment instantiation.
            **kwargs: Additional attributes assigned to the array

        Returns:
            `Module`
        """
        return Module(name,
                view = ModuleView.user,
                instances = _ArrayInstancesMapping(width, height),
                coalesce_connections = True,
                module_class = ModuleClass.array,
                width = width,
                height = height,
                edge = edge,
                **kwargs)

    def instantiate(self, model, position, *, name = None, **kwargs):
        """Instantiate ``model`` at the specified position in the array.

        Args:
            model (`Module`): A tile, an array or a switch box
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Root position for the tile/array, or exact position of
                the switch box

        Keyword Args:
            name (:obj:`str`): Name of the instance. By default, ``"t_ix{x}y{y}"`` is used for tile/array instances
                and ``"sb_ix{x}y{t}{corner}"`` is used for switch box instances
            **kwargs: Additional attributes assigned to the instance

        Returns:
            `Instance`:
        """
        position = Position(*position)
        if model.module_class.is_switch_box:
            # Easier case: instantiating switch box
            # check if the position is already occupied
            if (i := self._module._instances.get_root(position, model.key.corner)) is not None:
                raise PRGAInternalError("Switch box position ({}, {}, {:r}) already occupied by {}"
                        .format(*position, corner, i))
            # instantiate the switch box
            return ModuleUtils.instantiate(self._module, model,
                    uno(name, 'sb_ix{}y{}{}'.format(*position, model.key.corner.case("ne", "nw", "se", "sw"))),
                    key = (position, model.key.corner))
        elif model.module_class.is_tile or model.module_class.is_array:
            # A bit more complex case: instantiating tile/array
            # check if any position that will be covered by this tile is already occupied
            for x, y in product(range(model.width), range(model.height)):
                pos = position + (x, y)
                # check if the position is within the array
                if not (0 <= pos.x < self.width and 0 <= pos.y < self.height):
                    raise PRGAAPIError("'{}' is not in array {} ({} x {})"
                            .format(pos, self._module, self.width, self.height))
                # check if the position is taken
                if (i := self._module._instances.get_root(pos)) is not None:
                    raise PRGAAPIError("'{}' in array {} is occupied by {}"
                            .format(pos, self._module, i))
                # check switch box positions that are covered by this instance
                sub_on_edge = OrientationTuple(
                        north = y == model.height - 1,
                        east = x == model.width - 1,
                        south = y == 0,
                        west = x == 0)
                for corner in Corner:
                    if model.module_class.is_tile and any(sub_on_edge[ori] for ori in corner.decompose()):
                        continue
                    elif (i := self._module._instances.get_root(pos, corner)) is not None:
                        raise PRGAAPIError("Switch box position ({}, {}, {:r}) already occupied by {}"
                                .format(*pos, corner, i))
                # check edge compatibility
                array_on_edge = OrientationTuple(
                        north = pos.y == self.height - 1 and self._module.edge.north,
                        east = pos.x == self.width - 1 and self._module.edge.east,
                        south = pos.y == 0 and self._module.edge.south,
                        west = pos.x == 0 and self._module.edge.west)
                for ori in Orientation:
                    if (sub_on_edge[ori] and model.edge[ori]) != array_on_edge[ori]:
                        raise PRGAAPIError("Edge incompatible")
            # cool, check passed. Now process the instantiation
            i = ModuleUtils.instantiate(self._module, model,
                    uno(name, 't_ix{}y{}'.format(*position)),
                    key = position)
            for x, y in product(range(model.width), range(model.height)):
                offset = Position(x, y)
                sub_on_edge = OrientationTuple(
                        north = y == model.height - 1,
                        east = x == model.width - 1,
                        south = y == 0,
                        west = x == 0)
                if not (sub_on_edge.west and sub_on_edge.south):
                    self._module._instances[position + offset] = offset
                for corner in Corner:
                    if model.module_class.is_array or all(not sub_on_edge[ori] for ori in corner.decompose()):
                        self._module._instances[position + offset, corner] = offset
            return i
        else:
            raise PRGAAPIError("Cannot instantiate {} of class {} in array {}"
                    .format(model, model.module_class.name, self._module))

    def fill(self, sbox_pattern = SwitchBoxPattern.wilton, *,
            identifier = None, dont_create = False, dont_update = False):
        """Automatically create switch box connections using switch box patterns.

        Args:
            sbox_pattern (`SwitchBoxPattern`):

        Keyword Args:
            identifier (:obj:`str`): Used to differentiate the switch boxes
            dont_create (:obj:`bool`): If set to ``True``, only existing switch box instances are to be filled. No new
                instances are created
            dont_update (:obj:`bool`): If set to ``True``, existing switch box instances are not updated

        Returns:
            `ArrayBuilder`: Return ``self`` to support chaining, e.g.,
                ``array = builder.fill().auto_connect().commit()``
        """
        processed_boxes = set()
        for x, y in product(range(self._module.width), range(self._module.height)):
            position = Position(x, y)
            for corner in sbox_pattern.fill_corners:
                if any(ori.case(y == self.height - 1, x == self.width - 1, y == 0, x == 0) and self._module.edge[ori]
                        for ori in corner.decompose()):
                    continue
                elif (instance := self._module._instances.get_root(position, corner)) is None:
                    if dont_create:
                        continue
                elif not instance.model.module_class.is_switch_box or dont_update:
                    continue
                # analyze the environment around the switch box
                outputs = {}    # orientation -> drive_at_crosspoints, crosspoints_only
                curpos, curcorner = position, corner
                while True:
                    # primary output
                    primary_output = Orientation[curcorner.case("south", "east", "west", "north")]
                    if not self._no_channel_for_switchbox(self._module, curpos, curcorner, primary_output, True):
                        drivex, _ = outputs.get(primary_output, (False, False))
                        drivex = drivex or self._no_channel_for_switchbox(self._module, curpos, curcorner,
                                primary_output)
                        outputs[primary_output] = drivex, False
                    # secondary output: when the switch box supposed to drive certain segments is not fullfiling
                    # its job
                    secondary_output = primary_output.opposite
                    if (not self._no_channel_for_switchbox(self._module, curpos, curcorner, secondary_output, True)
                            and self._no_channel_for_switchbox(self._module, curpos, curcorner, secondary_output)):
                        otherpos, othercorner = self._equiv_sbox_position(curpos, curcorner,
                                Corner[secondary_output.case("southwest", "northwest", "northeast", "southeast")])
                        if (not (0 <= otherpos.x < self.width and 0 <= otherpos.y < self.height) or
                                ((i := self._module._instances.get_root(otherpos, othercorner)) is not None and
                                    not i.model.module_class.is_switch_box)):
                            _, xo = outputs.get(secondary_output, (True, True))
                            outputs[secondary_output] = True, xo
                    # go to the next corner
                    curpos, curcorner = self._equiv_sbox_position(curpos, curcorner)
                    # check if we've gone through all corners
                    if curcorner in sbox_pattern.fill_corners:
                        break
                if len(outputs) == 0:
                    continue
                # analyze excluded inputs
                excluded_inputs = set(ori for ori in Orientation
                        if self._no_channel_for_switchbox(self._module, position, corner, ori))
                if len(excluded_inputs) == 4:
                    continue
                # if the instance is not there, create new switch box and instantiate there
                if instance is None:
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
                    sbox = self._context.build_switch_box(corner, identifier = sbox_identifier).module
                    instance = self.instantiate(sbox, position)
                if instance.model.key not in processed_boxes:
                    builder = SwitchBoxBuilder(self._context, instance.model)
                    for output, (drivex, xo) in iteritems(outputs):
                        builder.fill(output, drive_at_crosspoints = drivex, crosspoints_only = xo,
                                exclude_input_orientations = excluded_inputs, pattern = sbox_pattern)
                    processed_boxes.add(instance.model.key)
        return self

    def auto_connect(self, *, is_top = None):
        """Automatically connect submodules.

        Keyword Args:
            is_top (:obj:`bool`): If set to ``True``, the array is treated as if it is the top-level array. This
                affects if unconnected routing nodes are exposed as ports. If not set, this method checks the
                ``context`` to see if the module being built is the top-level array

        Returns:
            `ArrayBuilder`: Return ``self`` to support chaining, e.g.,
                ``array = builder.fill().auto_connect().commit()``
        """
        is_top = self._module is self._context.top if is_top is None else is_top
        # 1st pass: auto-connect all sub-arrays
        auto_connected = set()
        for pos in product(range(self._module.width), range(self._module.height)):
            # 1. check out the instance
            if (instance := self._module.instances.get( pos )) is None:
                continue
            # 2. auto-connect
            elif instance.model.module_class.is_array and instance.model.key not in auto_connected:
                auto_connected.add( instance.model.key )
                type(self)(self._context, instance.model).auto_connect(is_top = False)
        # 2nd pass: connect routing nodes
        for key, instance in iteritems(self._module.instances):
            try:
                (x, y), corner = key
            except TypeError:
                (x, y), corner = key, None
            # if the instance is a tile/array, process global wires
            if corner is None:
                for pin in itervalues(instance.pins):
                    if (global_ := getattr(pin.model, "global_", None)) is not None:
                        self.connect(self._get_or_create_global_input(self._module, global_), pin)
            # process routing nodes
            snapshot = tuple(iteritems(instance.pins))
            for node, pin in snapshot:
                if isinstance(node, BridgeID):              # bridges
                    if node.bridge_type.is_regular_input:
                        args = self._prepare_segment_driver_search(pin)
                        drivers = tuple(self._find_segment_drivers(self._module, *args))
                        if len(drivers) > 1:
                            raise PRGAInternalError(
                                    "\n".join([
                                        "Multiple candidate drivers found for node {}:".format(args[0]), ] +
                                        ["\t{}".format(driver) for driver in drivers]))
                        elif len(drivers) == 1:
                            NetUtils.connect(self._expose_node(drivers[0]), pin)
                        elif not is_top:
                            self._expose_node(pin, create_port = True)
                    elif ((node.bridge_type.is_cboxout or node.bridge_type.is_cboxout2) and
                            pin.model.direction.is_output):
                        self._connect_cboxout(self._module, pin, create_port = not is_top)
                elif isinstance(node, BlockPinID) and pin.model.direction.is_input:
                    tile_pos = node.position + (x, y) - node.prototype.position 
                    if (tile := self.get_hierarchical_root(self._module, tile_pos)) is not None:
                        src_node = node.move(-self.hierarchical_position(tile) + (x, y))
                        if (driver := tile.pins.get(src_node)) is None:
                            if (blk := tile.model.instances.get(node.subtile)) is None:
                                continue
                            elif blk.model is not node.prototype.parent:
                                continue
                            port = TileBuilder._expose_blockpin(blk.pins[node.prototype.key])
                            driver = tile.pins[port.key]
                        self.connect(self._expose_node(driver), pin)
                    elif not is_top and not (0 <= tile_pos.x < self.width and 0 <= tile_pos.y < self.height):
                        self._expose_node(pin, create_port = True)
        return self
