# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import (Position, Subtile, Orientation, ModuleView, Dimension, BlockPinID, SegmentID, SegmentType,
        Direction, Corner, IOType, BlockPortFCValue, BlockFCValue)
from ..core.builder.array import NonLeafArrayBuilder
from ..netlist.net.common import NetType
from ..netlist.net.util import NetUtils
from ..netlist.module.util import ModuleUtils
from ..util import Object, uno
from ..xml import XMLGenerator
from ..exception import PRGAInternalError, PRGAAPIError

import os
from itertools import product, chain
from collections import OrderedDict, namedtuple
from abc import abstractproperty, abstractmethod

import logging
_logger = logging.getLogger(__name__)

__all__ = ['FASMDelegate', 'TimingDelegate', 'VPRScalableDelegate',
        'VPRArchGeneration', 'VPRScalableArchGeneration', 'VPR_RRG_Generation']

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class FASMDelegate(Object):
    """FASM delegate supplying FASM metadata."""

    def reset(self):
        """Reset the delegate."""
        pass

    def fasm_mux_for_intrablock_switch(self, source, sink, instance = None):
        """Get the "fasm_mux" string for the connection from ``source`` to ``sink``.

        Args:
            source (`AbstractGenericNet`): Source bit
            sink (`AbstractGenericNet`): Sink bit
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block. ``source`` and ``sink`` are
                both immediate child-nets of this instance if ``instance`` is not None.
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_mux" features
        """
        return tuple()

    def fasm_prefix_for_intrablock_module(self, instance):
        """Get the "fasm_prefix" string for a hierarchical cluster/primitive ``instance``.

        Args:
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block

        Returns:
            :obj:`str`: "fasm_prefix" for the module
        """
        return ''

    def fasm_features_for_mode(self, instance, mode):
        """Get the "fasm_features" string for hierarchical multimode ``instance`` when it's configured to ``mode``.

        Args:
            instance (`AbstractInstance`): Hierarchical multimode instance in the logic/io block
            mode (:obj:`str`):
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_features" features to be emitted for the leaf-level multimode in the
                hierarchy
        """
        return tuple()

    def fasm_params_for_primitive(self, instance):
        """Get the "fasm_params" strings for hierarchical primitive ``instance``.

        Args:
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`str` ]: "fasm_param" feature mapping for the primitive instance
        """
        return {}

    def fasm_lut(self, instance):
        """Get the "fasm_lut" string for hierarchical LUT instance ``instance``.

        Args:
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block

        Returns:
            :obj:`str`: "fasm_lut" feature for the LUT instance
        """
        return ''
    
    def fasm_prefix_for_tile(self, instance):
        """Get the "fasm_prefix" strings for hierarchical block ``instance``. If the block instance is
        one of a few IO block instances, the fasm prefixes for all its siblings are returned together.

        Args:
            instance (`AbstractInstance`): Hierarchical logic/io block instance in the top-level array

        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_prefix" for the block instances
        """
        return tuple()

    def fasm_features_for_routing_switch(self, source, sink, instance):
        """Get the "fasm_features" strings for connecting routing box ports ``source`` and ``sink`` in hierarchical
        routing box ``instance``.

        Args:
            source (`AbstractGenericNet`): Source bit
            sink (`AbstractGenericNet`): Sink bit
            instance (`AbstractInstance`): Hierarchical routing box instance in the top-level array
        """
        return tuple()

# ----------------------------------------------------------------------------
# -- Timing Delegate ---------------------------------------------------------
# ----------------------------------------------------------------------------
class TimingDelegate(Object):
    """Timing delegate for VPR generation."""

    def reset(self):
        """Reset the delegate."""
        pass

    class Switch(namedtuple("Switch", "name Tdel R Cin Cout mux_trans_size buf_size")):
        def __new__(cls, name, Tdel, *, R = 0., Cin = 0., Cout = 0., mux_trans_size = 0., buf_size = "auto"):
            return super(TimingDelegate.Switch, cls).__new__(cls,
                    name, Tdel, R, Cin, Cout, mux_trans_size, buf_size)

    @property
    def vpr_switches(self):
        """Return a sequence of VPR switches."""
        return self._default_switches

    class Segment(namedtuple("Segment", "name length mux freq Rmetal Cmetal sb_pattern cb_pattern")):
        def __new__(cls, name, length, mux, *, freq = 1.0, Rmetal = 0.0, Cmetal = 0.0,
                sb_pattern = None, cb_pattern = None):
            return super(TimingDelegate.Segment, cls).__new__(cls,
                    name, length, mux, freq, Rmetal, Cmetal,
                    uno(sb_pattern, tuple(1 for i in range(length + 1))),
                    uno(cb_pattern, tuple(1 for i in range(length))) )

    def vpr_segment(self, prototype):
        """Return the VPR <segment> info for `Segment` ``prototype``."""
        return TimingDelegate.Segment(prototype.name, prototype.length, self.vpr_switches[0].name)

    def vpr_delay_of_intrablock_switch(self, source, sink, instance = None):
        """Get the constant delay value of the connection from ``source`` to ``sink``.

        Args:
            source (`AbstractGenericNet`): Source bit
            sink (`AbstractGenericNet`): Sink bit
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block. ``source`` and ``sink`` are
                both immediate child-nets of this instance if ``instance`` is not None.
        
        Returns:
            :obj:`float`: Max delay. Return `None` if not applicable 
            :obj:`float`: Min delay. Return `None` if not applicable
        """
        return None, None

    def vpr_setup_time_of_primitive_port(self, port, instance):
        """Get the setup time of the primitive port ``port``.

        Args:
            port (`AbstractGenericNet`):
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block. ``port`` is a sequential
                endpoint of this instance.
        
        Returns:
            :obj:`float`: Setup time. Return `None` if not applicable
        """
        return 1e-11

    def vpr_hold_time_of_primitive_port(self, port, instance):
        """Get the hold time of the primitive port ``port``.

        Args:
            port (`AbstractGenericNet`):
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block. ``port`` is a sequential
                endpoint of this instance.
        
        Returns:
            :obj:`float`: Hold time. Return `None` if not applicable
        """
        return None

    def vpr_clk2q_time_of_primitive_port(self, port, instance):
        """Get the clock-to-Q delay of the primitive port ``port``.

        Args:
            port (`AbstractGenericNet`):
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block. ``port`` is a sequential
                startpoint of this instance.
        
        Returns:
            :obj:`float`: Max delay. Return `None` if not applicable 
            :obj:`float`: Min delay. Return `None` if not applicable
        """
        return 1e-11, None

    def vpr_delay_of_primitive_path(self, source, sink, instance):
        """Get the propagation delay of the combinational path from ``source`` to ``sink``.

        Args:
            source (`AbstractGenericNet`): Source bit
            sink (`AbstractGenericNet`): Sink bit
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block. ``source`` and ``sink`` are
                both immediate child-nets of this instance if ``instance`` is not None.
        
        Returns:
            :obj:`float`: Max delay. Return `None` if not applicable 
            :obj:`float`: Min delay. Return `None` if not applicable
        """
        return 1e-11, None

    def vpr_interblock_routing_switch(self, source, sink):
        """Get the routing switch for connection ``source`` -> ``sink``.

        Arg:
            source (`AbstractGenericNet`): Hierarchical source bit
            sink (`AbstractGenericNet`): Hierarchical sink bit
        """
        return self.vpr_switches[0].name

