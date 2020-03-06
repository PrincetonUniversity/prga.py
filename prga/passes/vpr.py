# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import (Position, Subtile, Orientation, ModuleView, Dimension, BlockPinID, SegmentID, SegmentType,
        Direction, Corner)
from ..core.builder.array import NonLeafArrayBuilder
from ..netlist.net.bus import Pin
from ..netlist.net.util import NetUtils
from ..util import Object, uno
from ..xml import XMLGenerator
from ..exception import PRGAInternalError

import os
from itertools import product, chain
from collections import OrderedDict

__all__ = ['FASMDelegate', 'VPRInputsGeneration']

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class FASMDelegate(Object):
    """FASM delegate supplying FASM metadata."""

    def fasm_mux_for_intrablock_switch(self, source, sink):
        """Get the "fasm_mux" string for the connection from ``source`` to ``sink``.

        Args:
            source (`AbstractGenericNet`): Source bit
            sink (`AbstractGenericNet`): Sink bit
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_mux" features
        """
        return tuple()

    def fasm_prefix_for_intrablock_module(self, hierarchical_instance):
        """Get the "fasm_prefix" string for a hierarchical cluster/primitive instance ``hierarchical_instance``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical instance in bottom-up order in
                a block

        Returns:
            :obj:`str`: "fasm_prefix" for the module
        """
        return ''

    def fasm_features_for_mode(self, hierarchical_instance, mode):
        """Get the "fasm_features" string for multimode instance ``hierarchical_instance`` when it's configured to
        ``mode``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical multimode instance in
                bottom-up order in a block
            mode (:obj:`str`):
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_features" features to be emitted for the leaf-level multimode in the
                hierarchy
        """
        return tuple()

    def fasm_params_for_primitive(self, hierarchical_instance):
        """Get the "fasm_params" strings for primitive instance ``hierarchical_instance``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical instance in bottom-up order in
                a block

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`str` ]: "fasm_param" feature mapping for the primitive instance
        """
        return {}

    def fasm_lut(self, hierarchical_instance):
        """Get the "fasm_lut" string for LUT instance ``hierarchical_instance``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical instance in bottom-up order in
                a block

        Returns:
            :obj:`str`: "fasm_lut" feature for the LUT instance
        """
        return ''
    
    def fasm_prefix_for_tile(self, hierarchical_instance):
        """Get the "fasm_prefix" strings for the block instances in tile instance ``hierarchical_instance``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical instance in bottom-up order in
                the top-level array

        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_prefix" for the block instances
        """
        return tuple()

    def fasm_features_for_routing_switch(self, switch_input):
        """Get the "fasm_features" strings for selecting ``switch_input``.

        Args:
            switch_input (`AbstractGenericNet`): Hierarchical switch input bit
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_features" features
        """
        return tuple()

