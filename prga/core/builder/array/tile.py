# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseArrayBuilder
from ..box.cbox import ConnectionBoxBuilder
from ...common import Orientation, OrientationTuple, ModuleView, ModuleClass, Position, BlockFCValue
from ....netlist.module.module import Module
from ....netlist.module.instance import Instance
from ....netlist.module.util import ModuleUtils
from ....util import Object, uno

__all__ = ['TileBuilder']

# ----------------------------------------------------------------------------
# -- Tile Instance Mapping ---------------------------------------------------
# ----------------------------------------------------------------------------
class _TileInstancesMapping(Object, MutableMapping):
    """Helper class for ``Tile.instances`` property.

    Args:
        width (:obj:`int`): Width of the tile/array
        height (:obj:`int`): Height of the tile/array

    Supported key types:
        :obj:`int`: Index of a subtile
        :obj:`tuple` [:obj:`Orientation`, :obj:`int` ]: Orientation of the connection box and the offset
    """

    __slots__ = ["cboxes", "subtiles"]
    def __init__(self, width, height):
        self.cboxes = OrientationTuple(north = [None] * width, east = [None] * height,
                south = [None] * width, west = [None] * height)
        self.subtiles = []

    def __getitem__(self, key):
        try:
            ori, offset = key
            try:
                if self.cboxes[ori][offset] is not None:
                    return self.cboxes[ori][offset]
                else:
                    raise KeyError(key)
            except IndexError:
                raise KeyError(key)
        except TypeError:
            try:
                return self.subtiles[key]
            except (IndexError, TypeError):
                raise KeyError(key)

    def __setitem__(self, key, value):
        try:
            ori, offset = key
            try:
                if self.cboxes[ori][offset] is None:
                    self.cboxes[ori][offset] = value
                else:
                    raise PRGAInternalError("Connection box position ({}, {}) already occupied by {}"
                            .format(ori, offset, self.cboxes[ori][offset]))
            except IndexError:
                raise PRGAInternalError("Invalid connection box position: ({}, {})"
                        .format(ori, offset))
        except TypeError:
            if key < len(self.subtiles):
                raise PRGAInternalError("Subtile {} already occupied by {}".format(key, self.subtiles[key])) 
            elif key > len(self.subtiles):
                raise PRGAInternalError("Invalid subtile ID: {}".format(key))
            self.subtiles.append( value )

    def __delitem__(self, key):
        raise PRGAInternalError("Deleting from a tile instances mapping is not supported")

    def __len__(self):
        return len(self.subtiles) + sum(1 for l in self.cboxes for i in l if i is not None)

    def __iter__(self):
        for i in range(len(self.subtiles)):
            yield i
        for ori in Orientation:
            for offset, instance in enumerate(self.cboxes[ori]):
                if instance is not None:
                    yield ori, offset

