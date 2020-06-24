# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import BaseRoutingBoxBuilder
from ...common import (Position, BridgeID, BridgeType, BlockFCValue, ModuleView, ModuleClass, BlockPinID, Direction,
        Orientation, Dimension, BlockPortFCValue)
from ....algorithm.interconnect import InterconnectAlgorithms
from ....netlist.net.common import PortDirection
from ....netlist.module.module import Module
from ....netlist.module.util import ModuleUtils
from ....exception import PRGAAPIError, PRGAInternalError
from ....util import uno

from collections import namedtuple
from itertools import product

__all__ = ["ConnectionBoxBuilder"]

# ----------------------------------------------------------------------------
# -- Connection Box Key ------------------------------------------------------
# ----------------------------------------------------------------------------
class _ConnectionBoxKey(namedtuple('_ConnectionBoxKey', 'tile orientation offset')):
    """Connection box key.

    Args:
        tile (`Module`): The tile which this connection box is in
        orientation (`Orientation`): On which side of the tile is the connection box
        offset (:obj:`int`): Offset of the connection box on the specified edge
    """

    def __hash__(self):
        return hash( (self.tile.key, self.orientation, self.offset) )

    @property
    def position(self):
        """`Position`: Position of this connection box in the tile."""
        return Position(self.orientation.case(default = self.offset, west = 0, east = self.tile.width - 1),
                self.orientation.case(default = self.offset, south = 0, north = self.tile.height - 1))

    @property
    def channel(self):
        """:obj:`tuple` [`Position`, `Dimension` ]: The channel that is occupied by this connection box."""
        if self.orientation.is_north:
            return self.position, Dimension.x
        elif self.orientation.is_south:
            return self.position - (0, 1), Dimension.x
        elif self.orientation.is_west:
            return self.position - (1, 0), Dimension.y
        elif self.orientation.is_east:
            return self.position, Dimension.y
        else:
            raise PRGAInternalError("Unknown orientation: {:r}".format(self.orientation))