TimingDelegate._default_switches = (TimingDelegate.Switch("default", 1e-11), )

# ----------------------------------------------------------------------------
# -- Base Class for VPR arch.xml Generation ----------------------------------
# ----------------------------------------------------------------------------
class _VPRArchGeneration(Object, AbstractPass):
    """Base generator for VPR's architecture description XML."""

    __slots__ = ['output_file', 'fasm', 'timing',                           # customizable variables
            'xml', 'active_blocks', 'active_primitives', 'active_directs',  # temporary variables 
            'lut_sizes',                                                    # temporary variables
            ]
    def __init__(self, output_file, *, fasm = None, timing = None):
        self.output_file = output_file
        self.fasm = fasm
        self.timing = timing

    @property
    def is_readonly_pass(self):
        return True

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

    def _tile(self, block, ori = None):
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
            # 2. FC: done per subclass
            self._fc(block, ori)
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

    def _interconnect(self, sink, hierarchy = None, parent_name = None):
        sources = NetUtils.get_multisource(sink)
        if len(sources) == 0:
            return
        type_ = "direct" if len(sources) == 1 else "mux"
        # get a unique name for the interconnect
        name = [type_]
        if sink.bus_type.is_slice:
            if sink.bus.parent.module_class.is_mode:
                name.append( sink.bus.parent.key )
        else:
            if sink.parent.module_class.is_mode:
                name.append( sink.parent.key )
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
        # generate XML tag
        fasm_muxes = {}
        with self.xml.element(type_, {
            "name": "_".join(name),
            "input": self._net2vpr(sources, parent_name),
            "output": self._net2vpr(sink, parent_name),
            }):
            sink_vpr = self._net2vpr(sink, parent_name)
            for src in sources:
                src_vpr = self._net2vpr(src, parent_name)
                # FASM mux
                fasm_mux = self.fasm.fasm_mux_for_intrablock_switch(src, sink, hierarchy)
                if fasm_mux:
                    fasm_muxes[src_vpr] = ", ".join(fasm_mux)
                elif len(sources) > 1:
                    fasm_muxes[src_vpr] = 'ignored'
                # pack pattern
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
                # timing
                max_, min_ = self.timing.vpr_delay_of_intrablock_switch(src, sink, hierarchy)
                if not (max_ is None and min_ is None):
                    attrs = {
                            "in_port": self._net2vpr(src),
                            "out_port": self._net2vpr(sink),
                            }
                    if max_ is not None:
                        attrs["max"] = max_
                    if min_ is not None:
                        attrs["min"] = min_
                    self.xml.element_leaf("delay_constant", attrs)
            if not all(fasm_mux.startswith("ignored") for fasm_mux in itervalues(fasm_muxes)):
                with self.xml.element("metadata"):
                    self.xml.element_leaf("meta", {"name": "fasm_mux"},
                            '\n'.join('{} : {}'.format(src, features) for src, features in iteritems(fasm_muxes)))

    def _leaf_pb_type(self, hierarchy):
        instance = hierarchy[0]
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
                        # this timing is forced to be fake now. It will be fixed later when dual-mode IO is handled as
                        # a multi-mode primitive instead of a special primitive
                        self.xml.element_leaf('delay_constant', {'max': '1e-11',
                            'in_port': 'inpad.inpad', 'out_port': '{}.inpad'.format(instance.name)})
                    fasm_features = '\n'.join(self.fasm.fasm_features_for_mode(hierarchy, "inpad"))
                    if fasm_features:
                        with self.xml.element("metadata"):
                            self.xml.element_leaf('meta', {'name': 'fasm_features'}, fasm_features)
                # mode: outpad
                with self.xml.element('mode', {'name': 'outpad'}):
                    with self.xml.element('pb_type', {'name': 'outpad', 'blif_model': '.output', 'num_pb': '1'}):
                        self.xml.element_leaf('input', {'name': 'outpad', 'num_pins': '1'})
                    with self.xml.element('interconnect'), self.xml.element('direct', {'name': 'outpad',
                        'output': 'outpad.outpad', 'input': '{}.outpad'.format(instance.name)}):
                        self.xml.element_leaf('delay_constant', {'max': '1e-11',
                            'out_port': 'outpad.outpad', 'in_port': '{}.outpad'.format(instance.name)})
                    fasm_features = '\n'.join(self.fasm.fasm_features_for_mode(hierarchy, "outpad"))
                    if fasm_features:
                        with self.xml.element("metadata"):
                            self.xml.element_leaf('meta', {'name': 'fasm_features'}, fasm_features)
            return
        elif primitive.primitive_class.is_multimode:
            with self.xml.element("pb_type", {"name": instance.name, "num_pb": 1}):
                # 1. emit ports:
                for port in itervalues(primitive.ports):
                    attrs = {'name': port.name, 'num_pins': len(port)}
                    self.xml.element_leaf(
                            'clock' if port.is_clock else port.direction.case('input', 'output'),
                            attrs)
                # 2. enumerate modes
                for mode_name, mode in iteritems(primitive.modes):
                    with self.xml.element("mode", {"name": mode_name}):
                        self._pb_type_body(mode, hierarchy)
            return
        attrs = {'name': instance.name, 'num_pb': '1'}
        bitwise_timing = True
        if primitive.primitive_class.is_lut:
            self.lut_sizes.add( len(primitive.ports['in']) )
            bitwise_timing = False
            attrs.update({"blif_model": ".names", "class": "lut"})
        elif primitive.primitive_class.is_flipflop:
            attrs.update({"blif_model": ".latch", "class": "flipflop"})
        elif primitive.primitive_class.is_inpad:
            attrs.update({"blif_model": ".input"})
        elif primitive.primitive_class.is_outpad:
            attrs.update({"blif_model": ".output"})
        elif primitive.primitive_class.is_memory:
            self.active_primitives.add( primitive.key )
            bitwise_timing = False
            attrs.update({"class": "memory",
                "blif_model": ".subckt " + getattr(primitive, "vpr_model", primitive.name), })
        elif primitive.primitive_class.is_custom:
            self.active_primitives.add( primitive.key )
            bitwise_timing = getattr(primitive, "vpr_bitwise_timing", True)
            attrs.update({
                "blif_model": ".subckt " + getattr(primitive, "vpr_model", primitive.name), })
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
                outputs_with_comb_path = set()
                if port.direction.is_input:
                    # combinational sinks
                    for sink_name in getattr(port, "vpr_combinational_sinks", tuple()):
                        sink = primitive.ports[sink_name]
                        outputs_with_comb_path.add(sink)
                        delay, max_of_max, min_of_min = {}, None, None
                        for srcbit, sinkbit in product(port, sink):
                            max_, min_ = self.timing.vpr_delay_of_primitive_path(srcbit, sinkbit, hierarchy)
                            delay[NetUtils._reference(srcbit), NetUtils._reference(sinkbit)] = max_, min_
                            if max_ is not None and (max_of_max is None or max_ > max_of_max):
                                max_of_max = max_
                            if min_ is not None and (min_of_min is None or min_ < min_of_min):
                                min_of_min = min_
                        if max_of_max is None:
                            raise PRGAInternalError("Max delay required for comb. path from '{}' to '{}' in '{}'"
                                    .format(port, sink, hierarchy))
                        if bitwise_timing:
                            for srcbit, sinkbit in product(port, sink):
                                max_, min_ = delay[NetUtils._reference(srcbit), NetUtils._reference(sinkbit)]
                                min_ = uno(min_, min_of_min)
                                attrs = {"max": uno(max_, max_of_max),
                                        "in_port": self._net2vpr(srcbit, instance.name),
                                        "out_port": self._net2vpr(sinkbit, instance.name), }
                                if min_ is not None:
                                    attrs["min"] = min_
                                self.xml.element_leaf("delay_constant", attrs)
                        else:
                            attrs = {"max": max_of_max,
                                    "in_port": self._net2vpr(port, instance.name),
                                    "out_port": self._net2vpr(sink, instance.name), }
                            if min_of_min is not None:
                                attrs["min"] = min_of_min
                            self.xml.element_leaf("delay_constant", attrs)
                # clocked?
                if port.clock is not None:
                    clock = primitive.ports[port.clock]
                    # setup & hold
                    if port.direction.is_input or port in outputs_with_comb_path:
                        setup, max_setup = [], None
                        for i, bit in enumerate(port):
                            this_setup = self.timing.vpr_setup_time_of_primitive_port(bit, hierarchy)
                            setup.append(this_setup)
                            if this_setup is not None and (max_setup is None or this_setup > max_setup):
                                max_setup = this_setup
                        if max_setup is None:
                            raise PRGAInternalError("Setup time required for seq. endpoint '{}' in '{}'"
                                    .format(port, hierarchy))
                        if bitwise_timing:
                            for i, bit in enumerate(port):
                                self.xml.element_leaf("T_setup", {
                                    "port": self._net2vpr(bit, instance.name),
                                    "value": uno(setup[i], max_setup),
                                    "clock": clock.name, })
                        else:
                            self.xml.element_leaf("T_setup", {
                                "port": self._net2vpr(port, instance.name),
                                "value": max_setup,
                                "clock": clock.name, })
                    # clk2q
                    if port.direction.is_output or getattr(port, "vpr_combinational_sinks", False):
                        clk2q, max_of_max, min_of_min = [], None, None
                        for i, bit in enumerate(port):
                            max_, min_ = self.timing.vpr_clk2q_time_of_primitive_port(port, hierarchy)
                            clk2q.append( (max_, min_) )
                            if max_ is not None and (max_of_max is None or max_ > max_of_max):
                                max_of_max = max_
                            if min_ is not None and (min_of_min is None or min_ < min_of_min):
                                min_of_min = min_
                        if max_of_max is None:
                            raise PRGAInternalError("Max clk-to-Q time required for seq. startpoint '{}' in '{}'"
                                    .format(port, hierarchy))
                        if bitwise_timing:
                            for i, bit in enumerate(port):
                                max_, min_ = clk2q[i]
                                min_ = uno(min_, min_of_min)
                                attrs = {"max": uno(max_, max_of_max),
                                        "port": self._net2vpr(bit, instance.name),
                                        "clock": clock.name, }
                                if min_ is not None:
                                    attrs["min"] = min_
                                self.xml.element_leaf("T_clock_to_Q", attrs)
                        else:
                            attrs = {"max": max_of_max,
                                    "port": self._net2vpr(port, instance.name),
                                    "clock": clock.name, }
                            if min_of_min is not None:
                                attrs["min"] = min_of_min
                            self.xml.element_leaf("T_clock_to_Q", attrs)
            # 3. FASM parameters
            fasm_params = self.fasm.fasm_params_for_primitive(hierarchy)
            if fasm_params:
                with self.xml.element('metadata'):
                    self.xml.element_leaf("meta", {"name": "fasm_params"},
                        '\n'.join("{} = {}".format(config, param) for param, config in iteritems(fasm_params)))

    def _pb_type_body(self, module, hierarchy = None):
        parent_name = hierarchy[0].name if hierarchy else module.name
        # 1. emit cluster/primitive instances
        fasm_luts = {}
        for instance in itervalues(module.instances):
            hierarchical_instance = (hierarchy.delve(instance, no_check = module.module_class.is_mode)
                    if hierarchy else instance)
            if instance.model.module_class.is_cluster:
                self._pb_type(instance.model, hierarchical_instance)
            elif instance.model.module_class.is_primitive:
                self._leaf_pb_type(hierarchical_instance)
                if instance.model.primitive_class.is_lut:
                    fasm_lut = self.fasm.fasm_lut(hierarchical_instance)
                    if fasm_lut:
                        fasm_luts[instance.name] = fasm_lut
                    else:
                        fasm_luts[instance.name] = 'ignored[{}:0]'.format(2 ** len(instance.pins['in']) - 1)
        # 2. emit interconnect
        with self.xml.element('interconnect'):
            for net in chain(itervalues(module.ports),
                    iter(pin for inst in itervalues(module.instances) for pin in itervalues(inst.pins))):
                if not net.is_sink:
                    continue
                for sink in net:
                    self._interconnect(sink, hierarchy, parent_name)
        # 3. FASM metadata
        fasm_features = ''
        if module.module_class.is_mode:
            fasm_features = '\n'.join(self.fasm.fasm_features_for_mode(hierarchy, module.key))
        fasm_prefix = self.fasm.fasm_prefix_for_intrablock_module(hierarchy)
        if all(fasm_lut.startswith("ignored") for fasm_lut in itervalues(fasm_luts)):
            fasm_luts = {}
        if not (fasm_features or fasm_prefix or fasm_luts):
            return
        with self.xml.element("metadata"):
            if fasm_features:
                self.xml.element_leaf('meta', {'name': 'fasm_features'}, fasm_features)
            if fasm_prefix:
                self.xml.element_leaf('meta', {'name': 'fasm_prefix'}, fasm_prefix)
            if len(fasm_luts) > 1:
                self.xml.element_leaf('meta', {'name': 'fasm_type'}, 'SPLIT_LUT')
                self.xml.element_leaf('meta', {'name': 'fasm_lut'},
                        '\n'.join('{} = {}[0]'.format(lut, name) for name, lut in iteritems(fasm_luts)))
            elif len(fasm_luts) == 1:
                name, lut = next(iter(iteritems(fasm_luts)))
                self.xml.element_leaf('meta', {'name': 'fasm_type'}, 'LUT')
                self.xml.element_leaf('meta', {'name': 'fasm_lut'},
                        '{} = {}'.format(lut, name))

    def _pb_type(self, module, hierarchy = None):
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
            # 2. emit pb_type body
            self._pb_type_body(module, hierarchy)

    def _model(self, primitive, vpr_name):
        with self.xml.element("model", {"name": vpr_name}):
            with self.xml.element("output_ports"):
                for port in itervalues(primitive.ports):
                    if port.direction.is_input:
                        continue
                    attrs = {"name": port.name}
                    if port.is_clock:
                        attrs["is_clock"] = "1"
                    elif port.clock is not None:
                        attrs["clock"] = port.clock
                    self.xml.element_leaf("port", attrs)
            with self.xml.element("input_ports"):
                for port in itervalues(primitive.ports):
                    if port.direction.is_output:
                        continue
                    attrs = {"name": port.name}
                    if port.is_clock:
                        attrs["is_clock"] = "1"
                    else:
                        if port.clock is not None:
                            attrs["clock"] = port.clock
                        if getattr(port, "vpr_combinational_sinks", False):
                            attrs["combinational_sink_ports"] = " ".join(port.vpr_combinational_sinks)
                    self.xml.element_leaf("port", attrs)

    def _direct(self, tunnel):
        vpr_offset = tunnel.source.position - tunnel.sink.position - tunnel.offset
        self.xml.element_leaf("direct", {
            "name": tunnel.name,
            "from_pin": "{}.{}".format(tunnel.source.parent.name, tunnel.source.name),
            "to_pin": "{}.{}".format(tunnel.sink.parent.name, tunnel.sink.name),
            "x_offset": vpr_offset.x,
            "y_offset": vpr_offset.y,
            "z_offset": 0,
            })

    def run(self, context):
        # create and add VPR summary if not present
        if not hasattr(context.summary, 'vpr'):
            context.summary.vpr = {}
        # output file update to the VPR summary is done per subclass
        if isinstance(self.output_file, basestring):
            f = os.path.abspath(self.output_file)
            makedirs(os.path.dirname(f))
            self._update_output_file(context.summary.vpr, f)
            self.output_file = open(f, OpenMode.wb)
        else:
            f = os.path.abspath(self.output_file.name)
            makedirs(os.path.dirname(f))
            self._update_output_file(context.summary.vpr, f)
        # FASM 
        if self.fasm is None:
            self.fasm = context.fasm_delegate
        self.fasm.reset()
        # timing
        if self.timing is None:
            self.timing = TimingDelegate()  # fake timing
        self.timing.reset()
        # link and reset context summary
        if self._update_summary:
            self.active_blocks = context.summary.active_blocks = OrderedDict()
            self.active_primitives = context.summary.active_primitives = set()
            self.lut_sizes = context.summary.lut_sizes = set()
        else:
            self.active_blocks = OrderedDict()
            self.active_primitives = set()
            self.lut_sizes = set()
        self.active_directs = []
        # XML generation
        with XMLGenerator(self.output_file, True) as xml, xml.element("architecture"):
            self.xml = xml
            # layout: done per subclass
            with xml.element("layout"):
                self._layout(context)
            # directs:
            for tunnel in itervalues(context.tunnels):
                if tunnel.source.parent.key in self.active_blocks and tunnel.sink.parent.key in self.active_blocks:
                    self.active_directs.append(tunnel)
            if self.active_directs:
                with xml.element("directlist"):
                    for tunnel in self.active_directs:
                        self._direct(tunnel)
            # physical tiles
            with xml.element("tiles"):
                for block_key, orilist in iteritems(self.active_blocks):
                    block = context.database[ModuleView.user, block_key]
                    if block.module_class.is_io_block:
                        for ori in orilist:
                            self._tile(block, ori)
                    else:
                        self._tile(block)
            # complex blocks
            with xml.element("complexblocklist"):
                for block_key in self.active_blocks:
                    self._pb_type(context.database[ModuleView.user, block_key])
            # models
            with xml.element("models"):
                generated = set()
                for model_key in self.active_primitives:
                    model = context.database[ModuleView.user, model_key]
                    vpr_model = getattr(model, "vpr_model", model.name)
                    if vpr_model in generated:
                        continue
                    else:
                        generated.add(vpr_model)
                        self._model(model, vpr_model)
            # device: done per subclass
            with xml.element("device"):
                self._device(context)
            # switches: based on timing delegate
            with xml.element("switchlist"):
                for switch in self.timing.vpr_switches:
                    xml.element_leaf("switch", {
                        "type": "mux",      # type forced to mux
                        "name": switch.name,
                        "R": switch.R,
                        "Cin": switch.Cin,
                        "Cout": switch.Cout,
                        "Tdel": switch.Tdel,
                        "mux_trans_size": switch.mux_trans_size,
                        "buf_size": switch.buf_size,
                        })
            # segments:
            with xml.element("segmentlist"):
                for segment in itervalues(context.segments):
                    segment = self.timing.vpr_segment(segment)
                    with xml.element('segment', {
                        'name': segment.name,
                        'freq': segment.freq,
                        'length': segment.length,
                        'type': 'unidir',   # type forced to unidir
                        'Rmetal': segment.Rmetal,
                        'Cmetal': segment.Cmetal,
                        }):
                        xml.element_leaf('mux', {'name': segment.mux})
                        xml.element_leaf('sb', {'type': 'pattern'},
                                ' '.join(map(str, segment.sb_pattern)))
                        xml.element_leaf('cb', {'type': 'pattern'},
                                ' '.join(map(str, segment.cb_pattern)))
            # clean up
            del xml

    # -- properties/methods to be overriden/implemented by sub-classes -------
    @abstractproperty
    def _update_summary(self):
        raise NotImplementedError

    @abstractmethod
    def _update_output_file(self, summary, output_file):
        raise NotImplementedError

    @abstractmethod
    def _layout(self, context):
        # This method must also update ``active_blocks``
        raise NotImplementedError

    @abstractmethod
    def _fc(self, block, ori):
        raise NotImplementedError

    @abstractmethod
    def _device(self, context):
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- VPR arch.xml Generation -------------------------------------------------
# ----------------------------------------------------------------------------
class VPRArchGeneration(_VPRArchGeneration):
    """Generate VPR's architecture description XML."""

    __slots__ = ['ios']

    @property
    def key(self):
        return "vpr.arch"

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
        ori = cbox_presence[0].opposite
        if not array.edge[ori]:
            raise PRGAInternalError(("Connection box found to the {} of IO block '{}' at {} but "
                "the block is not on the {} edge of the FPGA")
                .format(cbox_presence[0].name, blk_inst.model.name, position, ori.name))
        return ori

    @property
    def _update_summary(self):
        return True

    def _update_output_file(self, summary, output_file):
        summary["arch"] = output_file

    def _layout_array(self, array, hierarchy = None, elaborated = None):
        elaborated = uno(elaborated, set())
        if array.module_class.is_nonleaf_array:
            if not hierarchy:
                ModuleUtils.elaborate(array, True, lambda x: x.model.module_class.is_leaf_array)
                for instance in itervalues(array.instances):
                    self._layout_array(instance.model, instance, elaborated)
            else:
                for instance in itervalues(array.instances):
                    self._layout_array(instance.model, hierarchy.delve(instance), elaborated)
        else:
            if array.key not in elaborated:
                ModuleUtils.elaborate(array, True, lambda x: x.model.module_class.is_block)
                elaborated.add(array.key)
            position = NonLeafArrayBuilder._instance_position(hierarchy) if hierarchy is not None else Position(0, 0)
            for x, y in product(range(array.width), range(array.height)):
                blk_inst = array.instances.get( ((x, y), Subtile.center) )
                if blk_inst is None:
                    continue
                fasm_prefix = '\n'.join(self.fasm.fasm_prefix_for_tile(
                    hierarchy.delve(blk_inst) if hierarchy is not None else blk_inst ))
                attrs = {'priority': 1, 'x': position.x + x, 'y': position.y + y}
                if blk_inst.model.module_class.is_io_block:
                    # special process needed for IO blocks
                    # determine the orientation of this IO block
                    ori = self._iob_orientation(blk_inst)
                    self.active_blocks.setdefault(blk_inst.model.key, set()).add(ori)
                    for iotype in (IOType.ipin, IOType.opin):
                        if iotype.case('inpad', 'outpad') in blk_inst.model.instances['io'].pins:
                            for i in range(blk_inst.model.capacity):
                                self.ios.append( (iotype, Position(position.x + x, position.y + y), i) )
                    attrs['type'] = blk_inst.model.name + '_' + ori.name[0]
                else:
                    self.active_blocks[blk_inst.model.key] = True
                    attrs['type'] = blk_inst.model.name
                if fasm_prefix:
                    with self.xml.element('single', attrs), self.xml.element("metadata"):
                        self.xml.element_leaf("meta", {"name": "fasm_prefix"}, fasm_prefix)
                else:
                    self.xml.element_leaf("single", attrs)

    def _layout(self, context):
        self.ios = context.summary.ios = []
        with self.xml.element("fixed_layout",
                {"name": context.top.name, "width": context.top.width, "height": context.top.height}):
            self._layout_array(context.top)

    def _fc(self, block, ori):
        zero_overrides = set()
        for d in self.active_directs:
            for port in (d.source, d.sink):
                if port.parent is block:
                    zero_overrides.add( port.key )
        if zero_overrides:
            with self.xml.element("fc",
                    {"in_type": "frac", "in_val": "1.0", "out_type": "frac", "out_val": "1.0"}):
                for port in zero_overrides:
                    self.xml.element_leaf("fc_override",
                            {"fc_type": "frac", "fc_val": 0., "port_name": port})
        else:
            self.xml.element_leaf("fc",
                    {"in_type": "frac", "in_val": "1.0", "out_type": "frac", "out_val": "1.0"})

    def _device(self, context):
        # fake device
        self.xml.element_leaf('sizing', {'R_minW_nmos': '0.0', 'R_minW_pmos': '0.0'})
        self.xml.element_leaf('connection_block', {'input_switch_name': self.timing.vpr_switches[0].name})
        self.xml.element_leaf('area', {'grid_logic_tile_area': '0.0'})
        self.xml.element_leaf('switch_block', {'type': 'wilton', 'fs': '3'})
        self.xml.element_leaf('default_fc',
                {'in_type': 'frac', 'in_val': '1.0', 'out_type': 'frac', 'out_val': '1.0'})
        with self.xml.element('chan_width_distr'):
            self.xml.element_leaf('x', {'distr': 'uniform', 'peak': '1.0'})
            self.xml.element_leaf('y', {'distr': 'uniform', 'peak': '1.0'})

