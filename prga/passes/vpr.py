# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import Position, Subtile, Orientation, ModuleView
from ..netlist.net.util import NetUtils
from ..util import Object, uno
from ..xml import XMLGenerator
from ..exception import PRGAInternalError

import os
from itertools import product, chain

__all__ = ['FASMDelegate', 'VPRArchXMLGeneration']

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
# -- VPR Architecture Generation ---------------------------------------------
# ----------------------------------------------------------------------------
class VPRArchXMLGeneration(Object, AbstractPass):
    """Generate XML architecture file for VPR."""

    __slots__ = ['f']
    def __init__(self, f = "arch.vpr.xml"):
        self.f = f

    @classmethod
    def _iob_orientation(cls, array, blk_inst):
        position = blk_inst.key[0]
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
    def _layout_array(cls, xml, array, active_blocks, hierarchy = tuple()):
        if array.module_class.is_nonleaf_array:
            for instance in itervalues(array.instances):
                cls._layout_array(xml, instance.model, active_blocks, (instance, ) + hierarchy)
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
                    ori = cls._iob_orientation(array, blk_inst)
                    active_blocks.setdefault(blk_inst.model.key, set()).add(ori)
                    attrs['type'] = blk_inst.model.name + '_' + ori.name[0]
                else:
                    active_blocks[blk_inst.model.key] = True
                    attrs['type'] = blk_inst.model.name
                xml.element_leaf('single', attrs)

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
    def _interconnect(cls, xml, sink, hierarchy = tuple(), parent_name = None):
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
        with xml.element(type_, {
            "name": "_".join(name),
            "input": cls._net2vpr(sources, parent_name),
            "output": cls._net2vpr(sink, parent_name),
            }):
            for src in sources:
                conn = NetUtils.get_connection(src, sink)
                if conn is None:
                    continue
                pack_patterns = conn.get("pack_patterns", tuple())
                for pack_pattern in pack_patterns:
                    xml.element_leaf("pack_pattern", {
                        "name": pack_pattern,
                        "in_port": cls._net2vpr(src, parent_name),
                        "out_port": cls._net2vpr(sink, parent_name),
                        })

    @classmethod
    def _leaf_pb_type(cls, xml, hierarchical_instance, active_primitives):
        instance = hierarchical_instance[0]
        primitive = instance.model
        if primitive.primitive_class.is_iopad:
            with xml.element("pb_type", {"name": instance.name, "num_pb": 1}):
                # ports
                xml.element_leaf('input', {'name': 'outpad', 'num_pins': '1'})
                xml.element_leaf('output', {'name': 'inpad', 'num_pins': '1'})
                # mode: inpad
                with xml.element('mode', {'name': 'inpad'}):
                    with xml.element('pb_type', {'name': 'inpad', 'blif_model': '.input', 'num_pb': '1'}):
                        xml.element_leaf('output', {'name': 'inpad', 'num_pins': '1'})
                    with xml.element('interconnect'), xml.element('direct', {'name': 'inpad',
                        'input': 'inpad.inpad', 'output': '{}.inpad'.format(instance.name)}):
                        xml.element_leaf('delay_constant', {'max': '1e-11',
                            'in_port': 'inpad.inpad', 'out_port': '{}.inpad'.format(instance.name)})
                # mode: outpad
                with xml.element('mode', {'name': 'outpad'}):
                    with xml.element('pb_type', {'name': 'outpad', 'blif_model': '.output', 'num_pb': '1'}):
                        xml.element_leaf('input', {'name': 'outpad', 'num_pins': '1'})
                    with xml.element('interconnect'), xml.element('direct', {'name': 'outpad',
                        'output': 'outpad.outpad', 'input': '{}.outpad'.format(instance.name)}):
                        xml.element_leaf('delay_constant', {'max': '1e-11',
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
            active_primitives.add( primitive.key )
            attrs.update({"blif_model": ".subckt " + primitive.name, "class": "memory"})
        elif primitive.primitive_class.is_custom:
            active_primitives.add( primitive.key )
            attrs.update({"blif_model": ".subckt " + primitive.name})
        with xml.element('pb_type', attrs):
            # 1. emit ports
            for port in itervalues(primitive.ports):
                attrs = {'name': port.name, 'num_pins': len(port)}
                port_class = getattr(port, 'port_class', None)
                if port_class is not None:
                    attrs['port_class'] = port_class.name
                xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        attrs)
            # 2. timing
            for port in itervalues(primitive.ports):
                if port.is_clock:
                    continue
                if port.clock is not None:
                    clock = primitive.ports[port.clock]
                    if port.direction.is_input:
                        xml.element_leaf('T_setup', {
                                'port': cls._net2vpr(port, instance.name),
                                'value': '1e-11',
                                'clock': clock.name,
                            })
                    else:
                        xml.element_leaf('T_clock_to_Q', {
                            'port': cls._net2vpr(port, instance.name),
                            'max': '1e-11',
                            'clock': clock.name,
                            })
                if port.direction.is_output:
                    for sink in port:
                        sources = NetUtils.get_multisource(sink)
                        if len(sources) > 0:
                            xml.element_leaf('delay_constant', {
                                'max': '1e-11',
                                'in_port': cls._net2vpr(NetUtils.get_multisource(sink), instance.name),
                                'out_port': cls._net2vpr(sink, instance.name),
                                })

    @classmethod
    def _pb_type(cls, xml, module, active_primitives, hierarchy = tuple()):
        parent_name = hierarchy[0].name if hierarchy else module.name
        attrs = {"name": parent_name}
        if hierarchy:
            attrs["num_pb"] = 1
        with xml.element("pb_type", attrs):
            # 1. emit ports:
            for port in itervalues(module.ports):
                attrs = {'name': port.name, 'num_pins': len(port)}
                if not port.is_clock and hasattr(port, 'global_'):
                    attrs['is_non_clock_global'] = "true"
                xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        attrs)
            # 2. emit cluster/primitive instances
            for instance in itervalues(module.instances):
                if instance.model.module_class.is_cluster:
                    cls._pb_type(xml, instance.model, active_primitives, (instance, ) + hierarchy)
                elif instance.model.module_class.is_primitive:
                    cls._leaf_pb_type(xml, (instance, ) + hierarchy, active_primitives)
            # 3. emit interconnect
            with xml.element('interconnect'):
                for net in chain(itervalues(module.ports),
                        iter(pin for inst in itervalues(module.instances) for pin in itervalues(inst.pins))):
                    if not net.is_sink:
                        continue
                    for sink in net:
                        cls._interconnect(xml, sink, hierarchy, parent_name)

    @classmethod
    def _tile(cls, xml, block, ori = None):
        tile_name = block.name if ori is None else '{}_{}'.format(block.name, ori.name[0])
        attrs = {"name": tile_name,
                "capacity": block.capacity,
                "width": block.width,
                "height": block.height}
        with xml.element("tile", attrs):
            # 1. emit ports:
            for port in itervalues(block.ports):
                attrs = {'name': port.name, 'num_pins': len(port)}
                if not port.is_clock and hasattr(port, 'global_'):
                    attrs['is_non_clock_global'] = "true"
                xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        attrs)
            # 2. FC
            xml.element_leaf("fc", {"in_type": "frac", "in_val": "1.0", "out_type": "frac", "out_val": "1.0"})
            # 3. pinlocations
            with xml.element("pinlocations", {"pattern": "custom"}):
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
                        xml.element_leaf("loc", {
                            "side": orientation.case("top", "right", "bottom", "left"),
                            "xoffset": x, "yoffset": y},
                            ' '.join('{}.{}'.format(tile_name, port.name) for port in ports))
            # 4. equivalent sites
            with xml.element("equivalent_sites"):
                xml.element_leaf("site", {"pb_type": block.name, "pin_mapping": "direct"})

    @classmethod
    def _segment(cls, xml, segment):
        with xml.element('segment', {
            'name': segment.name,
            'freq': '1.0',
            'length': segment.length,
            'type': 'unidir',
            'Rmetal': '0.0',
            'Cmetal': '0.0',
            }):
            # fake switch
            xml.element_leaf('mux', {'name': 'default'})
            xml.element_leaf('sb', {'type': 'pattern'}, ' '.join(iter('1' for i in range(segment.length + 1))))
            xml.element_leaf('cb', {'type': 'pattern'}, ' '.join(iter('1' for i in range(segment.length))))

    @property
    def key(self):
        return "vpr.xml.arch"

    @property
    def is_readonly_pass(self):
        return True

    def run(self, context):
        if isinstance(self.f, basestring):
            d = os.path.abspath(os.path.dirname(self.f))
            makedirs(d)
            self.f = open(self.f, OpenMode.wb)
        active_blocks = {}
        active_primitives = set()
        with XMLGenerator(self.f, True) as xml, xml.element("architecture"):
            # layout
            with xml.element("layout"), xml.element("fixed_layout",
                    {"name": context.top.name, "width": context.top.width, "height": context.top.height}):
                self._layout_array(xml, context.top, active_blocks)
            # physical tiles
            with xml.element("tiles"):
                for block_key, orilist in iteritems(active_blocks):
                    block = context.database[ModuleView.user, block_key]
                    if block.module_class.is_io_block:
                        for ori in orilist:
                            self._tile(xml, block, ori)
                    else:
                        self._tile(xml, block)
            # complex blocks
            with xml.element("complexblocklist"):
                for block_key in active_blocks:
                    self._pb_type(xml, context.database[ModuleView.user, block_key], active_primitives)
            # models
            with xml.element("models"):
                for model_key in active_primitives:
                    pass
            # device: faked
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
            # switches: faked
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
                    self._segment(xml, segment)