# ----------------------------------------------------------------------------
# -- VPR Input Files Generation ----------------------------------------------
# ----------------------------------------------------------------------------
class VPRInputsGeneration(Object, AbstractPass):
    """Generate XML input files for VPR."""

    __slots__ = ['output_dir', 'xml', 'active_blocks', 'active_primitives', 'block2id', 'blockpin2ptc',
            'sgmt2id', 'sgmt2ptc', 'sgmt2node_id', 'sgmt2node_id_truncated', 'chanx_id', 'chany_id',
            'srcsink_id', 'blockpin_id']
    def __init__(self, output_dir = "."):
        self.output_dir = output_dir

    @classmethod
    def _iob_orientation(cls, blk_inst):
        position = blk_inst.key[0]
        array = blk_inst.parent
        # find the connection box(es) in this tile
        cbox_presence = tuple(ori for ori in iter(Orientation)
                if not ori.is_auto and (position, ori.to_subtile()) in array.instances)
        if len(cbox_presence) == 0:
            raise PRGAInternalError(
                    "No connection box found around IO block '{}' at {} of array '{}'"
                    .format(blk_inst.model.name, position, array.name))
        elif len(cbox_presence) > 1:
            raise PRGAInternalError(
                    "Multiple connection boxes ({}) found around IO block '{}' at {} of array '{}'"
                    .format(", ".join(ori.name for ori in cbox_presence),
                        blk_inst.model.name, position, array.name))
        return cbox_presence[0].opposite

    @classmethod
    def _net2vpr(cls, net, parent_name = None):
        if net.bus_type.is_concat:
            return " ".join(cls._net2vpr(i, parent_name) for i in net.items)
        if net.bus_type.is_nonref:
            if net.net_type.is_port:
                return '{}.{}'.format(parent_name or net.parent.name, net.name)
            else:
                return '{}.{}'.format(net.hierarchy[0].name, net.model.name)
        elif net.bus_type.is_slice:
            s = ""
            if net.net_type.is_port:
                s = '{}.{}'.format(parent_name or net.parent.name, net.bus.name)
            else:
                s = '{}.{}'.format(net.bus.hierarchy[0].name, net.bus.model.name)
            if isinstance(net.index, int):
                s += "[{}]".format(net.index)
            else:
                s += "[{}:{}]".format(net.index.start, net.index.stop - 1)
            return s

    @classmethod
    def _get_hierarchical_block(cls, array, position):
        if array.module_class.is_nonleaf_array:
            subarray = array._instances.get_root(position)
            if subarray is None:
                return None, None
            return cls._get_hierarchical_block(subarray.model, position - subarray.key)
        else:
            inst = array.instances.get( (position, Subtile.center) )
            if inst is None:
                return None, None
            elif inst.model.module_class.is_io_block:
                return inst.model, cls._iob_orientation(inst)
            else:
                return inst.model, None

    @classmethod
    def _calc_hierarchical_position(cls, hierarchy, base = Position(0, 0)):
        return sum(iter(i.key[0] if i.parent.module_class.is_leaf_array else i.key for i in hierarchy), base)

    def _arch_layout_array(self, array, hierarchy = tuple()):
        if array.module_class.is_nonleaf_array:
            for instance in itervalues(array.instances):
                self._arch_layout_array(instance.model, (instance, ) + hierarchy)
        else:
            position = sum(iter(inst.key for inst in hierarchy), Position(0, 0))
            for x, y in product(range(array.width), range(array.height)):
                blk_inst = array.instances.get( ((x, y), Subtile.center) )
                if blk_inst is None:
                    continue
                attrs = {'priority': 1, 'x': position.x + x, 'y': position.y + y}
                if blk_inst.model.module_class.is_io_block:
                    # special process needed for IO blocks
                    # determine the orientation of this IO block
                    ori = self._iob_orientation(blk_inst)
                    self.active_blocks.setdefault(blk_inst.model.key, set()).add(ori)
                    attrs['type'] = blk_inst.model.name + '_' + ori.name[0]
                else:
                    self.active_blocks[blk_inst.model.key] = True
                    attrs['type'] = blk_inst.model.name
                self.xml.element_leaf('single', attrs)

    def _rrg_grid_array(self, array):
        for x, y in product(range(array.width), range(array.height)):
            pos = Position(x, y)
            instance = NonLeafArrayBuilder._get_hierarchical_root(array, Position(x, y), Subtile.center)
            if instance is None:
                self.xml.element_leaf("grid_loc", {
                    "block_type_id": 0, "x": x, "y": y, "width_offset": 0, "height_offset": 0})
            else:
                rootpos = sum(
                        iter(inst.key if inst.model.module_class.is_array else inst.key[0] for inst in instance),
                        Position(0, 0))
                id_ = None
                if instance[0].model.module_class.is_io_block:
                    ori = self._iob_orientation(instance[0])
                    id_ = self.block2id[instance[0].model.key, ori]
                else:
                    id_ = self.block2id[instance[0].model.key, None]
                self.xml.element_leaf("grid_loc", {
                    "block_type_id": id_, "x": x, "y": y,
                    "width_offset": x - rootpos.x, "height_offset": y - rootpos.y})

    def _interconnect(self, sink, hierarchy = tuple(), parent_name = None):
        sources = NetUtils.get_multisource(sink)
        if len(sources) == 0:
            return
        type_ = "direct" if len(sources) == 1 else "mux"
        name = [type_]
        if sink.net_type.is_pin:
            if sink.bus_type.is_slice:
                name.append( sink.bus.hierarchy[0].name )
                name.append( sink.bus.model.name )
                name.append( str(sink.index) )
            else:
                name.append( sink.hierarchy[0].name )
                name.append( sink.model.name )
        else:
            if sink.bus_type.is_slice:
                name.append( sink.bus.name )
                name.append( str(sink.index) )
            else:
                name.append( sink.name )
        with self.xml.element(type_, {
            "name": "_".join(name),
            "input": self._net2vpr(sources, parent_name),
            "output": self._net2vpr(sink, parent_name),
            }):
            for src in sources:
                conn = NetUtils.get_connection(src, sink)
                if conn is None:
                    continue
                pack_patterns = conn.get("pack_patterns", tuple())
                for pack_pattern in pack_patterns:
                    self.xml.element_leaf("pack_pattern", {
                        "name": pack_pattern,
                        "in_port": self._net2vpr(src, parent_name),
                        "out_port": self._net2vpr(sink, parent_name),
                        })

    def _leaf_pb_type(self, hierarchical_instance):
        instance = hierarchical_instance[0]
        primitive = instance.model
        if primitive.primitive_class.is_iopad:
            with self.xml.element("pb_type", {"name": instance.name, "num_pb": 1}):
                # ports
                self.xml.element_leaf('input', {'name': 'outpad', 'num_pins': '1'})
                self.xml.element_leaf('output', {'name': 'inpad', 'num_pins': '1'})
                # mode: inpad
                with self.xml.element('mode', {'name': 'inpad'}):
                    with self.xml.element('pb_type', {'name': 'inpad', 'blif_model': '.input', 'num_pb': '1'}):
                        self.xml.element_leaf('output', {'name': 'inpad', 'num_pins': '1'})
                    with self.xml.element('interconnect'), self.xml.element('direct', {'name': 'inpad',
                        'input': 'inpad.inpad', 'output': '{}.inpad'.format(instance.name)}):
                        self.xml.element_leaf('delay_constant', {'max': '1e-11',
                            'in_port': 'inpad.inpad', 'out_port': '{}.inpad'.format(instance.name)})
                # mode: outpad
                with self.xml.element('mode', {'name': 'outpad'}):
                    with self.xml.element('pb_type', {'name': 'outpad', 'blif_model': '.output', 'num_pb': '1'}):
                        self.xml.element_leaf('input', {'name': 'outpad', 'num_pins': '1'})
                    with self.xml.element('interconnect'), self.xml.element('direct', {'name': 'outpad',
                        'output': 'outpad.outpad', 'input': '{}.outpad'.format(instance.name)}):
                        self.xml.element_leaf('delay_constant', {'max': '1e-11',
                            'out_port': 'outpad.outpad', 'in_port': '{}.outpad'.format(instance.name)})
                return
        attrs = {'name': instance.name, 'num_pb': '1'}
        if primitive.primitive_class.is_lut:
            attrs.update({"blif_model": ".names", "class": "lut"})
        elif primitive.primitive_class.is_flipflop:
            attrs.update({"blif_model": ".latch", "class": "flipflop"})
        elif primitive.primitive_class.is_inpad:
            attrs.update({"blif_model": ".input"})
        elif primitive.primitive_class.is_outpad:
            attrs.update({"blif_model": ".output"})
        elif primitive.primitive_class.is_memory:
            self.active_primitives.add( primitive.key )
            attrs.update({"blif_model": ".subckt " + primitive.name, "class": "memory"})
        elif primitive.primitive_class.is_custom:
            self.active_primitives.add( primitive.key )
            attrs.update({"blif_model": ".subckt " + primitive.name})
        with self.xml.element('pb_type', attrs):
            # 1. emit ports
            for port in itervalues(primitive.ports):
                attrs = {'name': port.name, 'num_pins': len(port)}
                port_class = getattr(port, 'port_class', None)
                if port_class is not None:
                    attrs['port_class'] = port_class.name
                self.xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        attrs)
            # 2. timing
            for port in itervalues(primitive.ports):
                if port.is_clock:
                    continue
                if port.clock is not None:
                    clock = primitive.ports[port.clock]
                    if port.direction.is_input:
                        self.xml.element_leaf('T_setup', {
                                'port': self._net2vpr(port, instance.name),
                                'value': '1e-11',
                                'clock': clock.name,
                            })
                    else:
                        self.xml.element_leaf('T_clock_to_Q', {
                            'port': self._net2vpr(port, instance.name),
                            'max': '1e-11',
                            'clock': clock.name,
                            })
                if port.direction.is_output:
                    for sink in port:
                        sources = NetUtils.get_multisource(sink)
                        if len(sources) > 0:
                            self.xml.element_leaf('delay_constant', {
                                'max': '1e-11',
                                'in_port': self._net2vpr(NetUtils.get_multisource(sink), instance.name),
                                'out_port': self._net2vpr(sink, instance.name),
                                })

    def _pb_type(self, module, hierarchy = tuple()):
        parent_name = hierarchy[0].name if hierarchy else module.name
        attrs = {"name": parent_name}
        if hierarchy:
            attrs["num_pb"] = 1
        with self.xml.element("pb_type", attrs):
            # 1. emit ports:
            for port in itervalues(module.ports):
                attrs = {'name': port.name, 'num_pins': len(port)}
                if not port.is_clock and hasattr(port, 'global_'):
                    attrs['is_non_clock_global'] = "true"
                self.xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        attrs)
            # 2. emit cluster/primitive instances
            for instance in itervalues(module.instances):
                if instance.model.module_class.is_cluster:
                    self._pb_type(instance.model, (instance, ) + hierarchy)
                elif instance.model.module_class.is_primitive:
                    self._leaf_pb_type((instance, ) + hierarchy)
            # 3. emit interconnect
            with self.xml.element('interconnect'):
                for net in chain(itervalues(module.ports),
                        iter(pin for inst in itervalues(module.instances) for pin in itervalues(inst.pins))):
                    if not net.is_sink:
                        continue
                    for sink in net:
                        self._interconnect(sink, hierarchy, parent_name)

    def _arch_tile(self, block, ori = None):
        tile_name = block.name if ori is None else '{}_{}'.format(block.name, ori.name[0])
        attrs = {"name": tile_name,
                "capacity": block.capacity,
                "width": block.width,
                "height": block.height}
        with self.xml.element("tile", attrs):
            # 1. emit ports:
            for port in itervalues(block.ports):
                attrs = {'name': port.name, 'num_pins': len(port)}
                if not port.is_clock and hasattr(port, 'global_'):
                    attrs['is_non_clock_global'] = "true"
                self.xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        attrs)
            # 2. FC
            self.xml.element_leaf("fc", {"in_type": "frac", "in_val": "1.0", "out_type": "frac", "out_val": "1.0"})
            # 3. pinlocations
            with self.xml.element("pinlocations", {"pattern": "custom"}):
                for x, y, orientation in product(
                        range(block.width),
                        range(block.height),
                        Orientation if ori is None else (ori.opposite, )):
                    if orientation.is_auto:
                        continue
                    elif x not in (0, block.width - 1) and y not in (0, block.height - 1):
                        continue
                    ports = []
                    for port in itervalues(block.ports):
                        if port.position == (x, y) and port.orientation in (Orientation.auto, orientation):
                            ports.append(port)
                    if ports:
                        self.xml.element_leaf("loc", {
                            "side": orientation.case("top", "right", "bottom", "left"),
                            "xoffset": x, "yoffset": y},
                            ' '.join('{}.{}'.format(tile_name, port.name) for port in ports))
            # 4. equivalent sites
            with self.xml.element("equivalent_sites"):
                self.xml.element_leaf("site", {"pb_type": block.name, "pin_mapping": "direct"})

    def _rrg_tile(self, block, ori):
        blockpin2ptc = self.blockpin2ptc.setdefault( block.key, OrderedDict() )
        block_name = block.name if ori is None else '{}_{}'.format(block.name, ori.name[0])
        with self.xml.element("block_type", {
            "name": block_name, "width": block.width, "height": block.height, "id": self.block2id[block.key, ori]}):
            ptc = 0
            for subblock in range(block.capacity):
                subblock_name = '{}[{}]'.format(block_name, subblock) if block.capacity > 1 else block_name
                for port in itervalues(block.ports):
                    if port.direction.is_input and not port.is_clock:
                        if subblock == 0:
                            blockpin2ptc[port.key] = ptc
                        for i in range(len(port)):
                            with self.xml.element("pin_class", {"type": "INPUT"}):
                                self.xml.element_leaf("pin", {"ptc": ptc},
                                        '{}.{}[{}]'.format(subblock_name, port.name, i))
                            ptc += 1
                for port in itervalues(block.ports):
                    if port.direction.is_output:
                        if subblock == 0:
                            blockpin2ptc[port.key] = ptc
                        for i in range(len(port)):
                            with self.xml.element("pin_class", {"type": "OUTPUT"}):
                                self.xml.element_leaf("pin", {"ptc": ptc},
                                        '{}.{}[{}]'.format(subblock_name, port.name, i))
                            ptc += 1
                for port in itervalues(block.ports):
                    if port.is_clock:
                        if subblock == 0:
                            blockpin2ptc[port.key] = ptc
                        for i in range(len(port)):
                            with self.xml.element("pin_class", {"type": "INPUT"}):
                                self.xml.element_leaf("pin", {"ptc": ptc},
                                        '{}.{}[{}]'.format(subblock_name, port.name, i))
                            ptc += 1
                if subblock == 0:
                    blockpin2ptc["#"] = ptc

    def _arch_segment(self, segment):
        with self.xml.element('segment', {
            'name': segment.name,
            'freq': '1.0',
            'length': segment.length,
            'type': 'unidir',
            'Rmetal': '0.0',
            'Cmetal': '0.0',
            }):
            # fake switch
            self.xml.element_leaf('mux', {'name': 'default'})
            self.xml.element_leaf('sb', {'type': 'pattern'}, ' '.join(iter('1' for i in range(segment.length + 1))))
            self.xml.element_leaf('cb', {'type': 'pattern'}, ' '.join(iter('1' for i in range(segment.length))))

    def _rrg_segment(self, segment, id_):
        with self.xml.element('segment', {'name': segment.name, 'id': id_}):
            self.xml.element_leaf('timing', {'R_per_meter': 0.0, 'C_per_meter': 0.0})

    def _rrg_node(self, type_, id_, ptc, xlow, ylow, *,
            track_dir = None, port_ori = None, xhigh = None, yhigh = None, segment_id = None):
        node_attr = {"capacity": 1, "id": id_, "type": type_}
        loc_attr = {"xlow": xlow, "ylow": ylow, "ptc": ptc,
                "xhigh": uno(xhigh, xlow), "yhigh": uno(yhigh, ylow)}
        if type_ in ("CHANX", "CHANY"):
            assert track_dir is not None and segment_id is not None
            node_attr["direction"] = track_dir.case("INC_DIR", "DEC_DIR")
        elif type_ in ("IPIN", "OPIN"):
            assert port_ori is not None
            loc_attr["side"] = port_ori.case("TOP", "RIGHT", "BOTTOM", "LEFT")
        with self.xml.element("node", node_attr):
            self.xml.element_leaf("loc", loc_attr)
            self.xml.element_leaf("timing", {"C": 0.0, "R": 0.0})
            if type_ in ("CHANX", "CHANY"):
                self.xml.element_leaf("segment", {"segment_id": segment_id})

    def _calc_blockpin_id(self, pin, srcsink = False, position_hint = None):
        bus, index = (pin.bus, pin.index) if pin.bus_type.is_slice else (pin, 0)
        id_base = self.srcsink_id if srcsink else self.blockpin_id
        if position_hint is None:
            position_hint = self._calc_hierarchical_position(bus.hierarchy)
        id_base = id_base[position_hint.x][position_hint.y]
        pin2ptc = self.blockpin2ptc[bus.model.parent.key]
        return id_base + pin2ptc["#"] * bus.hierarchy[0].key[1] + pin2ptc[bus.model.key] + index

    def _calc_track_id(self, pin):
        bus, index = (pin.bus, pin.index) if pin.bus_type.is_slice else (pin, 0)
        node = bus.model.key
        dim, dir_ = node.orientation.dimension, node.orientation.direction
        # 1. which channel are we working on?
        channel_position = self._calc_hierarchical_position(bus.hierarchy)
        # adjustments based on switch box position
        corner = bus.hierarchy[0].key[1].to_corner()
        if node.orientation.is_east and corner.dotx(Dimension.x).is_inc:
            channel_position += (1, 0)
        elif not node.orientation.is_east and corner.dotx(Dimension.x).is_dec:
            channel_position -= (1, 0)
        if node.orientation.is_north and corner.dotx(Dimension.y).is_inc:
            channel_position += (0, 1)
        elif not node.orientation.is_north and corner.dotx(Dimension.y).is_dec:
            channel_position -= (0, 1)
        pos = channel_position # short alias
        # 2. section?
        section = node.orientation.case(
                north = corner.dotx(Dimension.y).case(1, 0) - node.position.y,
                east = corner.dotx(Dimension.x).case(1, 0) - node.position.x,
                south = corner.dotx(Dimension.y).case(0, 1) + node.position.y,
                west = corner.dotx(Dimension.x).case(0, 1) + node.position.x)
        # 3. channel id base
        node_id_base, before, after = dim.case(self.chanx_id, self.chany_id)[pos.x][pos.y]
        if node_id_base is None:
            raise PRGAInternalError("Node ID not assigned for channel {} at {}".format(dim.name, pos))
        # 4. segment id base
        segment_node_id_base = (self.sgmt2node_id if dir_.case(before, after)
                else self.sgmt2node_id_truncated)[node.prototype.name]
        # 5. return the ID
        return (node_id_base +
                dir_.case(0, (self.sgmt2node_id if before else self.sgmt2node_id_truncated)["#"]) +
                segment_node_id_base +
                section * node.prototype.width + index)

    def _calc_track_ptc(self, node, i):
        remainder = ori.case(
                node.position.y - node.section + node.prototype.length - 1,
                node.position.x - node.section + node.prototype.length - 1,
                node.position.y + node.section,
                node.position.x + node.section) % node.prototype.length
        return (self.sgmt2ptc[name] + 2 * (remainder * node.prototype.width + i) +
                node.orientation.direction.case(0, 1))

    def _rrg_edges(self, sink, sink_node):
        stack = [sink]
        while stack:
            cur = stack.pop()
            # find the previous net
            for prev in NetUtils.get_hierarchical_multisource(cur):
                assert not prev.net_type.is_unconnected
                if not prev.net_type.is_pin:
                    continue
                prev_bus, prev_index = (prev.bus, prev.index) if prev.bus_type.is_slice else (prev, 0)
                node = prev_bus.model.key
                if isinstance(node, SegmentID) and node.segment_type.is_sboxout:
                    self.xml.element_leaf("edge", {
                        "src_node": self._calc_track_id(prev),
                        "sink_node": sink_node,
                        "switch_id": 1})
                elif prev_bus.hierarchy[0].model.module_class.is_block:
                    self.xml.element_leaf("edge", {
                        "src_node": self._calc_blockpin_id(prev),
                        "sink_node": sink_node,
                        "switch_id": 1})
                else:
                    stack.append(prev)

    @property
    def key(self):
        return "vpr.input"

    @property
    def is_readonly_pass(self):
        return True

    def run(self, context):
        arch_f = os.path.join(os.path.abspath(self.output_dir), "arch.vpr.xml")
        rrg_f = os.path.join(os.path.abspath(self.output_dir), "rrg.vpr.xml")
        # runtime-generated data
        self.active_blocks = {}
        self.active_primitives = set()
        self.block2id = OrderedDict()
        self.blockpin2ptc = {}
        # architecture XML generation
        with XMLGenerator(open(arch_f, OpenMode.wb), True) as xml, xml.element("architecture"):
            self.xml = xml
            # layout
            with xml.element("layout"), xml.element("fixed_layout",
                    {"name": context.top.name, "width": context.top.width, "height": context.top.height}):
                self._arch_layout_array(context.top)
            # physical tiles
            with xml.element("tiles"):
                for block_key, orilist in iteritems(self.active_blocks):
                    block = context.database[ModuleView.user, block_key]
                    if block.module_class.is_io_block:
                        for ori in orilist:
                            self.block2id[block_key, ori] = len(self.block2id) + 1
                            self._arch_tile(block, ori)
                    else:
                        self._arch_tile(block)
                        self.block2id[block_key, None] = len(self.block2id) + 1
            # complex blocks
            with xml.element("complexblocklist"):
                for block_key in self.active_blocks:
                    self._pb_type(context.database[ModuleView.user, block_key])
            # models
            with xml.element("models"):
                for model_key in self.active_primitives:
                    pass
            # device: fake
            with xml.element('device'):
                xml.element_leaf('sizing', {'R_minW_nmos': '0.0', 'R_minW_pmos': '0.0'})
                xml.element_leaf('connection_block', {'input_switch_name': 'default'})
                xml.element_leaf('area', {'grid_logic_tile_area': '0.0'})
                xml.element_leaf('switch_block', {'type': 'wilton', 'fs': '3'})
                xml.element_leaf('default_fc',
                        {'in_type': 'frac', 'in_val': '1.0', 'out_type': 'frac', 'out_val': '1.0'})
                with xml.element('chan_width_distr'):
                    xml.element_leaf('x', {'distr': 'uniform', 'peak': '1.0'})
                    xml.element_leaf('y', {'distr': 'uniform', 'peak': '1.0'})
            # switches: fake
            with xml.element("switchlist"):
                xml.element_leaf('switch', {
                    'type': 'mux',
                    'name': 'default',
                    'R': '0.0',
                    'Cin': '0.0',
                    'Cout': '0.0',
                    'Tdel': '1e-11',
                    'mux_trans_size': '0.0',
                    'buf_size': '0.0',
                    })
            # segments:
            with xml.element("segmentlist"):
                for segment in itervalues(context.segments):
                    self._arch_segment(segment)
            # clean up
            del self.xml
        # runtime-generated data
        self.sgmt2id = OrderedDict()
        self.sgmt2ptc = OrderedDict()
        self.sgmt2node_id = OrderedDict()
        self.sgmt2node_id_truncated = OrderedDict()
        # VPR nodes: CHANX. [x][y] -> node_id_base, consecutive channels to the left, ... to the right
        self.chanx_id = [[(None, 0, 0) for _ in range(context.top.height)] for _ in range(context.top.width)]
        for y in range(context.top.height):
            startx = context.top.width
            for x in range(context.top.width):
                if NonLeafArrayBuilder._no_channel(context.top, Position(x, y), Orientation.east):
                    for xx in range(startx, x):
                        self.chanx_id[xx][y] = (0, xx - startx, x - 1 - xx)
                    startx = context.top.width
                elif x < startx:
                    startx = x
        # VPR node: CHANY. [x][y] -> node_id_base, consecutive channels to from below, ... from above
        self.chany_id = [[(None, 0, 0) for _ in range(context.top.height)] for _ in range(context.top.width)]
        for x in range(context.top.width):
            starty = context.top.height
            for y in range(context.top.height):
                if NonLeafArrayBuilder._no_channel(context.top, Position(x, y), Orientation.north):
                    for yy in range(starty, y):
                        self.chany_id[x][yy] = (0, yy - starty, y - 1 - yy)
                    starty = context.top.height
                elif y < starty:
                    starty = y
        # total number of nodes
        channel_width = 2 * sum(sgmt.width * sgmt.length for sgmt in itervalues(context.segments))
        total_num_nodes = 0
        # VPR nodes: SOURCE & SINK
        self.srcsink_id = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        # VPR nodes: IPIN & OPIN
        self.blockpin_id = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        # routing resource graph generation
        with XMLGenerator(open(rrg_f, OpenMode.wb), True) as xml, xml.element("rr_graph"):
            self.xml = xml
            # channels:
            with xml.element("channels"):
                xml.element_leaf("channel", {
                    'chan_width_max':   channel_width,
                    'x_min':            channel_width,
                    'y_min':            channel_width,
                    'x_max':            channel_width,
                    'y_max':            channel_width,
                    })
                for y in range(context.top.height - 1):
                    xml.element_leaf('x_list', {'index': y, 'info': channel_width})
                for x in range(context.top.width - 1):
                    xml.element_leaf('y_list', {'index': x, 'info': channel_width})
            # switches: fake
            with xml.element('switches'):
                with xml.element('switch', {'id': '0', 'type': 'mux', 'name': '__vpr_delayless_switch__', }):
                    xml.element_leaf('timing', {'R': '0.0', 'Cin': '0.0', 'Cout': '0.0', 'Tdel': '0.0', })
                    xml.element_leaf('sizing', {'mux_trans_size': '0.0', 'buf_size': '0.0', })
                with xml.element('switch', {'id': '1', 'type': 'mux', 'name': 'default', }):
                    xml.element_leaf('timing', {'R': '0.0', 'Cin': '0.0', 'Cout': '0.0', 'Tdel': '1e-11', })
                    xml.element_leaf('sizing', {'mux_trans_size': '0.0', 'buf_size': '0.0', })
            # segments
            with xml.element('segments'):
                ptc, node_id, node_id_truncated = 0, 0, 0
                for i, (name, sgmt) in enumerate(iteritems(context.segments)):
                    self.sgmt2id[name] = i
                    self.sgmt2ptc[name] = ptc
                    ptc += 2 * sgmt.width * sgmt.length
                    self.sgmt2node_id[name] = node_id
                    node_id += sgmt.width
                    self.sgmt2node_id_truncated[name] = node_id_truncated
                    node_id_truncated += sgmt.width * sgmt.length
                    self._rrg_segment(sgmt, i)
                self.sgmt2node_id["#"] = node_id
                self.sgmt2node_id_truncated["#"] = node_id_truncated
            # block types
            with xml.element('block_types'):
                xml.element_leaf("block_type", {"id": 0, "name": "EMPTY", "width": 1, "height": 1})
                for block_key, ori in self.block2id:
                    self._rrg_tile(context.database[ModuleView.user, block_key], ori)
            # grid
            with xml.element("grid"):
                self._rrg_grid_array(context.top)
            # nodes
            with xml.element("rr_nodes"):
                for x, y in product(range(context.top.width), range(context.top.height)):
                    pos = Position(x, y)
                    # 1. block pin nodes
                    block, ori = self._get_hierarchical_block(context.top, pos)
                    if block is not None:
                        pin2ptc = self.blockpin2ptc[block.key]
                        self.srcsink_id[x][y] = total_num_nodes
                        for subblock in range(block.capacity):
                            ptc_base = subblock * pin2ptc["#"]
                            for key, ptc in iteritems(pin2ptc):
                                if key == "#":
                                    continue
                                port = block.ports[key]
                                for i in range(len(port)):
                                    self._rrg_node(port.direction.case("SINK", "SOURCE"), total_num_nodes,
                                            ptc_base + ptc + i, x + port.position.x, y + port.position.y)
                                    total_num_nodes += 1
                        self.blockpin_id[x][y] = total_num_nodes
                        for subblock in range(block.capacity):
                            ptc_base = subblock * pin2ptc["#"]
                            for key, ptc in iteritems(pin2ptc):
                                if key == "#":
                                    continue
                                port = block.ports[key]
                                port_ori = ori.opposite if block.module_class.is_io_block else port.orientation
                                for i in range(len(port)):
                                    self._rrg_node(port.direction.case("IPIN", "OPIN"), total_num_nodes,
                                            ptc_base + ptc + i, x + port.position.x, y + port.position.y,
                                            port_ori = port_ori)
                                    total_num_nodes += 1
                    # 2. channel nodes
                    for dim in Dimension:
                        node_id_base, before, after = dim.case(self.chanx_id, self.chany_id)[x][y]
                        if node_id_base is None:
                            continue
                        dim.case(self.chanx_id, self.chany_id)[x][y] = (total_num_nodes, before, after)
                        for dir_, (name, segment_id) in product(Direction, iteritems(self.sgmt2id)):
                            segment = context.segments[name]
                            ori = Orientation.compose(dim, dir_)
                            for section, i in product(range(1 if dir_.case(before, after) > 0 else segment.length),
                                    range(segment.width)):
                                remainder = ori.case(
                                        y - section + segment.length - 1,
                                        x - section + segment.length - 1,
                                        y + section,
                                        x + section) % segment.length
                                ptc = self.sgmt2ptc[name] + 2 * remainder * segment.width + i * 2 + dir_.case(0, 1)
                                self._rrg_node(dim.case("CHANX", "CHANY"), total_num_nodes, ptc,
                                        ori.case(x, x, x, x - min(before, segment.length - 1 - section)),
                                        ori.case(y, y, y - min(before, segment.length - 1 - section), y),
                                        track_dir = dir_,
                                        xhigh = ori.case(x, x + min(after, segment.length - 1 - section), x, x),
                                        yhigh = ori.case(y + min(after, segment.length - 1 - section), y, y, y),
                                        segment_id = segment_id,
                                        )
                                total_num_nodes += 1
            # edges
            with xml.element("rr_edges"):
                for x, y in product(range(context.top.width), range(context.top.height)):
                    pos = Position(x, y)
                    # block pin
                    inst = NonLeafArrayBuilder._get_hierarchical_root(context.top, pos, Subtile.center)
                    if inst is not None and pos == self._calc_hierarchical_position(inst):
                        # this is a block instance
                        block = inst[0].model
                        pin2ptc = self.blockpin2ptc[block.key]
                        for subblock in range(block.capacity):
                            inst = NonLeafArrayBuilder._get_hierarchical_root(context.top, pos, subblock)
                            for key in pin2ptc:
                                if key == "#":
                                    continue
                                port = block.ports[key]
                                for bit in Pin(port, inst):
                                    xml.element_leaf('edge', {
                                        'src_node': self._calc_blockpin_id(bit, port.direction.is_output, pos),
                                        'sink_node': self._calc_blockpin_id(bit, port.direction.is_input, pos),
                                        'switch_id': 0,
                                        })
                                if port.direction.is_input:
                                    for bit in Pin(port, inst):
                                        self._rrg_edges(bit, self._calc_blockpin_id(bit, False, pos))
                    # segments
                    for corner in Corner:
                        inst = NonLeafArrayBuilder._get_hierarchical_root(context.top, pos, corner.to_subtile())
                        if inst is None or not inst[0].model.module_class.is_switch_box:
                            continue
                        for node, port in iteritems(inst[0].model.ports):
                            if not node.segment_type.is_sboxout:
                                continue
                            for bit in Pin(port, inst):
                                self._rrg_edges(bit, self._calc_track_id(bit))
            del self.xml