# ----------------------------------------------------------------------------
# -- VPR Scalable arch.xml Generation Delegate -------------------------------
# ----------------------------------------------------------------------------
class VPRScalableDelegate(Object):
    """Delegate for generating a scalable VPR architecture XML."""

    __slots__ = ['active_tiles', 'device', 'layout_rules', 'aspect_ratio']
    def __init__(self, aspect_ratio, *, device = None):
        self.aspect_ratio = aspect_ratio
        self.active_tiles = OrderedDict()
        self.device = uno(device, {})
        self.layout_rules = []

    def add_active_tile(self, block, ori = None, fc = None):
        fc = BlockFCValue._construct(uno(fc, (1., 1.)))
        if block.module_class.is_io_block:
            if ori is None:
                raise PRGAAPIError("An edge must be specified for IO block: {}".format(block))
            elif ori in self.active_tiles.setdefault(block.key, {}):
                _logger.warning("Overriding previously added active tile: {}-{}".format(block, ori.name))
            self.active_tiles[block.key][ori] = fc
        else:
            if block.key in self.active_tiles:
                _logger.warning("Overriding previously added active tile: {}".format(block))
            self.active_tiles[block.key] = fc

    _rule_args = {
            "fill": {},
            "perimeter": {},
            "corners": {},
            "single": {"x": True, "y": True},
            "col": {"startx": True, "repeatx": False, "starty": False, "incry": False},
            "row": {"starty": True, "repeaty": False, "startx": False, "incrx": False},
            "region": {"startx": False, "endx": False, "repeatx": False, "incrx": False,
                "starty": False, "endy": False, "repeaty": False, "incry": False},
            }

    def add_layout_rule(self, rule, priority, block, ori = None, **kwargs):
        # verify if ``block`` and ``ori`` are valid
        type_ = "EMPTY"
        if block is not None:
            if block.module_class.is_io_block:
                if ori is None:
                    raise PRGAAPIError("An edge must be specified for IO block: {}".format(block))
                elif block.key not in self.active_tiles or ori not in self.active_tiles[block.key]:
                    raise PRGAAPIError("Tile {}-{} is not activated yet".format(block, ori))
                type_ = "{}_{}".format(block.name, ori.name[0])
            else:
                if block.key not in self.active_tiles:
                    raise PRGAAPIError("Tile {} is not activated yet".format(block))
                type_ = block.name
        # assemble the rule
        if rule not in self._rule_args:
            raise PRGAAPIError("Unknown rule type: {}".format(rule))
        attrs = {"type": type_, "priority": priority}
        for k, required in iteritems(self._rule_args[rule]):
            v = kwargs.get(k)
            if v is None:
                if required:
                    raise PRGAAPIError("Missing required keyword argument '{}' for rule '{}'".format(k, rule))
            else:
                attrs[k] = v
        self.layout_rules.append( (rule, attrs) ) 

