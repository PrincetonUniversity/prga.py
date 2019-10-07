# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from itertools import chain, count, product

__all__ = ['vpr_arch_instance', 'vpr_arch_block']

# ----------------------------------------------------------------------------
# -- Instance to VPR Architecture Description --------------------------------
# ----------------------------------------------------------------------------
def _bit2vpr(bit):
    return '{}.{}[{}]'.format(bit.parent.name, bit.bus.name, bit.index)

def _vpr_arch_clusterlike(xmlgen, module):
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
                        'input': _bit2vpr(sources[0]),
                        'output': _bit2vpr(sink),
                        }):
                        if (sources[0], sink) in module.pack_patterns:
                            xmlgen.element_leaf('pack_pattern', {
                                'name': 'pack_{}_{}_{}'.format(sink.parent.name, sink.bus.name, sink.index),
                                'in_port': _bit2vpr(sources[0]),
                                'out_port': _bit2vpr(sink),
                                })
                else:
                    with xmlgen.element('mux', {
                        'name': 'mux_{}_{}_{}'.format(sink.parent.name, sink.bus.name, sink.index),
                        'input': ' '.join(map(_bit2vpr, sources)),
                        'output': _bit2vpr(sink),
                        }):
                        # fake timing
                        for source in sources:
                            xmlgen.element_leaf('delay_constant', {
                                'max': '1e-11',
                                'in_port': _bit2vpr(source),
                                'out_port': _bit2vpr(sink),
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
        _vpr_arch_clusterlike(xmlgen, cluster)

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
                    _vpr_arch_clusterlike(xmlgen, mode)
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
                            'port': _bit2vpr(bit),
                            'value': '1e-11',
                            'clock': port.clock,
                            })
                else:
                    for bit in port:
                        xmlgen.element_leaf('T_clock_to_Q', {
                            'port': _bit2vpr(bit),
                            'max': '1e-11',
                            'clock': port.clock,
                            })
            if port.direction.is_output:
                for source in port.combinational_sources:
                    for src, sink in product(iter(primitive.ports[source]), iter(port)):
                        xmlgen.element_leaf('delay_constant', {
                            'max': '1e-11',
                            'in_port': _bit2vpr(src),
                            'out_port': _bit2vpr(sink),
                            })

def vpr_arch_instance(xmlgen, instance):
    if instance.model.module_class.is_cluster:      # cluster
        _vpr_arch_cluster_instance(xmlgen, instance)
    elif instance.model.module_class.is_primitive:  # primitive
        _vpr_arch_primitive_instance(xmlgen, instance)

def vpr_arch_block(xmlgen, block):
    with xmlgen.element('pb_type', {'name': block.name}):
        # 1. emit ports
        for port in itervalues(block.ports):
            xmlgen.element_leaf(
                    'clock' if port.is_clock else port.direction.case('input', 'output'),
                    {'name': port.name, 'num_pins': port.width})
        # 2. do the rest of the cluster
        _vpr_arch_clusterlike(xmlgen, block)
