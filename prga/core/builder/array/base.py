# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..base import BaseBuilder
from ..box.sbox import SwitchBoxBuilder
from ...common import Dimension, Position, Orientation, Corner, OrientationTuple, BridgeType
from ....netlist.net.common import PortDirection
from ....netlist.net.util import NetUtils
from ....netlist.module.util import ModuleUtils
from ....netlist.module.instance import Instance
from ....exception import PRGAInternalError
from ....util import Object

from abc import abstractmethod, abstractproperty
import logging
_logger = logging.getLogger(__name__)

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
        pos = pin.instance.key if pin.instance.model.module_class.is_array else pin.instance.key[0]
        node = pin.model.key.move(pos)
        if node.node_type.is_block:    # BLOCK PIN
            if (port := array.ports.get(node)) is not None:
                port = ModuleUtils.create_port(array, cls._node_name(node), len(pin),
                        pin.model.direction, key = node)
            source, sink = (pin, port) if port.direction.is_output else (port, pin)
            if (cur_source := NetUtils.get_source(sink, return_none_if_unconnected = True)) is None:
                NetUtils.connect(source, sink)
            elif cur_source != source:
                raise PRGAInternalError("{} already exposed but not correctly connected".format(pin))
            return port
        node = None
        if node.node_type.is_segment:  # SEGMENT
            node = node.convert(BridgeType.regular_output)
        elif node.node_type.is_bridge:
            if node.bridge_type.is_cboxout2:
                node = node.convert(BridgeType.cboxout)
        else:
            raise PRGAInternalError("Unknown node type: {:r}".format(pin.model.key.node_type))
        while (port := array.ports.get(node)) is not None:
            if port.direction is pin.model.direction:
                source, sink = (pin, port) if port.direction.is_output else (port, pin)
                if (cur_source := NetUtils.get_source(sink, return_none_if_unconnected = True)) is None:
                    NetUtils.connect(source, sink)
                    break
                elif cur_source == source:
                    break
            if node.bridge_type.is_cboxout:
                node = node.convert(BridgeType.cboxout2)
                continue
            raise PRGAInternalError("{} already exposed but not correctly connected".format(pin))
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
            if pos.x == bound.west and corner.dotx(Dimension.x).is_dec:
                return node, Position(bound.west - 1, pos.y), ordering, 1
            elif pos.x == bound.east and corner.dotx(Dimension.x).is_inc:
                return node, Position(bound.east + 1, pos.y), ordering, 1
            elif ori.is_north:
                if pos.y < bound.south:
                    return node, pos, ordering, 0
                else:
                    return node, Position(pos.x, bound.south - 1), ordering, 2
            else:
                if pos.y > bound.north:
                    return node, pos, ordering, 0
                else:
                    return node, Position(pos.x, bound.north + 1), ordering, 2
        else:
            if pos.y == bound.north and corner.dotx(Dimension.y).is_inc:
                return node, Position(pos.x, bound.north + 1), ordering, 1
            elif pos.y == bound.south and corner.dotx(Dimension.y).is_dec:
                return node, Position(pos.x, bound.south - 1), ordering, 1
            elif ori.is_east:
                if pos.x < bound.west:
                    return node, pos, ordering, 0
                else:
                    return node, Position(bound.west - 1, pos.y), ordering, 2
            else:
                if pos.x > bound.east:
                    return node, pos, ordering, 0
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
        if array.module_class.is_nonleaf_array:
            if (i := array._instances.get_root(position)) is None:
                return None
            if (sub := cls.get_hierarchical_root(i.model, position - i.key, corner)) is None:
                return None
            return sub.extend_hierarchy(above = i)
        elif array.module_class.is_leaf_array:
            return array._instances.get_root(position, corner)
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