# ----------------------------------------------------------------------------
# -- VPR Scalable arch.xml Generation ----------------------------------------
# ----------------------------------------------------------------------------
class VPRScalableArchGeneration(_VPRArchGeneration):
    """Generate a scalable version of VPR's architecture description XML.

    **WARNING**: The routing graph generated by VPR during FPGA sizing and routing channel fitting is almost
    guaranteed to be different than the underlying architecture. Use the generated architecture description only for
    exploring, but then use fixed layout and channel width for your real chip.
    """

    __slots__ = ['delegate', 'update_summary']
    def __init__(self, output_file, delegate, *, update_summary = False, timing = None):
        super(VPRScalableArchGeneration, self).__init__(output_file, fasm = FASMDelegate(), timing = timing)
        self.delegate = delegate
        self.update_summary = update_summary

    @property
    def key(self):
        return "vpr.scalable_arch"

    @property
    def _update_summary(self):
        return self.update_summary

    def _update_output_file(self, summary, output_file):
        summary["scalable_arch"] = output_file

    def _layout(self, context):
        # update active_blocks
        for key in self.delegate.active_tiles:
            block = context.database[ModuleView.user, key]
            if block.module_class.is_io_block:
                for ori in self.delegate.active_tiles[key]:
                    self.active_blocks.setdefault(key, set()).add(ori)
            else:
                self.active_blocks[key] = True
        # generate layout
        with self.xml.element("auto_layout", {"aspect_ratio": self.delegate.aspect_ratio}):
            for rule, attrs in self.delegate.layout_rules:
                self.xml.element_leaf(rule, attrs)

    def _fc(self, block, ori):
        fc = self.delegate.active_tiles[block.key] if ori is None else self.delegate.active_tiles[block.key][ori]
        for d in self.active_directs:
            for port in (d.source, d.sink):
                if port.parent is block and port.key not in fc.overrides:
                    fc.overrides[port.key] = BlockPortFCValue(0)
        attrs = {
                "in_type": "abs" if isinstance(fc.default_in.default, int) else "frac",
                "in_val": fc.default_in.default,
                "out_type": "abs" if isinstance(fc.default_out.default, int) else "frac",
                "out_val": fc.default_out.default,
                }
        if fc.overrides:
            with self.xml.element("fc", attrs):
                for name, port_fc in iteritems(fc.overrides):
                    self.xml.element_leaf("fc_override", {"fc_val": port_fc.default, "port_name": name,
                        "fc_type": "abs" if isinstance(port_fc.default, int) else "frac"})
                    for sgmt, sgmt_fc in iteritems(port_fc.overrides):
                        self.xml.element_leaf("fc_override",
                                {"fc_val": sgmt_fc, "port_name": name, "segment_name": sgmt, 
                                    "fc_type": "abs" if isinstance(sgmt_fc, int) else "frac"})
        else:
            self.xml.element_leaf("fc", attrs)

    def _device(self, context):
        # fake device
        self.xml.element_leaf('sizing', self.delegate.device.get("sizing",
            {'R_minW_nmos': 0., 'R_minW_pmos': 0.}))
        self.xml.element_leaf('connection_block', self.delegate.device.get("connection_block",
            {'input_switch_name': self.timing.vpr_switches[0].name}))
        self.xml.element_leaf('area', self.delegate.device.get("area",
            {'grid_logic_tile_area': 0.}))
        self.xml.element_leaf('switch_block', self.delegate.device.get("switch_block",
            {'type': 'wilton', 'fs': '3'}))
        self.xml.element_leaf('default_fc', self.delegate.device.get("default_fc",
                {'in_type': 'frac', 'in_val': '1.0', 'out_type': 'frac', 'out_val': '1.0'}))
        with self.xml.element('chan_width_distr'):
            self.xml.element_leaf('x', {'distr': 'uniform', 'peak': '1.0'})
            self.xml.element_leaf('y', {'distr': 'uniform', 'peak': '1.0'})

