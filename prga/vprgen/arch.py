# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Position
from prga.flow.util import iter_all_tiles

from itertools import chain, count, product

__all__ = ['vpr_arch_primitive', 'vpr_arch_instance', 'vpr_arch_tile', 'vpr_arch_layout',
        'vpr_arch_segment', 'vpr_arch_default_switch', 'vpr_arch_xml']

# ----------------------------------------------------------------------------
# -- Primitive Model to VPR Architecture Description -------------------------
# ----------------------------------------------------------------------------
def vpr_arch_primitive(xmlgen, primitive):
    with xmlgen.element('model', {'name': primitive.name}):
        with xmlgen.element('input_ports'):
            for iname, input_ in iteritems(primitive.ports):
                if not input_.direction.is_input:
                    continue
                attrs = {'name': iname}
                combinational_sink_ports = ' '.join(iter(oname for oname, output in iteritems(primitive.ports)
                    if output.direction.is_output and iname in output.combinational_sources))
                if combinational_sink_ports:
                    attrs['combinational_sink_ports'] = combinational_sink_ports
                if input_.is_clock:
                    attrs['is_clock'] = '1'
                elif input_.clock:
                    attrs['clock'] = input_.clock
                xmlgen.element_leaf('port', attrs)
        with xmlgen.element('output_ports'):
            for oname, output in iteritems(primitive.ports):
                if not output.direction.is_output:
                    continue
                attrs = {'name': oname}
                if output.is_clock:
                    attrs['is_clock'] = '1'
                elif output.clock:
                    attrs['clock'] = output.clock
                xmlgen.element_leaf('port', attrs)

# ----------------------------------------------------------------------------
# -- Tile to VPR Architecture Description ------------------------------------
# ----------------------------------------------------------------------------
def _bit2vpr(bit, parent = None):
    if bit.net_type.is_port:
        return '{}.{}[{}]'.format(parent or bit.parent.name, bit.bus.name, bit.index)
    else:
        return '{}.{}[{}]'.format(bit.parent.name, bit.bus.name, bit.index)

def _vpr_arch_clusterlike(xmlgen, module, parent = None):
    """Emit ``"pb_type"`` content for cluster-like modules."""
    # 1. emit sub-instances
    for instance in itervalues(module.instances):
        vpr_arch_instance(xmlgen, instance)
    # 2. emit interconnect
    with xmlgen.element('interconnect'):
        for pin in chain(iter(port for port in itervalues(module.ports) if port.direction.is_output),
                iter(pin for instance in itervalues(module.instances)
                    for pin in itervalues(instance.pins) if pin.direction.is_input)):
            for sink in pin:
                sources = tuple(src for src in sink.user_sources if not src.net_type.is_const)
                if len(sources) == 0:
                    continue
                elif len(sources) == 1:
                    with xmlgen.element('direct', {
                        'name': 'direct_{}_{}_{}'.format(sink.parent.name, sink.bus.name, sink.index),
                        'input': _bit2vpr(sources[0], parent),
                        'output': _bit2vpr(sink, parent),
                        }):
                        if (sources[0], sink) in module.pack_patterns:
                            xmlgen.element_leaf('pack_pattern', {
                                'name': 'pack_{}_{}_{}'.format(sink.parent.name, sink.bus.name, sink.index),
                                'in_port': _bit2vpr(sources[0], parent),
                                'out_port': _bit2vpr(sink, parent),
                                })
                else:
                    with xmlgen.element('mux', {
                        'name': 'mux_{}_{}_{}'.format(sink.parent.name, sink.bus.name, sink.index),
                        'input': ' '.join(map(lambda x: _bit2vpr(x, parent), sources)),
                        'output': _bit2vpr(sink, parent),
                        }):
                        # fake timing
                        for source in sources:
                            xmlgen.element_leaf('delay_constant', {
                                'max': '1e-11',
                                'in_port': _bit2vpr(source, parent),
                                'out_port': _bit2vpr(sink, parent),
                                })

def _vpr_arch_cluster_instance(xmlgen, instance):
    """Emit ``"pb_type"`` for cluster instance."""
    cluster = instance.model
    with xmlgen.element('pb_type', {'name': instance.name, 'num_pb': '1'}):
        # 1. emit ports
        for port in itervalues(cluster.ports):
            xmlgen.element_leaf(
                    'clock' if port.is_clock else port.direction.case('input', 'output'),
                    {'name': port.name, 'num_pins': port.width})
        # 2. do the rest of the cluster
        _vpr_arch_clusterlike(xmlgen, cluster, instance.name)