# ----------------------------------------------------------------------------
# -- Tile Builder ------------------------------------------------------------
# ----------------------------------------------------------------------------
class TileBuilder(BaseArrayBuilder):
    """Tile builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    # == high-level API ======================================================
    @classmethod
    def new(cls, name, width, height, *,
            disallow_segments_passthru = False,
            edge = OrientationTuple(False),
            **kwargs):
        """Create a new tile.

        Args:
            name (:obj:`str`): Name of the tile
            width (:obj:`int`): Width of the tile
            height (:obj:`int`): Height of the tile

        Keyword Args:
            disallow_segments_passthru (:obj:`bool`): If set to ``True``, segments are not allowed to run over the
                tile
            edge (`OrientationTuple` [:obj:`bool` ]): Marks this tile to be on the specified edges of the top-level
                array. This affects segment instantiation.
            **kwargs: Additional attributes assigned to the tile

        Returns:
            `Module`:
        """
        return Module(name,
                view = ModuleView.user,
                instances = _TileInstancesMapping(width, height),
                coalesce_connections = True,
                module_class = ModuleClass.tile,
                width = width,
                height = height,
                disallow_segments_passthru = disallow_segments_passthru,
                edge = edge,
                **kwargs)

    def instantiate(self, model, reps = None, *, name = None, **kwargs):
        """Instantiate ``model`` in the tile.

        Args:
            model (`Module`): User view of a logic/IO block to be instantiated
            reps (:obj:`int`): If set to a positive int, the specified number of instances are created, added to
                the tile, and returned. This affects the `capacity`_ attribute in the output VPR specs

        Keyword Args:
            name (:obj:`str`): Name of the instance. If not specified, ``"lb_i{subtile_id}"`` is used by default. If
                ``reps`` and ``name`` are both specified, each instance is then named ``"{name}_i{index}"``.
            **kwargs: Additional attributes assigned to each instance

        Returns:
            `Instance` or :obj:`tuple` [`Instance`]:

        .. capacity:
            https://docs.verilogtorouting.org/en/latest/arch/reference/#tag-%3Csub_tilename
        """
        if not model.module_class.is_block:
            raise PRGAInternalError("{} is not a logic/IO block".format(model))
        elif not (model.width == self._module.width and model.height == self._module.height):
            raise PRGAInternalError("The size of block {} ({}x{}) does not fit the size of tile {} ({}x{})"
                    .format(model, model.width, model.height, self._module, self._module.width, self._module.height))
        subtile = len(self._module._instances.subtiles)
        if reps is None:
            return ModuleUtils.instantiate(self._module, model, uno(name, "lb_i{}".format(subtile)), key = subtile)
        elif name is None:
            return tuple(ModuleUtils.instantiate(self._module, model, "lb_i{}".format(subtile + i),
                key = subtile + i, vpr_capacity = reps, vpr_subtile = i) for i in range(reps))
        else:
            return tuple(ModuleUtils.instantiate(self._module, model, "{}_i{}".format(name, i),
                key = subtile + i, vpr_capacity = reps, vpr_subtile = i) for i in range(reps))

    def build_connection_box(self, ori, offset, **kwargs):
        """Build the connection box at the specific position. Corresponding connection box instance is created and
        added to this tile if it's not already added into the tile.

        Args:
            ori (`Orientation`): Orientation of the connection box
            offset (:obj:`int`): Offset of the connection box in the specified orientation

        Keyword Args:
            **kwargs: Additional attributes assigned to the connection box module
        
        Returns:
            `ConnectionBoxBuilder`:

        Note:
            Connection boxes are indexed as the following:

            .. code-block:: python
                    0   1   2   3
                  +---------------+
                2 |     north     | 2
                1 | west     east | 1
                0 |     south     | 0
                  +---------------+
                    0   1   2   3
        """
        if (inst := self._module.instances.get( (ori, offset) )) is None:
            key = ConnectionBoxBuilder._cbox_key(self._module, ori, offset)
            if self._no_channel(self._module, key.position, ori):
                raise PRGAAPIError("No connection box allowed at ({}, {}) in tile {}"
                        .format(ori, offset, self._module))
            try:
                box = self._context.database[ModuleView.user, key]
                for k, v in iteritems(kwargs):
                    setattr(box, k, v)
            except KeyError:
                box = self._context._database[ModuleView.user, key] = ConnectionBoxBuilder.new(
                        self._module, ori, offset, **kwargs)
            inst = ModuleUtils.instantiate(self._module, box, "cb_i_{}{}".format(ori.name[0], offset),
                    key = (ori, offset))
        return ConnectionBoxBuilder(self._context, inst.model)

    def fill(self, default_fc, *, fc_override = None):
        """Fill connection boxes in the array.

        Args:
            default_fc: Default FC value for all blocks whose FC value is not defined. If one single :obj:`int` or
                :obj:`float` is given, this FC value applies to all ports of all blocks. If a :obj:`tuple` of two
                :obj:`int`s or :obj:`float`s are given, the first one applies to all input ports while the second one
                applies to all output ports. Use `BlockFCValue` for more custom options.

        Keyword Args:
            fc_override (:obj:`Mapping`): Override the FC settings for specific blocks. Indexed by block key.
        """
        # process FC values
        default_fc = BlockFCValue._construct(default_fc)
        fc_override = {k: BlockFCValue._construct(v) for k, v in iteritems(uno(fc_override, {}))}
        for tunnel in itervalues(self._context.tunnels):
            for port in (tunnel.source, tunnel.sink):
                fc = fc_override.setdefault(port.parent.key, BlockFCValue(default_fc.default_in, default_fc.default_out))
                fc.overrides[port.key] = BlockPortFCValue(0)
        # connection boxes
        for ori in Orientation:
            for offset in range(ori.dimension.case(x = self._module.height, y = self._module.width)):
                # check if a connection box instance is already here
                if (ori, offset) in self._module.instances:
                    continue
                pos = ConnectionBoxBuilder._cbox_key(self._module, ori, offset).position
                # check if a connection box is needed here
                # 1. channel?
                if self._no_channel(self._module, pos, ori):
                    continue
                # 2. port?
                cbox_needed = False
                blocks_checked = set()
                for instance in self._module._instances.subtiles:
                    if instance.model.key in blocks_checked:
                        continue
                    blocks_checked.add(instance.model.key)
                    for port in itervalues(instance.model.ports):
                        if port.position != pos or port.orientation is not ori:
                            continue
                        elif hasattr(port, 'global_'):
                            continue
                        elif any(fc_override.get(instance.model.key, default_fc).port_fc(port, sgmt)
                                for sgmt in itervalues(self._context.segments)):
                            cbox_needed = True
                            break
                    if cbox_needed:
                        break
                if not cbox_needed:
                    continue
                # ok, connection box is needed. create and fill
                builder = self.build_connection_box(ori, offset)
                builder.fill(default_fc, fc_override = fc_override)

    def auto_connect(self):
        """Automaticaly connect submodules."""
        # regular nets
        for ori in Orientation:
            for offset in range(ori.dimension.case(x = self._module.height, y = self._module.width)):
                if (box := self.instances.get( (ori, offset) )) is None:
                    continue
                for node, box_pin in iteritems(box.pins):
                    box_pin_conn = None
                    if node.node_type.is_block:
                        pin_pos, port, subtile = node
                        if (block_pos := box.model.key.position + pin_pos - port.position) == (0, 0):
                            box_pin_conn = self.instances[subtile].pins[port.key]
                        elif 0 <= block_pos.x < self._module.width and 0 <= block_pos.y < self._module.height:
                            continue
                    elif not node.node_type.is_bridge:
                        continue
                    if box_pin_conn is None:
                        node = node.move(box.model.key.position)
                        if (box_pin_conn := self._module.ports.get(node)) is None:
                            box_pin_conn = ModuleUtils.create_port(self._module, self._node_name(node),
                                    len(box_pin), box_pin.model.direction, key = node)
                    if box_pin.model.direction.is_input:
                        self.connect(box_pin_conn, box_pin)
                    else:
                        self.connect(box_pin, box_pin_conn)
        # TODO: direct tunnels