# ----------------------------------------------------------------------------
# -- VPR rrg.xml Generation --------------------------------------------------
# ----------------------------------------------------------------------------
class VPR_RRG_Generation(Object, AbstractPass):
    """Generate VPR's routing resource graph XML."""

    __slots__ = ['output_file', 'fasm', 'timing',                           # customizable variables
            # temporary variables:
            'xml', 'block2id', 'blockpin2ptc', 'switch2id',
            'sgmt2id', 'sgmt2ptc', 'sgmt2node_id', 'sgmt2node_id_truncated',
            'chanx_id', 'chany_id', 'srcsink_id', 'blockpin_id',
            ]
    def __init__(self, output_file, *, fasm = None, timing = None):
        self.output_file = output_file
        self.fasm = fasm
        self.timing = timing

    @property
    def key(self):
        return "vpr.rrg"

    @property
    def dependences(self):
        return "vpr.arch"

    @property
    def is_readonly_pass(self):
        return True

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
                return inst.model, VPRArchGeneration._iob_orientation(inst)
            else:
                return inst.model, None

    @classmethod
    def _calc_hierarchical_position(cls, hierarchy, base = Position(0, 0)):
        return sum(iter(i.key[0] if i.parent.module_class.is_leaf_array else i.key for i in hierarchy), base)

    @classmethod
    def _analyze_routable_pin(cls, pin):
        bus = pin.bus if pin.bus_type.is_slice else pin
        if isinstance(bus.model.key, SegmentID):    # segment
            node = bus.model.key
            chan_offset = Position(*bus.hierarchy[0].key[1].case(
                    northeast = node.orientation.case((0, 1), (1, 0), (0, 0), (0, 0)),
                    northwest = node.orientation.case((-1, 1), (0, 0), (-1, 0), (-1, 0)),
                    southeast = node.orientation.case((0, 0), (1, -1), (0, -1), (0, -1)),
                    southwest = node.orientation.case((-1, 0), (0, -1), (-1, -1), (-1, -1)),
                    ))
            section = node.orientation.case(
                    chan_offset.y - node.position.y,
                    chan_offset.x - node.position.x,
                    node.position.y - chan_offset.y,
                    node.position.x - chan_offset.x,
                    )
            chanpos = cls._calc_hierarchical_position(bus.hierarchy) + chan_offset
            return chanpos, node.orientation.dimension, node.orientation.direction, node.prototype.length - section
        else:                                       # block pin
            ori = None
            if bus.hierarchy.model.module_class.is_io_block:
                ori = VPRArchGeneration._iob_orientation(bus.hierarchy[0]).opposite
            else:
                ori = bus.model.orientation
            chanpos = (cls._calc_hierarchical_position(bus.hierarchy) + bus.model.position +
                    ori.case( (0, 0), (0, 0), (0, -1), (-1, 0) ))
            return chanpos, ori.dimension.perpendicular, None, None

    def _tile(self, block, ori = None):
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

    def _grid(self, array):
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
                    ori = VPRArchGeneration._iob_orientation(instance[0])
                    id_ = self.block2id[instance[0].model.key, ori]
                else:
                    id_ = self.block2id[instance[0].model.key, None]
                self.xml.element_leaf("grid_loc", {
                    "block_type_id": id_, "x": x, "y": y,
                    "width_offset": x - rootpos.x, "height_offset": y - rootpos.y})

    def _node(self, type_, id_, ptc, xlow, ylow, *,
            track_dir = None, port_ori = None, xhigh = None, yhigh = None, segment = None):
        node_attr = {"capacity": 1, "id": id_, "type": type_}
        loc_attr = {"xlow": xlow, "ylow": ylow, "ptc": ptc,
                "xhigh": uno(xhigh, xlow), "yhigh": uno(yhigh, ylow)}
        timing_attr = {"C": 0., "R": 0.}
        if type_ in ("CHANX", "CHANY"):
            assert track_dir is not None and segment is not None
            node_attr["direction"] = track_dir.case("INC_DIR", "DEC_DIR")
            #
            # The following code is not right. VPR adds switch input/output capacitance on top of the track
            # capacitance. This is a bit too expensive for us to do it here.
            #
            #   length = 1 + (abs(yhigh - ylow) if type_ == "CHANY" else abs(xhigh - xlow))
            #   timing_attr["C"] = length * segment.Cmetal
            #   timing_attr["R"] = length * segment.Rmetal
        elif type_ in ("IPIN", "OPIN"):
            assert port_ori is not None
            loc_attr["side"] = port_ori.case("TOP", "RIGHT", "BOTTOM", "LEFT")
        with self.xml.element("node", node_attr):
            self.xml.element_leaf("loc", loc_attr)
            self.xml.element_leaf("timing", timing_attr)
            if type_ in ("CHANX", "CHANY"):
                self.xml.element_leaf("segment", {"segment_id": self.sgmt2id[segment.name]})

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
        # 2. channel id base
        node_id_base, before, after = dim.case(self.chanx_id, self.chany_id)[pos.x][pos.y]
        if node_id_base is None:
            _logger.warning("Node ID not assigned for channel {} at {}".format(dim.name, pos))
            return None
        # 3. section?
        section = node.orientation.case(
                north = corner.dotx(Dimension.y).case(1, 0) - node.position.y,
                east = corner.dotx(Dimension.x).case(1, 0) - node.position.x,
                south = corner.dotx(Dimension.y).case(0, 1) + node.position.y,
                west = corner.dotx(Dimension.x).case(0, 1) + node.position.x)
        # 4. segment id base
        segment_node_id_base = (self.sgmt2node_id if dir_.case(before, after)
                else self.sgmt2node_id_truncated)[node.prototype.name]
        # 5. return the ID
        return (node_id_base +
                dir_.case(0, (self.sgmt2node_id if before else self.sgmt2node_id_truncated)["#"]) +
                segment_node_id_base +
                section * node.prototype.width + index)

    def _edges(self, sink, sink_node, sinkpos, sinkdim, sinkdir, sinkspan):
        _logger.debug("Scanning edges leading to node {} ({})"
                .format(sink_node, sink))
        num_edges = 0
        sink_conngraph_node = NetUtils._reference(sink)
        def yield_or_stop(m, n):
            idx, net_key = n
            if isinstance(idx, NetType):
                return False
            elif isinstance(net_key[0], SegmentID):
                return net_key[0].segment_type.is_sboxout
            elif isinstance(net_key[0], BlockPinID):
                return False
            else:
                return True
        def skip(m, n):
            idx, net_key = n
            if isinstance(net_key[0], SegmentID) or isinstance(net_key[0], BlockPinID):
                return not m.hierarchy[net_key[1:]].model.module_class.is_routing_box
            return False
        for path in NetUtils._navigate_backwards(sink.parent, sink_conngraph_node,
                yield_ = yield_or_stop, stop = yield_or_stop, skip = skip):
            src = NetUtils._dereference(sink.parent, path[0])
            srcpos, srcdim, srcdir, srcspan = self._analyze_routable_pin(src)
            src_bus, src_index = (src.bus, src.index) if src.bus_type.is_slice else (src, 0)
            src_node = None
            if isinstance(src_bus.model.key, SegmentID):
                srcori = Orientation.compose(srcdim, srcdir)
                diff = sinkpos - srcpos
                if sinkdir is None:    # track to block pin
                    # 1. same dimension
                    if not (srcdim is sinkdim and srcdim.case(diff.y, diff.x) == 0):
                        _logger.debug(" ... [x] Rejected b/c dim mismatch: {}".format(src))
                        continue
                    # 2. within reach
                    elif not (0 <= srcori.case(diff.y, diff.x, -diff.y, -diff.x) < srcspan):
                        _logger.debug(" ... [x] Rejected b/c out of reach: {}".format(src))
                        continue
                else:               # track to track
                    # 1. if in the same dimension
                    if srcdim is sinkdim:
                        # 1.1 same direction
                        if not (srcdir is sinkdir and srcdim.case(diff.y, diff.x) == 0):
                            _logger.debug(" ... [x] Rejected b/c dir mismatch: {}".format(src))
                            continue
                        # 1.2 within reach
                        elif not (0 < srcori.case(diff.y, diff.x, -diff.y, -diff.x) <= srcspan):
                            _logger.debug(" ... [x] Rejected b/c out of reach: {}".format(src))
                            continue
                    # 2. if in perpendicular dimensions
                    else:
                        if not srcori.case(
                                diff.x == sinkdir.case(1, 0) and 0 <= diff.y < srcspan,
                                diff.y == sinkdir.case(1, 0) and 0 <= diff.x < srcspan,
                                diff.x == sinkdir.case(1, 0) and 0 < -diff.y <= srcspan,
                                diff.y == sinkdir.case(1, 0) and 0 < -diff.x <= srcspan,
                                ):
                            _logger.debug(" ... [x] Rejected b/c out of reach: {}".format(src))
                            continue
                    # 3. append to path
                    path = path + (sink_conngraph_node, )
                src_node = self._calc_track_id(src)
                if src_node is None:
                    continue
            else:
                if sinkdir is not None:     # block pin to track
                    sinkori = Orientation.compose(sinkdim, sinkdir)
                    diff = srcpos - sinkpos
                    # 1. same dimension
                    if not (srcdim is sinkdim and srcdim.case(diff.y, diff.x) == 0):
                        _logger.debug(" ... [x] Rejected b/c dim mismatch: {}".format(src))
                        continue
                    # 2. within reach
                    elif not 0 <= sinkori.case(diff.y, diff.x, -diff.y, -diff.x) < sinkspan:
                        _logger.debug(" ... [x] Rejected b/c out of reach: {}".format(src))
                        continue
                    # 3. append to path
                    path = path + (sink_conngraph_node, )
                src_node = self._calc_blockpin_id(src)
            _logger.debug(" ... [v] Accepted: {}".format(src))
            num_edges += 1
            switch_name = self.timing.vpr_interblock_routing_switch(src, sink)
            attrs = { "src_node": src_node, "sink_node": sink_node, "switch_id": self.switch2id[switch_name]}
            # pair nodes
            assert len(path) % 2 == 1
            fasm_features = []
            for i in range(1, len(path), 2):
                box_input, box_output = map(lambda x: NetUtils._dereference(sink.parent, x),
                        (path[i], path[i + 1]))
                hierarchy = None
                if box_input.bus_type.is_slice:
                    hierarchy = box_input.bus.hierarchy
                    box_input = box_input.bus.model[box_input.index]
                else:
                    hierarchy = box_input.hierarchy
                    box_input = box_input.model
                if box_output.bus_type.is_slice:
                    box_output = box_output.bus.model[box_output.index]
                else:
                    box_output = box_output.model
                fasm_features.extend(self.fasm.fasm_features_for_routing_switch(
                    box_input, box_output, hierarchy))
            if fasm_features:
                with self.xml.element("edge", attrs), self.xml.element("metadata"):
                    self.xml.element_leaf("meta", {"name": "fasm_features"},
                            "\n".join(fasm_features))
            else:
                self.xml.element_leaf("edge", attrs)
        if num_edges:
            _logger.debug(" === {} edges found connected to node {} ({})".format(num_edges, sink_node, sink))
        else:
            _logger.info(" === No edge found connected to node {} ({})".format(sink_node, sink))

    def run(self, context):
        # runtime-generated data
        self.block2id = OrderedDict()
        self.blockpin2ptc = OrderedDict()
        self.switch2id = OrderedDict()
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
        channel_width = context.summary.vpr["channel_width"] = 2 * sum(sgmt.width * sgmt.length
                for sgmt in itervalues(context.segments))
        total_num_nodes = 0
        # VPR nodes: SOURCE & SINK
        self.srcsink_id = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        # VPR nodes: IPIN & OPIN
        self.blockpin_id = [[None for _ in range(context.top.height)] for _ in range(context.top.width)]
        # update VPR summary
        if isinstance(self.output_file, basestring):
            f = os.path.abspath(self.output_file)
            makedirs(os.path.dirname(f))
            context.summary.vpr["rrg"] = f
            self.output_file = open(f, OpenMode.wb)
        else:
            f = os.path.abspath(self.output_file.name)
            makedirs(os.path.dirname(f))
            context.summary.vpr["rrg"] = f
        # FASM 
        if self.fasm is None:
            self.fasm = context.fasm_delegate
        self.fasm.reset()
        # timing
        if self.timing is None:
            self.timing = TimingDelegate()  # fake timing
        self.timing.reset()
        # routing resource graph generation
        with XMLGenerator(self.output_file, True) as xml, xml.element("rr_graph"):
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
                with xml.element('switch', {'id': 0, 'type': 'mux', 'name': '__vpr_delayless_switch__', }):
                    xml.element_leaf('timing', {'R': 0., 'Cin': 0., 'Cout': 0., 'Tdel': 0., })
                    xml.element_leaf('sizing', {'mux_trans_size': 0., 'buf_size': 0., })
                for switch in self.timing.vpr_switches:
                    id_ = self.switch2id[switch.name] = len(self.switch2id) + 1
                    with xml.element('switch', {'id': id_, 'type': 'mux', 'name': switch.name, }):
                        xml.element_leaf('timing',
                                {'R': switch.R, 'Cin': switch.Cin, 'Cout': switch.Cout, 'Tdel': switch.Tdel, })
                        xml.element_leaf('sizing',
                                {'mux_trans_size': switch.mux_trans_size, 'buf_size': switch.buf_size, })
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
                    with self.xml.element("segment", {"name": name, "id": i}):
                        sgmt = self.timing.vpr_segment(sgmt)
                        self.xml.element_leaf("timing", {"R_per_meter": sgmt.Rmetal, "C_per_meter": sgmt.Cmetal})
                self.sgmt2node_id["#"] = node_id
                self.sgmt2node_id_truncated["#"] = node_id_truncated
            # block types
            with xml.element('block_types'):
                xml.element_leaf("block_type", {"id": 0, "name": "EMPTY", "width": 1, "height": 1})
                for block_key in context.summary.active_blocks:
                    block = context.database[ModuleView.user, block_key]
                    if block.module_class.is_io_block:
                        for ori in context.summary.active_blocks[block_key]:
                            self.block2id[block_key, ori] = len(self.block2id) + 1
                            self._tile(block, ori)
                    else:
                        self.block2id[block_key, None] = len(self.block2id) + 1
                        self._tile(block)
            # grid
            with xml.element("grid"):
                self._grid(context.top)
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
                                    self._node(port.direction.case("SINK", "SOURCE"), total_num_nodes,
                                            ptc_base + ptc + i, x, y,
                                            xhigh = x + block.width - 1, yhigh = y + block.height - 1)
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
                                    self._node(port.direction.case("IPIN", "OPIN"), total_num_nodes,
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
                                self._node(dim.case("CHANX", "CHANY"), total_num_nodes, ptc,
                                        ori.case(x, x, x, x - min(before, segment.length - 1 - section)),
                                        ori.case(y, y, y - min(before, segment.length - 1 - section), y),
                                        track_dir = dir_,
                                        xhigh = ori.case(x, x + min(after, segment.length - 1 - section), x, x),
                                        yhigh = ori.case(y + min(after, segment.length - 1 - section), y, y, y),
                                        segment = self.timing.vpr_segment(segment),
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
                        block = inst.model
                        pin2ptc = self.blockpin2ptc[block.key]
                        for subblock in range(block.capacity):
                            inst = NonLeafArrayBuilder._get_hierarchical_root(context.top, pos, subblock)
                            for key in pin2ptc:
                                if key == "#":
                                    continue
                                port = block.ports[key]
                                channel = pos + port.position + port.orientation.case(
                                        (0, 0), (0, 0), (0, -1), (-1, 0))
                                pin = port._to_pin( inst )
                                for bit in pin:
                                    xml.element_leaf('edge', {
                                        'src_node': self._calc_blockpin_id(bit, port.direction.is_output, pos),
                                        'sink_node': self._calc_blockpin_id(bit, port.direction.is_input, pos),
                                        'switch_id': 0,
                                        })
                                if port.direction.is_input and not hasattr(port, 'global_'):
                                    args = self._analyze_routable_pin(pin)
                                    for bit in pin:
                                        self._edges(bit, self._calc_blockpin_id(bit, False, pos), *args)
                    # segments
                    for corner in Corner:
                        inst = NonLeafArrayBuilder._get_hierarchical_root(context.top, pos, corner.to_subtile())
                        if inst is None or not inst.model.module_class.is_switch_box:
                            continue
                        for node, port in iteritems(inst.model.ports):
                            if not node.segment_type.is_sboxout:
                                continue
                            pin = port._to_pin( inst )
                            args = self._analyze_routable_pin(pin)
                            for bit in pin:
                                sink_node = self._calc_track_id(bit)
                                if sink_node is not None:
                                    self._edges(bit, sink_node, *args)
            del self.xml