def _vpr_arch_primitive_instance(xmlgen, instance):
    """Emit ``"pb_type"`` for primitive instance."""
    primitive = instance.model
    if primitive.primitive_class.is_iopad:
        with xmlgen.element('pb_type', {'name': instance.name, 'num_pb': '1'}):
            xmlgen.element_leaf('input', {'name': 'outpad', 'num_pins': '1'})
            xmlgen.element_leaf('output', {'name': 'inpad', 'num_pins': '1'})
            with xmlgen.element('mode', {'name': 'inpad'}):
                with xmlgen.element('pb_type', {'name': 'inpad', 'blif_model': '.input', 'num_pb': '1'}):
                    xmlgen.element_leaf('output', {'name': 'inpad', 'num_pins': '1'})
                with xmlgen.element('interconnect'):
                    with xmlgen.element('direct', {'name': 'inpad',
                        'input': 'inpad.inpad', 'output': '{}.inpad'.format(instance.name)}):
                        xmlgen.element_leaf('delay_constant', {'max': '1e-11',
                            'in_port': 'inpad.inpad', 'out_port': '{}.inpad'.format(instance.name)})
            with xmlgen.element('mode', {'name': 'outpad'}):
                with xmlgen.element('pb_type', {'name': 'outpad', 'blif_model': '.output', 'num_pb': '1'}):
                    xmlgen.element_leaf('input', {'name': 'outpad', 'num_pins': '1'})
                with xmlgen.element('interconnect'):
                    with xmlgen.element('direct', {'name': 'outpad',
                        'output': 'outpad.outpad', 'input': '{}.outpad'.format(instance.name)}):
                        xmlgen.element_leaf('delay_constant', {'max': '1e-11',
                            'out_port': 'outpad.outpad', 'in_port': '{}.outpad'.format(instance.name)})
        return
    elif primitive.primitive_class.is_multimode:
        with xmlgen.element('pb_type', {'name': instance.name, 'num_pb': '1'}):
            # 1. emit ports
            for port in itervalues(instance.model.ports):
                xmlgen.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        {'name': port.name, 'num_pins': str(port.width)})
            # 2. emit modes
            for mode in itervalues(instance.model.modes):
                with xmlgen.element('mode', {'name': mode.name}):
                    _vpr_arch_clusterlike(xmlgen, mode, instance.name)
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
        attrs.update({"blif_model": ".subckt " + primitive.name, "class": "memory"})
    elif primitive.primitive_class.is_custom:
        attrs.update({"blif_model": ".subckt " + primitive.name})
    with xmlgen.element('pb_type', attrs):
        # 1. emit ports
        for port in itervalues(primitive.ports):
            attrs = {'name': port.name, 'num_pins': str(port.width)}
            if port.port_class is not None:
                attrs['port_class'] = port.port_class.name
            xmlgen.element_leaf(
                    'clock' if port.is_clock else port.direction.case('input', 'output'),
                    attrs)
        # 2. fake timing
        for port in itervalues(primitive.ports):
            if port.is_clock:
                continue
            if port.clock is not None:
                if port.direction.is_input:
                    for bit in port:
                        xmlgen.element_leaf('T_setup', {
                            'port': _bit2vpr(bit, instance.name),
                            'value': '1e-11',
                            'clock': port.clock,
                            })
                else:
                    for bit in port:
                        xmlgen.element_leaf('T_clock_to_Q', {
                            'port': _bit2vpr(bit, instance.name),
                            'max': '1e-11',
                            'clock': port.clock,
                            })
            if port.direction.is_output:
                for source in port.combinational_sources:
                    for src, sink in product(iter(primitive.ports[source]), iter(port)):
                        xmlgen.element_leaf('delay_constant', {
                            'max': '1e-11',
                            'in_port': _bit2vpr(src, instance.name),
                            'out_port': _bit2vpr(sink, instance.name),
                            })