# ----------------------------------------------------------------------------
# -- Connection Box Builder --------------------------------------------------
# ----------------------------------------------------------------------------
class ConnectionBoxBuilder(BaseRoutingBoxBuilder):
    """Connection box builder.

    Args:
        context (`Context`): The context of the builder
        module (`Module`): The module to be built
    """

    # == internal API ========================================================
    @classmethod
    def _segment_relative_position(self, cbox_ori, segment, segment_ori, section = 0):
        if not (0 <= section < segment.length):
            raise PRGAAPIError("Section '{}' does not exist in segment '{}'"
                    .format(section, segment))
        if cbox_ori.dimension.is_y:
            if segment_ori.is_east:
                return (-section, cbox_ori.case(north = 0, south = -1))
            elif segment_ori.is_west:
                return ( section, cbox_ori.case(north = 0, south = -1))
        else:
            if segment_ori.is_north:
                return (cbox_ori.case(west = -1, east = 0), -section)
            elif segment_ori.is_south:
                return (cbox_ori.case(west = -1, east = 0),  section)
        raise PRGAAPIError("Section {} of segment '{}' going {} does not go through cbox '{}'"
                .format(section, segment, segment_ori.name, self._module))

    @classmethod
    def _cbox_key(cls, tile, orientation, offset = None):
        if offset is None:
            if orientation.dimension.case(x = tile.height == 1, y = tile.width == 1):
                offset = 0
            else:
                raise PRGAAPIError("'offset' is required because tile {} is larger than 1x1".format(tile))
        return _ConnectionBoxKey(tile, orientation, offset)

    # == high-level API ======================================================
    def get_segment_input(self, segment, orientation, section = 0, *, dont_create = False):
        """Get or create a segment input port in this connection box.

        Args:
            segment (`Segment`): Prototype of the segment
            orientation (`Orientation`): Orientation of the segment
            section (:obj:`int`): Section of the segment

        Keyword Args:
            dont_create (:obj:`bool`): If set, return ``None`` when the requested segment input is not already created

        Returns:
            `Port`:
        """
        node = BridgeID(self._segment_relative_position(self._module.key.orientation, segment, orientation, section),
                segment, orientation, BridgeType.regular_input)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        segment.width, PortDirection.input_, key = node)

    def get_segment_output(self, segment, orientation, *, dont_create = False):
        """Get or create a segment output port in this connection box.

        Args:
            segment (`Segment`): Prototype of the segment
            orientation (`Orientation`): Orientation of the segment

        Keyword Args:
            dont_create (:obj:`bool`): If set, return ``None`` when the requested segment output is not already created

        Returns:
            `Port`:
        """
        node = BridgeID(self._segment_relative_position(self._module.key.orientation, segment, orientation, 0),
                segment, orientation, BridgeType.cboxout)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        segment.width, PortDirection.output, key = node)

    def get_blockpin(self, pin, *, dont_create = False):
        """Get or create a blockpin input/output port in this connection box.

        Args:
            pin (`Pin`): Pin of a block instance in the tile that this connection box is in

        Keyword Args:
            dont_create (:obj:`bool`): If set, return ``None`` when the requested block pin is not already created

        Returns:
            `Port`:
        """
        tile, orientation, offset = self._module.key
        if pin.parent is not tile:
            raise PRGAAPIError("{} is not a pin in {}".format(pin, tile))
        elif not pin.instance.model.module_class.is_block:
            raise PRGAAPIError("{} is not a block pin".format(pin))
        prototype, subtile = pin.model, pin.instance.key
        if prototype.orientation not in (None, orientation):
            raise PRGAAPIError("'{}' faces {} but connection box '{}' is on the {} side of '{}'"
                    .format(pin, prototype.orientation.name, self._module, orientation.name, tile))
        elif prototype.position != self._module.key.position:
            raise PRGAAPIError("'{}' is at {} but connection box '{}' is at {} of '{}'"
                    .format(pin, prototype.position, self._module, self._module.key.position, tile))
        node = BlockPinID(Position(0, 0), prototype, subtile)
        try:
            return self.ports[node]
        except KeyError:
            if dont_create:
                return None
            else:
                return ModuleUtils.create_port(self._module, self._node_name(node),
                        len(pin), prototype.direction.opposite, key = node)

    def fill(self,
            default_fc,
            *,
            fc_override = None,
            dont_create = False):
        """Automatically create port-segment connections using FC values.
        
        Args:
            default_fc: Default FC value for all blocks whose FC value is not defined. If one single :obj:`int` or
                :obj:`float` is given, this FC value applies to all ports of all blocks. If a :obj:`tuple` of two
                :obj:`int`s or :obj:`float`s are given, the first one applies to all input ports while the second one
                applies to all output ports. Use `BlockFCValue` for more custom options.

        Keyword Args:
            fc_override (:obj:`Mapping`): Override the FC settings for specific blocks. Indexed by block key.
            dont_create (:obj:`bool`): If set, connections are made only between already created nodes
        """
        # process FC values
        default_fc = BlockFCValue._construct(default_fc)
        fc_override = {k: BlockFCValue._construct(v) for k, v in iteritems(uno(fc_override, {}))}
        for tunnel in itervalues(self._context.tunnels):
            for port in (tunnel.source, tunnel.sink):
                fc = fc_override.setdefault(port.parent.key, BlockFCValue(default_fc.default_in, default_fc.default_out))
                fc.overrides[port.key] = BlockPortFCValue(0)
        tile, orientation, offset = self._module.key
        # iterate through segment types
        for sgmt in itervalues(self._context.segments):
            itracks = tuple(product(range(sgmt.width), range(sgmt.length)))
            iutil = [0] * len(itracks)
            otracks = tuple(range(sgmt.width))
            outil = [0] * len(otracks)
            # iterate through instances in the tile
            for instance in tile._instances.subtiles:
                # iterate through pins
                for pin in itervalues(instance.pins):
                    if hasattr(pin.model, "global_"):
                        continue
                    elif not (pin.model.position == self._module.key.position and pin.model.orientation in (orientation, None)):
                        continue
                    blockpin = self.get_blockpin(pin, dont_create = dont_create)
                    fc = fc_override.get(instance.model.key, default_fc)
                    if pin.model.direction.is_input:
                        for ti, pi in InterconnectAlgorithms.crossbar(
                                len(itracks), len(pin), fc.port_fc(pin.model, sgmt, True), n_util = iutil):
                            idx, section = itracks[ti]
                            for sgmt_dir in Direction:
                                sgmt_i = self.get_segment_input(sgmt,
                                        Orientation.compose(orientation.dimension.perpendicular, sgmt_dir),
                                        section, dont_create = dont_create)
                                if blockpin is not None and sgmt_i is not None:
                                    self.connect(sgmt_i[idx], blockpin[pi])
                    else:
                        for ti, pi in InterconnectAlgorithms.crossbar(
                                len(otracks), len(pin), fc.port_fc(pin.model, sgmt, False), n_util = outil):
                            idx = otracks[ti]
                            for sgmt_dir in Direction:
                                sgmt_o = self.get_segment_output(sgmt,
                                        Orientation.compose(orientation.dimension.perpendicular, sgmt_dir),
                                        dont_create = dont_create)
                                if blockpin is not None and sgmt_o is not None:
                                    self.connect(blockpin[pi], sgmt_o[idx])
 
    @classmethod
    def new(cls, tile, orientation, offset = None, *, name = None, **kwargs):
        """Create a new connection box in user view at a specific location in ``tile``.
        
        Args:
            tile (`Module`): The tile that this connection box is in
            orientation (`Orientation`): On which side of the tile is the connection box
            offset (:obj:`int`): Offset of the connection box in the specified orientation

        Keyword Args:
            name (:obj:`str`): Name of the connection box. If not specified, the box is named
                ``"cbox_{tile.name}_{orientation}{offset}"``
            **kwargs: Additional attributes assigned to the connection box. Beware that these
                attributes are **NOT** carried over to the logical view automatically generated by `TranslationPass`

        Return:
            `Module`:
        """
        key = cls._cbox_key(tile, orientation, offset)
        _, orientation, offset = key
        name = name or 'cbox_{}_{}{}'.format(tile.name, orientation.name[0], offset)
        return Module(name,
                view = ModuleView.user,
                is_cell = True,
                module_class = ModuleClass.connection_box,
                key = key,
                **kwargs)
