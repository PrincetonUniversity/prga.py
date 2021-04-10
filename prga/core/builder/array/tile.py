# -*- encoding: ascii -*-

from .base import BaseArrayBuilder
from ..box import ConnectionBoxBuilder
from ...common import (Orientation, OrientationTuple, ModuleView, ModuleClass, Position, BlockFCValue, Corner,
        BlockPortFCValue, BlockPinID)
from ....netlist import Module, Instance, ModuleUtils, NetUtils
from ....util import Object, uno
from ....exception import PRGAInternalError, PRGAAPIError

__all__ = ['TileBuilder']

# ----------------------------------------------------------------------------
# -- Tile Builder ------------------------------------------------------------
# ----------------------------------------------------------------------------
class TileBuilder(BaseArrayBuilder):
    """Tile builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    @classmethod
    def _expose_blockpin(cls, pin):
        """Expose a block pin as a ``BlockPinID`` node."""
        node = BlockPinID(pin.model.position, pin.model, pin.instance.key)
        port = ModuleUtils.create_port(pin.parent, cls._node_name(node), len(pin),
                pin.model.direction, key = node)
        if port.direction.is_input:
            NetUtils.connect(port, pin)
        else:
            NetUtils.connect(pin, port)
        return port

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
                coalesce_connections = True,
                view = ModuleView.abstract,
                module_class = ModuleClass.tile,
                width = width,
                height = height,
                disallow_segments_passthru = disallow_segments_passthru,
                edge = edge,
                **kwargs)

    def instantiate(self, model, reps = None, *, name = None, **kwargs):
        """Instantiate ``model`` in the tile.

        Args:
            model (`Module`): Abstract view of a logic/IO block to be instantiated
            reps (:obj:`int`): If set to a positive int, the specified number of instances are created, added to
                the tile, and returned. This affects the `capacity`_ attribute in the output VPR specs

        Keyword Args:
            name (:obj:`str`): Name of the instance. If not specified, ``"lb_i{subtile_id}"`` is used by default. If
                ``reps`` and ``name`` are both specified, each instance is then named ``"{name}_i{index}"``.
            **kwargs: Additional attributes assigned to each instance

        Returns:
            `Instance` or :obj:`tuple` [`Instance` ]:

        .. _capacity:
            https://docs.verilogtorouting.org/en/latest/arch/reference/#tag-%3Csub\_tilename
        """
        if not model.module_class.is_block:
            raise PRGAInternalError("{} is not a logic/IO block".format(model))
        elif not (model.width == self._module.width and model.height == self._module.height):
            raise PRGAInternalError("The size of block {} ({}x{}) does not fit the size of tile {} ({}x{})"
                    .format(model, model.width, model.height, self._module, self._module.width, self._module.height))
        elif 0 in self._module.instances:
            raise PRGAAPIError("At most one type of subtile per tile. {} is already instantiated in {}"
                    .format(self._module.instances[0].model, self._module))
        if reps is None:
            return ModuleUtils.instantiate(self._module, model, uno(name, "i_blk"), key = 0)
        else:
            return tuple(ModuleUtils.instantiate(self._module, model, "{}_i{}".format(uno(name, "i_blk"), i),
                key = i, vpr_capacity = reps, vpr_subtile = i) for i in range(reps))

    def build_connection_box(self, ori, offset, **kwargs):
        """Build the connection box at the specific position. Corresponding connection box instance is created and
        added to this tile if it's not already added into the tile.

        Args:
            ori (`Orientation` or :obj:`str`): Orientation of the connection box
            offset (:obj:`int`): Offset of the connection box in the specified orientation

        Keyword Args:
            **kwargs: Additional attributes assigned to the connection box module
        
        Returns:
            `ConnectionBoxBuilder`:

        Note:
            Connection boxes are indexed as the following::

                    0   1   2   3
                  +---------------+
                2 |     north     | 2
                1 | west     east | 1
                0 |     south     | 0
                  +---------------+
                    0   1   2   3
        """
        ori = Orientation.construct(ori)

        if (inst := self._module.instances.get( (ori, offset) )) is None:
            key = ConnectionBoxBuilder._cbox_key(self._module, ori, offset)
            if self._no_channel(self._module, *key.channel):
                raise PRGAAPIError("No connection box allowed at ({}, {}) in tile {}"
                        .format(ori, offset, self._module))
            try:
                box = self._context.database[ModuleView.abstract, key]
                for k, v in kwargs.items():
                    setattr(box, k, v)
            except KeyError:
                box = self._context._database[ModuleView.abstract, key] = ConnectionBoxBuilder.new(
                        self._module, ori, offset, **kwargs)
            inst = ModuleUtils.instantiate(self._module, box, "i_cbox_{}{}".format(ori.name[0], offset),
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

        Returns:
            `TileBuilder`: Return ``self`` to support chaining, e.g.,
                ``array = builder.fill().auto_connect().commit()``
        """
        # process FC values
        default_fc = BlockFCValue._construct(default_fc)
        fc_override = {k: BlockFCValue._construct(v) for k, v in uno(fc_override, {}).items()}
        for tunnel in self._context.tunnels.values():
            for port in (tunnel.source, tunnel.sink):
                fc = fc_override.setdefault(port.parent.key, BlockFCValue(default_fc.default_in, default_fc.default_out))
                fc.overrides[port.key] = BlockPortFCValue(0)
        # connection boxes
        for ori in Orientation:
            for offset in range(ori.dimension.case(x = self._module.height, y = self._module.width)):
                # check if a connection box instance is already here
                if (ori, offset) in self._module.instances:
                    continue
                boxkey = ConnectionBoxBuilder._cbox_key(self._module, ori, offset)
                # check if a connection box is needed here
                # 1. channel?
                if self._no_channel(self._module, *boxkey.channel):
                    continue
                # 2. port?
                cbox_needed = False
                blocks_checked = set()
                for key, instance in self._module.instances.items():
                    if not isinstance(key, int) or instance.model.key in blocks_checked:
                        continue
                    blocks_checked.add(instance.model.key)
                    for port in instance.model.ports.values():
                        if port.position != boxkey.position or port.orientation not in (ori, None):
                            continue
                        elif hasattr(port, 'global_'):
                            continue
                        elif any(fc_override.get(instance.model.key, default_fc).port_fc(port, sgmt)
                                for sgmt in self._context.segments.values()):
                            cbox_needed = True
                            break
                    if cbox_needed:
                        break
                if not cbox_needed:
                    continue
                # ok, connection box is needed. create and fill
                builder = self.build_connection_box(ori, offset)
                builder.fill(default_fc, fc_override = fc_override)
        return self

    def auto_connect(self):
        """Automatically connect submodules.

        Returns:
            `TileBuilder`: Return ``self`` to support chaining, e.g.,
                ``array = builder.fill().auto_connect().commit()``
        """
        # two passes
        # 1. visit CBoxes and connect
        for key, instance in self._module.instances.items():
            if isinstance(key, int):
                continue
            ori, offset = key
            for node, box_pin in instance.pins.items():
                # find the correct connection
                box_pin_conn = None
                if node.node_type.is_block:
                    pin_pos, port, subtile = node
                    if (block_pos := instance.model.key.position + pin_pos - port.position) == (0, 0):
                        box_pin_conn = self.instances[subtile].pins[port.key]
                    elif ((0 <= block_pos.x < self._module.width and 0 <= block_pos.y < self._module.height)
                            or not box_pin.model.direction.is_input):
                        raise PRGAInternalError("Invalid block pin node ({})".format(box_pin))
                    else:
                        # this must be the input of a direct inter-block tunnel
                        node = node.move(instance.model.key.position)
                        box_pin_conn = ModuleUtils.create_port(self._module, self._node_name(node),
                                len(box_pin), box_pin.model.direction, key = node)
                elif node.node_type.is_bridge:
                    node = node.move(instance.model.key.position)
                    if (box_pin_conn := self._module.ports.get(node)) is None:
                        boxpos = None
                        if node.bridge_type.is_regular_input:
                            boxpos = instance.model.key.position, Corner.compose(node.orientation,
                                    instance.model.key.orientation)
                        elif node.bridge_type.is_cboxout or node.bridge_type.is_cboxout2:
                            boxpos = instance.model.key.position, Corner.compose(node.orientation.opposite,
                                    instance.model.key.orientation)
                        else:
                            raise PRGAInternalError("Not expecting node {} in tile {}"
                                    .format(node, self._module))
                        box_pin_conn = ModuleUtils.create_port(self._module, self._node_name(node),
                                len(box_pin), box_pin.model.direction, key = node, boxpos = boxpos)
                else:
                    raise PRGAInternalError("Invalid routing node ({})".format(box_pin))

                # connect
                if box_pin.model.direction.is_input:
                    self.connect(box_pin_conn, box_pin)
                else:
                    self.connect(box_pin, box_pin_conn)

        # 2. visit subblocks and connect
        for key, instance in self._module.instances.items():
            if not isinstance(key, int):
                continue
            # direct tunnels
            for tunnel in self._context.tunnels.values():
                if tunnel.sink.parent is not instance.model:
                    continue
                # find the sink pin of the tunnel
                sink = instance.pins[tunnel.sink.key]
                # check if the sink pin is already driven
                if (driver := NetUtils.get_source(sink)) is None:
                    pass
                elif driver.net_type.is_pin:
                    assert driver.instance.model.module_class.is_connection_box
                    box = driver.instance.model
                    src_node = BlockPinID(tunnel.offset, tunnel.source, key)
                    if (tunnel_src_port := box.ports.get(src_node)) is None:
                        tunnel_src_port = ModuleUtils.create_port(box, ConnectionBoxBuilder._node_name(src_node),
                                len(tunnel.source), driver.model.direction.opposite, key = src_node)
                        NetUtils.connect(tunnel_src_port, driver.model)
                    sink = driver.instance.pins[src_node]
                    if NetUtils.get_source(sink) is not None:
                        continue
                else:
                    continue
                # create the source port and connect them
                src_node = BlockPinID(tunnel.sink.position + tunnel.offset, tunnel.source, key)
                NetUtils.connect(ModuleUtils.create_port(self._module, self._node_name(src_node),
                    len(tunnel.source), tunnel.sink.direction, key = src_node), sink)

        return self