def vpr_arch_instance(xmlgen, instance):
    """Convert an instance in a block into VPR architecture description.
    
    Args:
        xmlgen (`XMLGenerator`):
        instance (`RegularInstance`):
    """
    if instance.model.module_class.is_cluster:      # cluster
        _vpr_arch_cluster_instance(xmlgen, instance)
    elif instance.model.module_class.is_primitive:  # primitive
        _vpr_arch_primitive_instance(xmlgen, instance)

def vpr_arch_tile(xmlgen, tile):
    """Convert a tile into VPR architecture description.
    
    Args:
        xmlgen (`XMLGenerator`):
        tile (`Tile`):
    """
    with xmlgen.element('pb_type', {
        'name': tile.name,
        'capacity': tile.capacity,
        'width': tile.width,
        'height': tile.height,
        }):
        # 1. emit ports
        for port in itervalues(tile.block.ports):
            attrs = {'name': port.name, 'num_pins': port.width}
            if port.net_class.is_global and not port.is_clock:
                attrs['is_non_clock_global'] = "true"
            xmlgen.element_leaf(
                    'clock' if port.is_clock else port.direction.case('input', 'output'),
                    attrs)
        # 2. do the rest of the cluster
        _vpr_arch_clusterlike(xmlgen, tile.block, tile.name)
        # 3. pin locations
        with xmlgen.element('pinlocations', {'pattern': 'custom'}):
            if tile.block.module_class.is_io_block:
                xmlgen.element_leaf('loc', {'side': tile.orientation.case('bottom', 'left', 'top', 'right')},
                        ' '.join('{}.{}'.format(tile.name, port) for port in tile.block.ports))
            else:
                for y in range(tile.height):
                    # left
                    xmlgen.element_leaf('loc', {'side': 'left', 'xoffset': '0', 'yoffset': str(y)},
                        ' '.join('{}.{}'.format(tile.name, name) for name, port in iteritems(tile.block.ports)
                            if port.position == (0, y) and port.orientation.is_west))
                    # right
                    xmlgen.element_leaf('loc', {'side': 'right', 'xoffset': str(tile.width - 1), 'yoffset': str(y)},
                        ' '.join('{}.{}'.format(tile.name, name) for name, port in iteritems(tile.block.ports)
                            if port.position == (tile.width - 1, y) and port.orientation.is_east))
                for x in range(tile.width):
                    # bottom
                    xmlgen.element_leaf('loc', {'side': 'bottom', 'xoffset': str(x), 'yoffset': '0'},
                        ' '.join('{}.{}'.format(tile.name, name) for name, port in iteritems(tile.block.ports)
                            if port.position == (x, 0) and port.orientation.is_south))
                    # right
                    xmlgen.element_leaf('loc', {'side': 'top', 'xoffset': str(x), 'yoffset': str(tile.height - 1)},
                        ' '.join('{}.{}'.format(tile.name, name) for name, port in iteritems(tile.block.ports)
                            if port.position == (x, tile.height - 1) and port.orientation.is_north))

# # ----------------------------------------------------------------------------
# # -- Tile to VPR Architecture Description ------------------------------------
# # ----------------------------------------------------------------------------
# def vpr_arch_tile(xmlgen, tile):
#     """Convert a tile into VPR architecture description.
#     
#     Args:
#         xmlgen (`XMLGenerator`):
#         tile (`Tile`):
#     """
#     with xmlgen.element('tile', {
#         'name': tile.name,
#         'capacity': tile.capacity,
#         'width': tile.width,
#         'height': tile.height,
#         }):
#         # 1. emit ports
#         for port in itervalues(tile.block.ports):
#             attrs = {'name': port.name, 'num_pins': port.width}
#             if port.net_class.is_global and not port.is_clock:
#                 attrs['is_non_clock_global'] = "true"
#             xmlgen.element_leaf(
#                     'clock' if port.is_clock else port.direction.case('input', 'output'),
#                     attrs)
#         # 2. equivalent sites
#         with xmlgen.element('equivalent_sites'):
#             xmlgen.element_leaf('site', {'pb_type': tile.name})

# ----------------------------------------------------------------------------
# -- Layout to VPR Architecture Description ----------------------------------
# ----------------------------------------------------------------------------
def _vpr_arch_array(xmlgen, array, position = (0, 0)):
    """Convert an array to 'single' elements.

    Args:
        xmlgen (`XMLGenerator`):
        array (`Array`):
        position (:obj:`tuple` [:obj:`int`, :obj:`int` ]):
    """
    position = Position(*position)
    for pos, instance in iteritems(array.element_instances):
        pos += position
        if instance.module_class.is_tile:
            xmlgen.element_leaf('single', {
                'type': instance.model.name,
                'priority': '1',
                'x': pos.x,
                'y': pos.y,
                })
        else:
            _vpr_arch_array(xmlgen, instance.model, pos)

