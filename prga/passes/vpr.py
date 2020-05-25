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
from ..netlist.module.common import LazyDict
from ..netlist.module.util import ModuleUtils
from ..util import Object, uno
from ..xml import XMLGenerator
from ..exception import PRGAInternalError, PRGAAPIError

import os
import networkx as nx
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
        """Get the "fasm_prefix" string for hierarchical cluster/primitive ``instance``.

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

    def fasm_features_for_routing_switch(self, source, sink, instance = None):
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

    def vpr_interblock_routing_switch(self, source, sink, delay = 1e-11):
        """Get the routing switch for connection ``source`` -> ``sink``.

        Arg:
            source (`AbstractGenericNet`): Hierarchical source bit
            sink (`AbstractGenericNet`): Hierarchical sink bit
        """
        return self.vpr_switches[0]

    def vpr_delay_of_routing_switch(self, source, sink):
        """Get the propagation delay for connection ``source`` -> ``sink``.

        Arg:
            source (`AbstractGenericNet`): Hierarchical source bit
            sink (`AbstractGenericNet`): Hierarchical sink bit
        """
        return 1e-11

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
    def _net2vpr(cls, net, parent_name = None, bitwise = False):
        if net.bus_type.is_concat:
            return " ".join(cls._net2vpr(i, parent_name, bitwise) for i in net.items)
        elif net.net_type.is_const:
            raise PRGAInternalError("Cannot express constant nets in VPR")
        elif bitwise and len(net) > 1:
            return " ".join(cls._net2vpr(i, parent_name) for i in net)
        prefix, suffix = None, ""
        if net.net_type.is_port:
            prefix = '{}.{}'.format(parent_name or net.parent.name, net.bus.name)
        elif hasattr(net.bus.instance.hierarchy[0], "vpr_num_pb"):
            prefix = '{}[{}].{}'.format(net.bus.instance.hierarchy[0].key[0],
                    net.bus.instance.hierarchy[0].key[1], net.bus.model.name)
        else:
            prefix = '{}.{}'.format(net.bus.instance.hierarchy[0].name, net.bus.model.name)
        if net.bus_type.is_slice:
            if net.index.stop == net.index.start + 1:
                suffix = '[{}]'.format(net.index.start)
            else:
                suffix = '[{}:{}]'.format(net.index.stop - 1, net.index.start)
        return prefix + suffix

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
                if getattr(port, "vpr_equivalent_pins", False):
                    attrs["equivalent"] = "full"
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
                    if x not in (0, block.width - 1) and y not in (0, block.height - 1):
                        continue
                    ports = []
                    for port in itervalues(block.ports):
                        if port.position == (x, y) and port.orientation in (None, orientation):
                            ports.append(port)
                    if ports:
                        self.xml.element_leaf("loc", {
                            "side": orientation.case("top", "right", "bottom", "left"),
                            "xoffset": x, "yoffset": y},
                            ' '.join('{}.{}'.format(tile_name, port.name) for port in ports))
            # 4. equivalent sites
            with self.xml.element("equivalent_sites"):
                self.xml.element_leaf("site", {"pb_type": block.name, "pin_mapping": "direct"})

    def _interconnect(self, sink, instance = None, parent_name = None):
        sources = NetUtils.get_multisource(sink)
        if len(sources) == 0:
            return
        type_ = "direct" if len(sources) == 1 else "mux"
        # get a unique name for the interconnect
        name = [type_]
        if sink.bus.parent.module_class.is_mode:
            name.append( sink.bus.parent.key )
        if sink.net_type.is_pin:
            if sink.bus_type.is_slice:
                name.append( sink.bus.instance.name )
                name.append( sink.bus.model.name )
                name.append( str(sink.index.start) )
            else:
                name.append( sink.instance.name )
                name.append( sink.model.name )
        else:
            if sink.bus_type.is_slice:
                name.append( sink.bus.name )
                name.append( str(sink.index.start) )
            else:
                name.append( sink.name )
        # generate XML tag
        fasm_muxes = {}
        with self.xml.element(type_, {
            "name": "_".join(name),
            "input": self._net2vpr(sources, parent_name, bitwise = True),
            "output": (sink_vpr := self._net2vpr(sink, parent_name)),
            }):
            for src in sources:
                src_vpr = self._net2vpr(src, parent_name)
                # FASM mux
                fasm_mux = self.fasm.fasm_mux_for_intrablock_switch(src, sink, instance)
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
                max_, min_ = self.timing.vpr_delay_of_intrablock_switch(src, sink, instance)
                if not (max_ is None and min_ is None):
                    attrs = {
                            "in_port": self._net2vpr(src, parent_name),
                            "out_port": self._net2vpr(sink, parent_name),
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

    def _leaf_pb_type(self, instance, fasm_prefix = None):
        leaf, primitive, attrs = instance.hierarchy[0], instance.model, {}
        if hasattr(leaf, "vpr_num_pb"):
            attrs = {"name": leaf.key[0], "num_pb": leaf.vpr_num_pb}
        else:
            attrs = {"name": leaf.name, "num_pb": 1}
        if primitive.primitive_class.is_multimode:
            with self.xml.element("pb_type", attrs):
                # 1. emit ports:
                for port in itervalues(primitive.ports):
                    attrs = {'name': port.name, 'num_pins': len(port)}
                    self.xml.element_leaf(
                            'clock' if port.is_clock else port.direction.case('input', 'output'),
                            attrs)
                # 2. enumerate modes
                for mode_name, mode in iteritems(primitive.modes):
                    with self.xml.element("mode", {"name": mode_name}):
                        self._pb_type_body(mode, instance)
                # 3. FASM prefix
                if fasm_prefix:
                    with self.xml.element('metadata'):
                        self.xml.element_leaf('meta', {'name': 'fasm_prefix'}, fasm_prefix)
            return
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
        parent_name = attrs["name"]
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
                            max_, min_ = self.timing.vpr_delay_of_primitive_path(srcbit, sinkbit, instance)
                            delay[NetUtils._reference(srcbit), NetUtils._reference(sinkbit)] = max_, min_
                            if max_ is not None and (max_of_max is None or max_ > max_of_max):
                                max_of_max = max_
                            if min_ is not None and (min_of_min is None or min_ < min_of_min):
                                min_of_min = min_
                        if max_of_max is None:
                            raise PRGAInternalError("Max delay required for comb. path from '{}' to '{}' in '{}'"
                                    .format(port, sink, instance))
                        if bitwise_timing:
                            for srcbit, sinkbit in product(port, sink):
                                max_, min_ = delay[NetUtils._reference(srcbit), NetUtils._reference(sinkbit)]
                                min_ = uno(min_, min_of_min)
                                attrs = {"max": uno(max_, max_of_max),
                                        "in_port": self._net2vpr(srcbit, parent_name),
                                        "out_port": self._net2vpr(sinkbit, parent_name), }
                                if min_ is not None:
                                    attrs["min"] = min_
                                self.xml.element_leaf("delay_constant", attrs)
                        else:
                            attrs = {"max": max_of_max,
                                    "in_port": self._net2vpr(port, parent_name),
                                    "out_port": self._net2vpr(sink, parent_name), }
                            if min_of_min is not None:
                                attrs["min"] = min_of_min
                            self.xml.element_leaf("delay_constant", attrs)
                # clocked?
                if hasattr(port, "clock"):
                    clock = primitive.ports[port.clock]
                    # setup & hold
                    if port.direction.is_input or port in outputs_with_comb_path:
                        setup, max_setup = [], None
                        for i, bit in enumerate(port):
                            this_setup = self.timing.vpr_setup_time_of_primitive_port(bit, instance)
                            setup.append(this_setup)
                            if this_setup is not None and (max_setup is None or this_setup > max_setup):
                                max_setup = this_setup
                        if max_setup is None:
                            raise PRGAInternalError("Setup time required for seq. endpoint '{}' in '{}'"
                                    .format(port, instance))
                        if bitwise_timing:
                            for i, bit in enumerate(port):
                                self.xml.element_leaf("T_setup", {
                                    "port": self._net2vpr(bit, parent_name),
                                    "value": uno(setup[i], max_setup),
                                    "clock": clock.name, })
                        else:
                            self.xml.element_leaf("T_setup", {
                                "port": self._net2vpr(port, parent_name),
                                "value": max_setup,
                                "clock": clock.name, })
                    # clk2q
                    if port.direction.is_output or getattr(port, "vpr_combinational_sinks", False):
                        clk2q, max_of_max, min_of_min = [], None, None
                        for i, bit in enumerate(port):
                            max_, min_ = self.timing.vpr_clk2q_time_of_primitive_port(port, instance)
                            clk2q.append( (max_, min_) )
                            if max_ is not None and (max_of_max is None or max_ > max_of_max):
                                max_of_max = max_
                            if min_ is not None and (min_of_min is None or min_ < min_of_min):
                                min_of_min = min_
                        if max_of_max is None:
                            raise PRGAInternalError("Max clk-to-Q time required for seq. startpoint '{}' in '{}'"
                                    .format(port, instance))
                        if bitwise_timing:
                            for i, bit in enumerate(port):
                                max_, min_ = clk2q[i]
                                min_ = uno(min_, min_of_min)
                                attrs = {"max": uno(max_, max_of_max),
                                        "port": self._net2vpr(bit, parent_name),
                                        "clock": clock.name, }
                                if min_ is not None:
                                    attrs["min"] = min_
                                self.xml.element_leaf("T_clock_to_Q", attrs)
                        else:
                            attrs = {"max": max_of_max,
                                    "port": self._net2vpr(port, parent_name),
                                    "clock": clock.name, }
                            if min_of_min is not None:
                                attrs["min"] = min_of_min
                            self.xml.element_leaf("T_clock_to_Q", attrs)
            # 3. FASM parameters
            fasm_params = self.fasm.fasm_params_for_primitive(instance)
            if fasm_params or fasm_prefix:
                with self.xml.element('metadata'):
                    if fasm_params:
                        self.xml.element_leaf("meta", {"name": "fasm_params"},
                            '\n'.join("{} = {}".format(config, param) for param, config in iteritems(fasm_params)))
                    if fasm_prefix:
                        self.xml.element_leaf('meta', {'name': 'fasm_prefix'}, fasm_prefix)

    def _pb_type_body(self, module, instance = None, fasm_prefix = None):
        parent_name = module.name
        if instance:
            if hasattr(instance.hierarchy[0], "vpr_num_pb"):
                parent_name = instance.hierarchy[0].key[0]
            else:
                parent_name = instance.hierarchy[0].name
        # 1. emit cluster/primitive instances
        fasm_luts = {}
        for sub in itervalues(module.instances):
            hierarchical = sub.extend_hierarchy(above = instance)
            vpr_num_pb = getattr(sub, "vpr_num_pb", None)
            if vpr_num_pb is not None:
                if sub.key[1] != 0:
                    continue
                group = tuple( module.instances[sub.key[0], i].extend_hierarchy(above = instance)
                        for i in range(vpr_num_pb) )
                sub_prefix = tuple(self.fasm.fasm_prefix_for_intrablock_module(i) for i in group)
                if any(sub_prefix):
                    sub_prefix = "\n".join(p or "ignored" for p in sub_prefix)
                else:
                    sub_prefix = ''
                if sub.model.module_class.is_cluster:
                    self._pb_type(sub.model, hierarchical, sub_prefix)
                elif sub.model.module_class.is_primitive:
                    self._leaf_pb_type(hierarchical, sub_prefix)
                    if sub.model.primitive_class.is_lut:
                        for i, subsub in enumerate(group):
                            fasm_lut = self.fasm.fasm_lut(subsub)
                            if fasm_lut:
                                fasm_luts['{}[{}]'.format(sub.key[0], i)] = fasm_lut
                            else:
                                fasm_luts['{}[{}]'.format(sub.key[0], i)] = 'ignored[{}:0]'.format(
                                        2 ** len(subsub.pins["in"]) - 1)
            else:
                sub_prefix = self.fasm.fasm_prefix_for_intrablock_module(hierarchical)
                if sub.model.module_class.is_cluster:
                    self._pb_type(sub.model, hierarchical, sub_prefix)
                elif sub.model.module_class.is_primitive:
                    self._leaf_pb_type(hierarchical, sub_prefix)
                    if sub.model.primitive_class.is_lut:
                        fasm_lut = self.fasm.fasm_lut(hierarchical)
                        if fasm_lut:
                            fasm_luts['{}[0]'.format(sub.name)] = fasm_lut
                        else:
                            fasm_luts['{}[0]'.format(sub.name)] = 'ignored[{}:0]'.format(2 ** len(sub.pins["in"]) - 1)
        # 2. emit interconnect
        with self.xml.element('interconnect'):
            for net in chain(itervalues(module.ports),
                    iter(pin for inst in itervalues(module.instances) for pin in itervalues(inst.pins))):
                if not net.is_sink:
                    continue
                for sink in net:
                    self._interconnect(sink, instance, parent_name)
        # 3. FASM metadata
        fasm_features = ''
        if module.module_class.is_mode:
            fasm_features = '\n'.join(self.fasm.fasm_features_for_mode(instance, module.key))
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
                        '\n'.join('{} = {}'.format(lut, name) for name, lut in iteritems(fasm_luts)))
            elif len(fasm_luts) == 1:
                name, lut = next(iter(iteritems(fasm_luts)))
                self.xml.element_leaf('meta', {'name': 'fasm_type'}, 'LUT')
                self.xml.element_leaf('meta', {'name': 'fasm_lut'},
                        '{} = {}'.format(lut, name))

    def _pb_type(self, module, instance = None, fasm_prefix = None):
        attrs, parent_name = {}, module.name
        if instance:
            vpr_num_pb = getattr(instance.hierarchy[0], "vpr_num_pb", None)
            if vpr_num_pb:
                parent_name = instance.hierarchy[0].key[0]
                attrs["num_pb"] = vpr_num_pb
            else:
                parent_name = instance.hierarchy[0].name
                attrs["num_pb"] = 1
        attrs["name"] = parent_name
        with self.xml.element("pb_type", attrs):
            # 1. emit ports:
            for port in itervalues(module.ports):
                attrs = {'name': port.name, 'num_pins': len(port)}
                if not port.is_clock and hasattr(port, 'global_'):
                    attrs['is_non_clock_global'] = "true"
                if getattr(port, "vpr_equivalent_pins", False):
                    attrs["equivalent"] = "full"
                self.xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        attrs)
            # 2. emit pb_type body
            self._pb_type_body(module, instance, fasm_prefix)

    def _model(self, primitive, vpr_name):
        with self.xml.element("model", {"name": vpr_name}):
            with self.xml.element("output_ports"):
                for port in itervalues(primitive.ports):
                    if port.direction.is_input:
                        continue
                    attrs = {"name": port.name}
                    if port.is_clock:
                        attrs["is_clock"] = "1"
                    elif getattr(port, "clock", None) is not None:
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
                        if getattr(port, "clock", None) is not None:
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
        position = blk_inst.hierarchy[0].key[0]
        array = blk_inst.hierarchy[0].parent
        # find the connection box(es) in this tile
        cbox_presence = tuple(ori for ori in iter(Orientation)
                if (position, ori.to_subtile()) in array.instances)
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

    def _layout_array(self, array, instance = None, elaborated = None):
        if array.module_class.is_nonleaf_array:
            for subarray in itervalues(array.instances):
                self._layout_array(subarray.model, subarray.extend_hierarchy(above = instance))
        else:
            position = NonLeafArrayBuilder._instance_position(instance) if instance else Position(0, 0)
            for x, y in product(range(array.width), range(array.height)):
                blk_inst = array.instances.get( ((x, y), Subtile.center) )
                if blk_inst is None:
                    continue
                fasm_prefix = '\n'.join(self.fasm.fasm_prefix_for_tile(
                    blk_inst.extend_hierarchy(above = instance) ))
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
    certain to be different than the underlying architecture. Use the generated architecture description only for
    exploring, and then use fixed layout and channel width for your real chip.
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
            'xml', 'block2id', 'blockpin2ptc', 'switch2id', 'sgmt2id', 'sgmt2ptc',
            "chanx", "chany", "conn_graph",
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

    def _analyze_track(self, node):
        """Analyze a track node.

        Args:
            node (:obj:`Sequence` [:obj:`Hashable` ]): A reference node of a switch box pin (coalesced)

        Returns:
            orientation (`Orientation`): Expansion orientation
            lower_position (`Position`): The lower position of starting/ending channel
            higher_position (`Position`): The higher position of starting/ending channel
            ptc_position (:obj:`int`): Used to calculate the PTC for VPR
        """
        segment, ori = node[0].prototype, node[0].orientation
        sbox_position, corner = sum(node[2:], node[1][0]), node[1][1].to_corner()
        virtual_start = sbox_position + node[0].position
        low = high = (sbox_position + corner.case( (0, 0), (-1, 0), (0, -1), (-1, -1) ) +
                ori.case( (0, 1), (1, 0), (0, 0), (0, 0) ))
        dim, dir_ = ori.decompose()
        chan, step = dim.case((self.chanx, (1, 0)), (self.chany, (0, 1)))
        if dir_.is_inc:
            for _ in range(low[dim] - virtual_start[dim] + 1, segment.length):
                pos = high + step
                if chan[pos.x][pos.y]:
                    high = pos
                else:
                    break
        else:
            for _ in range(virtual_start[dim] - low[dim] + 1, segment.length):
                pos = low - step
                if chan[pos.x][pos.y]:
                    low = pos
                else:
                    break
        return ori, low, high, virtual_start[dim] - dir_.case(1, segment.length)

    def _analyze_blockpin(self, pin):
        """Analyze a block pin node.

        Args:
            pin (`Pin`): Hierarchical pin

        Returns:
            channel_position (`Position`): Position of the routing channel
            orientation (`Orientation`): Orientation of the port
            block_position (`Position`): Position of the parent block instance, used to calculate the
                xlow/ylow/xhigh/yhigh attributes for the src/sink nodes
        """
        port = pin.model
        block_position = NonLeafArrayBuilder._instance_position(pin.instance)
        chan = block_position + port.position
        ori = port.orientation
        if port.parent.module_class.is_io_block:
            ori = VPRArchGeneration._iob_orientation(pin.instance).opposite
        if ori.is_north:
            return chan, ori, block_position
        elif ori.is_east:
            return chan, ori, block_position
        elif ori.is_south:
            return chan - (0, 1), ori, block_position
        else:
            return chan - (1, 0), ori, block_position

    class _NodeOrderedDiGraph(nx.DiGraph):
        class _NodeAttrDict(LazyDict):
            __slots__ = ["id", "srcsink_id", "type", "equivalent"]

        node_dict_factory = OrderedDict
        node_attr_dict_factory = _NodeAttrDict
        edge_attr_dict_factory = LazyDict

    def _construct_conn_graph(self, top):
        node_id = 0
        def create_node(m, n):
            nonlocal node_id
            nonlocal self
            try:
                node, ((x, y), subtile) = n[:2]
            except (ValueError, TypeError):
                return None
            if isinstance(node, SegmentID):
                if node.segment_type.is_sboxout:
                    pos = (sum(n[2:], n[1][0]) + n[1][1].to_corner().case( (0, 0), (-1, 0), (0, -1), (-1, -1) ) +
                            node.orientation.case( (0, 1), (1, 0), (0, 0), (0, 0) ))
                    if node.orientation.dimension.case(self.chanx, self.chany)[pos.x][pos.y]:
                        d = {"id": node_id, "type": "TRACK"}
                        node_id += node.prototype.width
                        return d
                    else:
                        return None
                else:
                    return {}
            elif isinstance(node, BlockPinID):
                return {}
            else:
                net = NetUtils._dereference(m, n, coalesced = True)
                assert net.model.parent.module_class.is_block
                d = {"srcsink_id": node_id, "type": net.model.direction.case("IPIN", "OPIN")}
                if getattr(net.model, "vpr_equivalent_pins", False):
                    d.update({"id": node_id + 1, "equivalent": True})
                    node_id += 1 + len(net)
                else:
                    d["id"] = node_id + len(net)
                    node_id += 2 * len(net)
                return d
        self.conn_graph = ModuleUtils.reduce_timing_graph(top,
                graph_constructor = self._NodeOrderedDiGraph,
                blackbox_instance = lambda i: i.model.module_class.is_block or i.model.module_class.is_routing_box,
                create_node = create_node,
                create_edge = None,
                coalesce_connections = True)

    def _tile_pinlist(self, port, subblock_name, srcsink_ptc, iopin_ptc):
        equivalent = getattr(port, "vpr_equivalent_pins", False)
        if equivalent:
            with self.xml.element("pin_class", {"type": port.direction.case("INPUT", "OUTPUT")}):
                for i in range(len(port)):
                    self.xml.element_leaf("pin", {"ptc": iopin_ptc},
                            '{}.{}[{}]'.format(subblock_name, port.name, i))
                    iopin_ptc += 1
                srcsink_ptc += 1
        else:
            for i in range(len(port)):
                with self.xml.element("pin_class", {"type": port.direction.case("INPUT", "OUTPUT")}):
                    self.xml.element_leaf("pin", {"ptc": iopin_ptc},
                            '{}.{}[{}]'.format(subblock_name, port.name, i))
                iopin_ptc += 1
                srcsink_ptc += 1
        return srcsink_ptc, iopin_ptc

    def _tile(self, block, ori = None):
        blockpin2ptc = self.blockpin2ptc.setdefault( block.key, OrderedDict() )
        block_name = block.name if ori is None else '{}_{}'.format(block.name, ori.name[0])
        with self.xml.element("block_type", {
            "name": block_name, "width": block.width, "height": block.height, "id": self.block2id[block.key, ori]}):
            srcsink_ptc, iopin_ptc = 0, 0
            for subblock in range(block.capacity):
                subblock_name = '{}[{}]'.format(block_name, subblock) if block.capacity > 1 else block_name
                for port in itervalues(block.ports):
                    equivalent = getattr(port, "vpr_equivalent_pins", False)
                    if port.direction.is_input and not port.is_clock:
                        if subblock == 0:
                            blockpin2ptc[port.key] = srcsink_ptc, equivalent, iopin_ptc
                        srcsink_ptc, iopin_ptc = self._tile_pinlist(port, subblock_name, srcsink_ptc, iopin_ptc)
                for port in itervalues(block.ports):
                    if port.direction.is_output:
                        if subblock == 0:
                            blockpin2ptc[port.key] = srcsink_ptc, equivalent, iopin_ptc
                        srcsink_ptc, iopin_ptc = self._tile_pinlist(port, subblock_name, srcsink_ptc, iopin_ptc)
                for port in itervalues(block.ports):
                    if port.is_clock:
                        if subblock == 0:
                            blockpin2ptc[port.key] = srcsink_ptc, equivalent, iopin_ptc
                        srcsink_ptc, iopin_ptc = self._tile_pinlist(port, subblock_name, srcsink_ptc, iopin_ptc)
                if subblock == 0:
                    blockpin2ptc["#"] = srcsink_ptc, None, iopin_ptc

    def _grid(self, array):
        for x, y in product(range(array.width), range(array.height)):
            pos = Position(x, y)
            instance = NonLeafArrayBuilder._get_hierarchical_root(array, Position(x, y), Subtile.center)
            if instance is None:
                self.xml.element_leaf("grid_loc", {
                    "block_type_id": 0, "x": x, "y": y, "width_offset": 0, "height_offset": 0})
            else:
                rootpos = NonLeafArrayBuilder._instance_position(instance)
                if rootpos == pos:
                    for xx, yy in product(range(instance.model.width), range(instance.model.height - 1)):
                        self.chanx[x + xx][y + yy] = False
                    for xx, yy in product(range(instance.model.width - 1), range(instance.model.height)):
                        self.chany[x + xx][y + yy] = False
                id_ = None
                if instance.model.module_class.is_io_block:
                    ori = VPRArchGeneration._iob_orientation(instance)
                    id_ = self.block2id[instance.model.key, ori]
                else:
                    id_ = self.block2id[instance.model.key, None]
                self.xml.element_leaf("grid_loc", {
                    "block_type_id": id_, "x": x, "y": y,
                    "width_offset": x - rootpos.x, "height_offset": y - rootpos.y})

    def _node(self, type_, id_, ptc, xlow, ylow, *,
            track_dir = None, port_ori = None, xhigh = None, yhigh = None, segment = None, capacity = 1):
        node_attr = {"capacity": capacity, "id": id_, "type": type_}
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

    def _edge(self, src_id, sink_id, head_pin_bit = None, tail_pin_bit = None, delay = 0.0, fasm_features = tuple(),
            switch_id = None):
        if switch_id is None:
            switch = self.timing.vpr_interblock_routing_switch(head_pin_bit, tail_pin_bit, delay)
            switch_id = self.switch2id[switch.name]
        attrs = {"src_node": src_id,
                "sink_node": sink_id,
                "switch_id": switch_id,
                }
        if fasm_features:
            with self.xml.element("edge", attrs), self.xml.element("metadata"):
                self.xml.element_leaf("meta", {"name": "fasm_features"},
                        "\n".join(fasm_features))
        else:
            self.xml.element_leaf("edge", attrs)

    def _edge_box_output(self, head_pin_bit, tail_pin_bit, tail_pkg, fasm_features = tuple(), delay = 0.0):
        sink_port_bit = head_pin_bit.bus.model[head_pin_bit.index]
        for src_port_bit in NetUtils.get_multisource(sink_port_bit):
            this_fasm = fasm_features + self.fasm.fasm_features_for_routing_switch(src_port_bit, sink_port_bit,
                    head_pin_bit.bus.instance)
            this_delay = delay + self.timing.vpr_delay_of_routing_switch(src_port_bit, sink_port_bit)
            self._edge_box_input(head_pin_bit.bus.instance.pins[src_port_bit.bus.key][src_port_bit.index],
                    tail_pin_bit, tail_pkg, this_fasm, this_delay)

    def _edge_box_input(self, head_pin_bit, tail_pin_bit, tail_pkg, fasm_features = tuple(), delay = 0.0):
        head_idx, head_node = NetUtils._reference(head_pin_bit)

        try:
            predit = self.conn_graph.predecessors(head_node)
            pred_node = next(predit)
        except (nx.NetworkXError, StopIteration):
            return

        id_ = self.conn_graph.nodes[pred_node].get("id")
        head_pin_bit = NetUtils._dereference(head_pin_bit.parent, pred_node, coalesced = True)[head_idx]
        if id_ is None:
            self._edge_box_output(head_pin_bit, tail_pin_bit, tail_pkg, fasm_features, delay)
            return
        elif isinstance(tail_pin_bit.bus.model.key, SegmentID):     # ??? -> track
            tail_id, tail_lower, tail_higher, tail_ori = tail_pkg
            tail_start = tail_ori.direction.case(tail_lower, tail_higher)
            if isinstance(pred_node[0], SegmentID):                 # track -> track
                head_ori, head_lower, head_higher, _ = self._analyze_track(pred_node)
                if head_ori is tail_ori:                            # straight connection
                    dim, dir_ = tail_ori.decompose()
                    if (head_lower[dim.perpendicular] == tail_start[dim.perpendicular] and
                            head_lower[dim] <= tail_start[dim] + dir_.case(-1, 1) <= head_higher[dim]):
                        self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                        return
                elif head_ori is not tail_ori.opposite:             # not a U-turn
                    from_dim, from_dir = head_ori.decompose()
                    to_dim, to_dir = tail_ori.decompose()
                    if (head_lower[to_dim] + to_dir.case(1, 0) == tail_start[to_dim] and
                            head_lower[from_dim] <= tail_start[from_dim] + from_dir.case(0, 1) <= head_higher[from_dim]):
                        self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                        return
            else:                                                   # block pin -> track
                head_chan, head_ori, _ = self._analyze_blockpin(head_pin_bit.bus)
                dim = head_ori.dimension.perpendicular
                if dim is tail_ori.dimension and head_chan == tail_start:
                    self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                    return
        else:                                                       # ??? -> block pin
            tail_id, tail_chan, dim = tail_pkg
            if isinstance(pred_node[0], SegmentID):                 # track -> block pin
                head_ori, head_lower, head_higher, _ = self._analyze_track(pred_node)
                if (dim is head_ori.dimension and head_lower[dim] <= tail_chan[dim] <= head_higher[dim]
                        and tail_chan[dim.perpendicular] == head_lower[dim.perpendicular]):
                    self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                    return
            else:                                                   # block pin -> block pin
                self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                return
        _logger.info("Physical connection {} -> {} ignored due to reachability".format(head_pin_bit, tail_pin_bit))

    def run(self, context):
        # runtime-generated data
        self.block2id = OrderedDict()
        self.blockpin2ptc = OrderedDict()
        self.switch2id = OrderedDict()
        self.sgmt2id = OrderedDict()
        self.sgmt2ptc = OrderedDict()
        self.chanx = [[(0 < x < context.top.width - 1 and 0 <= y < context.top.height - 1)
            for y in range(context.top.height)] for x in range(context.top.width)]
        self.chany = [[(0 <= x < context.top.width - 1 and 0 < y < context.top.height - 1)
            for y in range(context.top.height)] for x in range(context.top.width)]
        channel_width = context.summary.vpr["channel_width"] = 2 * sum(sgmt.width * sgmt.length
                for sgmt in itervalues(context.segments))
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
                ptc = 0
                for i, (name, sgmt) in enumerate(iteritems(context.segments)):
                    self.sgmt2id[name] = i
                    self.sgmt2ptc[name] = ptc
                    ptc += 2 * sgmt.width * sgmt.length
                    with self.xml.element("segment", {"name": name, "id": i}):
                        sgmt = self.timing.vpr_segment(sgmt)
                        self.xml.element_leaf("timing", {"R_per_meter": sgmt.Rmetal, "C_per_meter": sgmt.Cmetal})
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
            # flatten grid and create coalesced connection graph
            with xml.element("grid"):
                self._grid(context.top)
                self._construct_conn_graph(context.top)
            # nodes
            with xml.element("rr_nodes"):
                for node, data in self.conn_graph.nodes(data = True):
                    if "id" not in data:
                        continue
                    elif isinstance(node[0], SegmentID):  # track
                        ori, lower, higher, ptc_pos = self._analyze_track(node)
                        segment = node[0].prototype
                        ptc = self.sgmt2ptc[segment.name] + ori.direction.case(0, 1)
                        for i in range(segment.width):
                            self._node(ori.dimension.case("CHANX", "CHANY"),
                                    data["id"] + i, 
                                    ptc + 2 * (ptc_pos % segment.length) * segment.width + i * 2,
                                    lower.x,
                                    lower.y,
                                    track_dir = ori.direction,
                                    xhigh = higher.x,
                                    yhigh = higher.y,
                                    segment = self.timing.vpr_segment(segment),
                                    )
                    else:                               # block pin
                        pin = NetUtils._dereference(context.top, node, coalesced = True)
                        _, ori, pos = self._analyze_blockpin(pin)
                        port, block = pin.model, pin.model.parent
                        srcsink_per_block, _, iopin_per_block = self.blockpin2ptc[block.key]["#"]
                        srcsink_ptc, equivalent, iopin_ptc = self.blockpin2ptc[block.key][port.key]
                        # SOURCE/SINK node
                        if equivalent:
                            self._node(port.direction.case("SINK", "SOURCE"), data["srcsink_id"],
                                    node[1][1] * srcsink_per_block + srcsink_ptc,
                                    pos.x, pos.y, capacity = len(port),
                                    xhigh = pos.x + block.width - 1, yhigh = pos.y + block.height - 1)
                        else:
                            for i in range(len(port)):
                                self._node(port.direction.case("SINK", "SOURCE"), data["srcsink_id"] + i,
                                        node[1][1] * srcsink_per_block + srcsink_ptc + i,
                                        pos.x, pos.y, capacity = 1,
                                        xhigh = pos.x + block.width - 1, yhigh = pos.y + block.height - 1)
                        # IPIN/OPIN node
                        for i in range(len(port)):
                            self._node(port.direction.case("IPIN", "OPIN"), data["id"] + i,
                                    node[1][1] * iopin_per_block + iopin_ptc + i,
                                    pos.x + port.position.x, pos.y + port.position.y, port_ori = ori)
            # edges
            with xml.element("rr_edges"):
                for sink_node, sink_data in self.conn_graph.nodes(data = True):
                    type_ = sink_data.get("type", None)
                    if type_ == "TRACK":
                        # 1. get the pin
                        sink_pin = NetUtils._dereference(context.top, sink_node, coalesced = True)
                        # 2. prepare the tail package
                        ori, lower, higher, _ = self._analyze_track(sink_node)
                        # 3. emit edges
                        for i, sink_pin_bit in enumerate(sink_pin):
                            self._edge_box_output(sink_pin_bit, sink_pin_bit,
                                    # tail_id,            lower_pos, higher_pos, orientation
                                    (sink_data["id"] + i, lower,     higher,     ori))
                    elif type_ == "IPIN":
                        # 1. get the pin
                        sink_pin = NetUtils._dereference(context.top, sink_node, coalesced = True)
                        # 2. prepare the tail package
                        chan, ori, _ = self._analyze_blockpin(sink_pin)
                        iopin_id = sink_data["id"]
                        srcsink_id = sink_data["srcsink_id"]
                        equivalent = sink_data.get("equivalent", False)
                        for i, sink_pin_bit in enumerate(sink_pin):
                            # 3.1 IPIN -> SINK
                            self._edge(iopin_id + i, srcsink_id + (0 if equivalent else i), switch_id = 0)
                            # 3.2 ??? -> IPIN
                            self._edge_box_input(sink_pin_bit, sink_pin_bit,
                                    # tail_id,     chan_pos, dimension
                                    (iopin_id + i, chan,     ori.dimension.perpendicular))
                    elif type_ == "OPIN":
                        # 1. get the pin
                        sink_pin = NetUtils._dereference(context.top, sink_node, coalesced = True)
                        # 2. emit SOURCE -> OPIN edges
                        iopin_id = sink_data["id"]
                        srcsink_id = sink_data["srcsink_id"]
                        equivalent = sink_data.get("equivalent", False)
                        for i in range(len(sink_pin)):
                            self._edge(srcsink_id + (0 if equivalent else i), iopin_id + i, switch_id = 0)
            del self.xml
