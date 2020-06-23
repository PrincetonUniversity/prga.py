# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseArrayBuilder
from ..box.sbox import SwitchBoxBuilder
from ...common import (Corner, Position, OrientationTuple, SwitchBoxPattern, ModuleView, ModuleClass, Orientation,
        BridgeID)
from ....netlist.net.util import NetUtils
from ....netlist.module.instance import Instance
from ....netlist.module.module import Module
from ....netlist.module.util import ModuleUtils
from ....util import Object, uno
from ....exception import PRGAInternalError, PRGAAPIError

from itertools import product

__all__ = ['LeafArrayBuilder']

# ----------------------------------------------------------------------------
# -- Leaf Array Instance Mapping ---------------------------------------------
# ----------------------------------------------------------------------------
class _LeafArrayInstancesMapping(Object, MutableMapping):
    """Helper class for ``LeafArray.instances`` property.

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

    def __getitem__(self, key):
        try:
            (x, y), corner = key
            try:
                if isinstance((i := self.sboxes[x][y][corner]), Instance):
                    return i
            except (IndexError, TypeError):
                pass
            raise KeyError(key)
        except TypeError:
            pass
        try:
            x, y = key
            try:
                if isinstance((i := self.tiles[x][y]), Instance):
                    return i
            except (IndexError, TypeError):
                pass
        except TypeError:
            pass
        raise KeyError(key)

    def __setitem__(self, key, value):
        try:
            (x, y), corner = key
            try:
                if self.sboxes[x][y][corner] is None:
                    self.sboxes[x][y][corner] = value
                    return
                else:
                    raise PRGAInternalError("Switch box position ({}, {}, {:r}) already occupied"
                            .format(x, y, corner))
            except (IndexError, TypeError):
                raise PRGAInternalError("Invalid switch box position ({}, {}, {:r})"
                        .format(x, y, corner))
        except TypeError:
            pass
        try:
            x, y = key
            try:
                if self.tiles[x][y] is None:
                    self.tiles[x][y] = value
                    return
                else:
                    raise PRGAInternalError("Tile position ({}, {}) already occupied"
                            .format(x, y))
            except (IndexError, TypeError):
                raise PRGAInternalError("Invalid tile position ({}, {})"
                        .format(x, y))
        except TypeError:
            raise PRGAInternalError("Invalid key: {:r}".format(key))

    def __delitem__(self, key):
        raise PRGAInternalError("Deleting from a tile instances mapping is not supported")

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
# -- Leaf Array Builder ------------------------------------------------------
# ----------------------------------------------------------------------------
class LeafArrayBuilder(BaseArrayBuilder):
    """Leaf array builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    # == high-level API ======================================================
    @classmethod
    def new(cls, name, width, height, *, edge = OrientationTuple(False), **kwargs):
        """Create a new leaf array.
        
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
                instances = _LeafArrayInstancesMapping(width, height),
                coalesce_connections = True,
                module_class = ModuleClass.leaf_array,
                width = width,
                height = height,
                edge = edge,
                **kwargs)

    def instantiate(self, model, position, *, name = None, **kwargs):
        """Instantiate ``model`` at the specified position in the array.

        Args:
            model (`Module`): A tile or a switch box
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of the tile/switch box

        Keyword Args:
            name (:obj:`str`): Name of the instance. By default, ``"t_x{x}y{y}"`` is used for tile instances and
                ``"sb_x{x}y{t}{corner}"`` is used for switch box instances
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
        elif model.module_class.is_tile:
            # A bit more complex case: instantiating tile
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
                    if any(sub_on_edge[ori] for ori in corner.decompose()):
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
                    uno(name, 't_x{}y{}'.format(*position)),
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
                    if all(not sub_on_edge[ori] for ori in corner.decompose()):
                        self._module._instances[position + offset, corner] = offset
            return i
        else:
            raise PRGAAPIError("Cannot instantiate {} of class {} in leaf array {}"
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
        """
        processed_boxes = set()
        for x, y in product(range(self._module.width), range(self._module.height)):
            position = Position(x, y)
            for corner in sbox_pattern.fill_corners:
                if (instance := self._module._instances.get_root(position, corner)) is None:
                    if dont_create:
                        continue
                elif not instance.model.module_class.is_switch_box:
                    continue
                # analyze the environment around the switch box
                outputs = {}    # orientation -> drive_at_crosspoints, crosspoints_only
                curpos, curcorner = position, corner
                while True:
                    # primary output
                    primary_output = Orientation[curcorner.case("south", "east", "west", "north")]
                    if not self._no_channel_for_switchbox(self._module, curpos, curcorner, primary_output, True):
                        drivex, _ = outputs.get(primary_output, (False, False))
                        drivex = drivex or self._no_channel_for_switchbox(self._module, curpos, curcorner, primary_output)
                        outputs[primary_output] = drivex, False
                    # secondary output: only effective on switch-boxes driving wire segments going out 
                    secondary_output = primary_output.opposite
                    if ( secondary_output.case( curpos.y == self._module.height - 1,
                        curpos.x == self._module.width - 1, curpos.y == 0, curpos.x == 0) and
                        self._no_channel_for_switchbox(self._module, curpos, curcorner, secondary_output)
                        ):
                        _, xo = outputs.get(secondary_output, (True, True))
                        outputs[secondary_output] = True, xo
                    # go to the next corner
                    curpos, curcorner = self._equiv_sbox_position(curpos, curcorner)
                    # if curcorner.is_northeast:
                    #     curpos, curcorner = curpos + (0, 1), Corner.southeast
                    # elif curcorner.is_southeast:
                    #     curpos, curcorner = curpos + (1, 0), Corner.southwest
                    # elif curcorner.is_southwest:
                    #     curpos, curcorner = curpos - (0, 1), Corner.northwest
                    # else:
                    #     assert curcorner.is_northwest
                    #     curpos, curcorner = curpos - (1, 0), Corner.northeast
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

    def auto_connect(self, *, is_top = None):
        is_top = self._module is self._context.top if is_top is None else is_top
        # connect routing nodes
        for key, instance in iteritems(self._module.instances):
            try:
                (x, y), corner = key
            except TypeError:
                (x, y), corner = key, None
            # if the instance is a tile, process global wires
            if corner is None:
                # TODO: connect global wires
                pass
            # process routing nodes
            for node, pin in iteritems(instance.pins):
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