def vpr_arch_layout(xmlgen, array):
    """Convert a top-level array to VPR architecture description.

    Args:
        xmlgen (`XMLGenerator`):
        array (`Array`):
    """
    with xmlgen.element('layout'):
        with xmlgen.element('fixed_layout', {'name': array.name, 'width': array.width, 'height': array.height}):
            _vpr_arch_array(xmlgen, array)

# ----------------------------------------------------------------------------
# -- Segment to VPR Architecture Description ---------------------------------
# ----------------------------------------------------------------------------
def vpr_arch_segment(xmlgen, segment):
    """Convert a segment to VPR architecture description.

    Args:
        xmlgen (`XMLGenerator`):
        segment (`Segment`):
    """
    with xmlgen.element('segment', {
        'name': segment.name,
        'freq': '1.0',
        'length': str(segment.length),
        'type': 'unidir',
        'Rmetal': '0.0',
        'Cmetal': '0.0',
        }):
        # fake switch
        xmlgen.element_leaf('mux', {'name': 'default'})
        xmlgen.element_leaf('sb', {'type': 'pattern'}, ' '.join(iter('1' for i in range(segment.length + 1))))
        xmlgen.element_leaf('cb', {'type': 'pattern'}, ' '.join(iter('1' for i in range(segment.length))))

def vpr_arch_default_switch(xmlgen):
    """Generate a default switch tag to VPR architecture description.

    Args:
        xmlgen (`XMLGenerator`):
    """
    xmlgen.element_leaf('switch', {
        'type': 'mux',
        'name': 'default',
        'R': '0.0',
        'Cin': '0.0',
        'Cout': '0.0',
        'Tdel': '1e-11',
        'mux_trans_size': '0.0',
        'buf_size': '0.0',
        })

# ----------------------------------------------------------------------------
# -- Generate Full VPR Architecture XML --------------------------------------
# ----------------------------------------------------------------------------
def vpr_arch_xml(xmlgen, context):
    """Generate the full VPR architecture XML for ``context``.

    Args:
        xmlgen (`XMLGenerator`):
        context (`BaseArchitectureContext`):
    """
    with xmlgen.element('architecture'):
        # models
        with xmlgen.element('models'):
            for primitive in itervalues(context.primitives):
                if primitive.primitive_class.is_custom or primitive.primitive_class.is_memory:
                    vpr_arch_primitive(xmlgen, primitive)
        # # tiles
        # with xmlgen.element('tiles'):
        #     for tile in iter_all_tiles(context):
        #         vpr_arch_tile(xmlgen, tile)
        # layout
        vpr_arch_layout(xmlgen, context.top)
        # device: faked
        with xmlgen.element('device'):
            xmlgen.element_leaf('sizing', {'R_minW_nmos': '0.0', 'R_minW_pmos': '0.0'})
            xmlgen.element_leaf('connection_block', {'input_switch_name': 'default'})
            xmlgen.element_leaf('area', {'grid_logic_tile_area': '0.0'})
            xmlgen.element_leaf('switch_block', {'type': 'wilton', 'fs': '3'})
            xmlgen.element_leaf('default_fc',
                    {'in_type': 'frac', 'in_val': '1.0', 'out_type': 'frac', 'out_val': '1.0'})
            with xmlgen.element('chan_width_distr'):
                xmlgen.element_leaf('x', {'distr': 'uniform', 'peak': '1.0'})
                xmlgen.element_leaf('y', {'distr': 'uniform', 'peak': '1.0'})
        # switchlist
        with xmlgen.element('switchlist'):
            vpr_arch_default_switch(xmlgen)
        # segmentlist
        with xmlgen.element('segmentlist'):
            for segment in itervalues(context.segments):
                vpr_arch_segment(xmlgen, segment)
        # complexblocklist
        with xmlgen.element('complexblocklist'):
            for tile in iter_all_tiles(context):
                vpr_arch_tile(xmlgen, tile)
