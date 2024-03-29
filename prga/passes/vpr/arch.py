# -*- encoding: ascii -*-

from .delegate import FASMDelegate
from ..base import AbstractPass
from ...core.builder.array.array import ArrayBuilder
from ...core.common import (Orientation, Position, ModuleView, IO, PrimitiveClass)
from ...netlist import TimingArcType, NetUtils, ModuleUtils, PortDirection
from ...xml import XMLGenerator
from ...exception import PRGAInternalError

from abc import abstractproperty, abstractmethod
from collections.abc import Sequence
from itertools import product
import os, gzip

__all__ = ["VPRArchGeneration", "VPRScalableDelegate"]

FASM_NONE = "$"

# ----------------------------------------------------------------------------
# -- Base Class for VPR arch.xml Generation ----------------------------------
# ----------------------------------------------------------------------------
class _VPRArchGeneration(AbstractPass):
    """Base generator for VPR's architecture description XML."""

    __slots__ = [
            # customizable variables
            'output_file', 'fasm', # 'timing',
            # temporary variables
            'xml', 'lut_sizes', 'active_primitives', 'active_blocks', 'active_tiles',
            ]

    def __init__(self, output_file, *, fasm = None):
        # , timing = None):
        self.output_file = output_file
        self.fasm = fasm
        # self.timing = timing

    @property
    def is_readonly_pass(self):
        return True

    @classmethod
    def _net2vpr(cls, net, parent_name, bitwise = False):
        if net.net_type.is_concat:
            return " ".join(cls._net2vpr(i, parent_name, bitwise) for i in net.items)
        elif net.net_type.is_const:
            raise PRGAInternalError("Cannot express constant nets in VPR")
        elif bitwise and len(net) > 1:
            return " ".join(cls._net2vpr(i, parent_name) for i in net)
        prefix, suffix = None, ""
        if net.net_type.is_bit:
            suffix = '[{}]'.format(net.index)
            net = net.bus
        elif net.net_type.is_slice:
            suffix = '[{}:{}]'.format(net.range_.stop - 1, net.range_.start)
            net = net.bus
        if net.net_type.is_port:
            prefix = '{}.{}'.format(parent_name, net.name)
        elif hasattr(net.instance, "vpr_num_pb"):
            prefix = '{}[{}].{}'.format(*net.instance.key, net.model.name)
        else:
            prefix = '{}.{}'.format(net.instance.name, net.model.name)
        return prefix + suffix

    def _tile(self, context, tile):
        with self.xml.element("tile", {"name": tile.name, "width": tile.width, "height": tile.height}):
            processed_blocks = set()
            for subtile, i in tile.instances.items():
                if not isinstance(subtile, int):
                    continue
                elif (block := i.model).key in processed_blocks:
                    continue

                subtile_name = "{}_s{}".format(tile.name, len(processed_blocks))
                processed_blocks.add( block.key )
                self.active_blocks.setdefault(block.key, set()).add(tile.name)
                capacity = getattr(i, "vpr_capacity", 1)

                with self.xml.element("sub_tile", {"name": subtile_name, "capacity": capacity}):
                    # 1. emit ports:
                    for port in block.ports.values():
                        attrs = {'name': port.name, 'num_pins': len(port)}
                        if not port.is_clock and hasattr(port, 'global_'):
                            attrs['is_non_clock_global'] = "true"
                        if getattr(port, "vpr_equivalent_pins", False):
                            attrs["equivalent"] = "full"
                        self.xml.element_leaf(
                                'clock' if port.is_clock else port.direction.case('input', 'output'),
                                attrs)
                    # 2. FC
                    if (unroutables := set(port.name for tunnel in context.tunnels.values()
                        for port in (tunnel.source, tunnel.sink) if port.parent is block) |
                        set(port.name for port in block.ports.values() if hasattr(port, "global_"))):
                        with self.xml.element("fc",
                                {"in_type": "frac", "in_val": "1.0", "out_type": "frac", "out_val": "1.0"}):
                            for port in unroutables:
                                self.xml.element_leaf("fc_override",
                                        {"fc_type": "frac", "fc_val": 0., "port_name": port})
                    else:
                        self.xml.element_leaf("fc",
                                {"in_type": "frac", "in_val": "1.0", "out_type": "frac", "out_val": "1.0"})
                    # 3. pinlocations
                    with self.xml.element("pinlocations", {"pattern": "custom"}):
                        for ori in Orientation:
                            if any(tile.edge[o] for o in Orientation if o is not ori.opposite):
                                continue
                            for offset in range(ori.dimension.case(tile.height, tile.width)):
                                pos = ori.case( (offset, tile.height - 1), (tile.width - 1, offset),
                                        (offset, 0), (0, offset) )
                                if (ports := tuple(port for port in block.ports.values()
                                    if port.position == pos and port.orientation in (None, ori))):
                                    self.xml.element_leaf("loc", {
                                        "side": ori.case("top", "right", "bottom", "left"),
                                        "xoffset": pos[0], "yoffset": pos[1]},
                                        ' '.join("{}.{}".format(subtile_name, port.name) for port in ports))
                    # 4. equivalent sites
                    with self.xml.element("equivalent_sites"):
                        self.xml.element_leaf("site", {"pb_type": block.name, "pin_mapping": "direct"})

    def _interconnect(self, sink, parent_name, instance = None):
        sources = NetUtils.concat(s for s in NetUtils.get_multisource(sink) if not s.net_type.is_const)
        if len(sources) == 0:
            return
        type_ = "direct" if len(sources) == 1 else "mux"
        # get a unique name for the interconnect
        name = [type_]
        if sink.parent.module_class.is_mode:
            name.append( sink.parent.key )
        sinkbus, index = sink, None
        if sink.net_type.is_bit:
            sinkbus, index = sink.bus, sink.index
        if sinkbus.net_type.is_pin:
            name.append( sinkbus.instance.name )
            name.append( sinkbus.model.name )
        else:
            name.append( sinkbus.name )
        if index is not None:
            name.append( str(index) )
        # generate XML tag
        fasm_muxes = {}
        with self.xml.element(type_, {
            "name": "_".join(name),
            "input": self._net2vpr(sources, parent_name, bitwise = True),
            "output": (sink_vpr := self._net2vpr(sink, parent_name)),
            }):
            for src in sources:
                src_vpr = self._net2vpr(src, parent_name)
                # pack pattern
                if (conn := NetUtils.get_connection(src, sink)) is None:
                    continue
                pack_patterns = getattr(conn, "vpr_pack_patterns", tuple())
                for pack_pattern in pack_patterns:
                    self.xml.element_leaf("pack_pattern", {
                        "name": pack_pattern,
                        "in_port": self._net2vpr(src, parent_name),
                        "out_port": sink_vpr,
                        })
                # FASM mux
                fasm_muxes[src_vpr] = self.fasm.fasm_mux_for_intrablock_switch(src, sink, instance)
                # FIXME: timing
                # max_, min_ = self.timing.vpr_delay_of_intrablock_switch(src, sink, instance)
                # if not (max_ is None and min_ is None):
                #     attrs = {
                #             "in_port": self._net2vpr(src, parent_name),
                #             "out_port": self._net2vpr(sink, parent_name),
                #             }
                #     if max_ is not None:
                #         attrs["max"] = max_
                #     if min_ is not None:
                #         attrs["min"] = min_
                #     self.xml.element_leaf("delay_constant", attrs)
            if any(fasm_muxes.values()):
                with self.xml.element("metadata"):
                    self.xml.element_leaf("meta", {"name": "fasm_mux"},
                            '\n'.join('{} : {}'.format(src, ", ".join(fasm_mux) or FASM_NONE)
                                for src, fasm_mux in fasm_muxes.items()))

    def _hierarchy(self, module, instances = None):
        attrs, hierarchy, fasm_prefixes = {}, None, None

        if isinstance(instances, Sequence):
            attrs = {"name": instances[0].hierarchy[0].key[0], "num_pb": len(instances), }
            hierarchy = instances[0]
            fasm_prefixes = tuple(self.fasm.fasm_prefix_for_intrablock_module(module, i) for i in instances)
            fasm_prefixes = ' '.join(s or FASM_NONE for s in fasm_prefixes) if any(fasm_prefixes) else None
        elif instances is not None:
            attrs = {"name": instances.hierarchy[0].key, "num_pb": 1, }
            hierarchy = instances
            fasm_prefixes = self.fasm.fasm_prefix_for_intrablock_module(module, instances)
        else:
            attrs = {"name": module.name, }
            fasm_prefixes = self.fasm.fasm_prefix_for_intrablock_module(module)

        fasm_features = self.fasm.fasm_features_for_intrablock_module(module, hierarchy)

        return attrs, hierarchy, fasm_prefixes, fasm_features

    def _pb_type_leaf_body(self, primitive, name, hierarchy, fasm_prefixes = None, fasm_features = None):
        # 1. emit ports
        for port in primitive.ports.values():
            port_attrs = {'name': port.name, 'num_pins': len(port)}
            if (port_class := getattr(port, 'port_class', None)) is not None:
                port_attrs['port_class'] = port_class.name
            self.xml.element_leaf(
                    'clock' if port.is_clock else port.direction.case('input', 'output'),
                    port_attrs)

        # 2. timing
        for port in primitive.ports.values():
            for arc in NetUtils.get_timing_arcs(sink = port):
                # FIXME: fake timing here
                if arc.type_.is_comb_bitwise or arc.type_.is_comb_matrix:
                    self.xml.element_leaf("delay_constant", {"max": 1e-10,
                        "in_port": self._net2vpr(arc.source, name),
                        "out_port": self._net2vpr(arc.sink, name)})
                elif arc.type_.is_seq_start:
                    self.xml.element_leaf("T_clock_to_Q", {"max": 1e-10,
                        "port": self._net2vpr(arc.sink, name),
                        "clock": arc.source.name})
                elif arc.type_.is_seq_end:
                    self.xml.element_leaf("T_setup", {"value": 1e-10,
                        "port": self._net2vpr(arc.sink, name),
                        "clock": arc.source.name})

        # 3. FASM parameters
        fasm_params = ({} if primitive.primitive_class.is_lut else
                self.fasm.fasm_params_for_primitive(hierarchy)) 
        if fasm_prefixes or fasm_features or any(fasm_params.values()):
            with self.xml.element("metadata"):
                if fasm_prefixes:
                    self.xml.element_leaf("meta", {"name": "fasm_prefix"}, fasm_prefixes)
                if fasm_features:
                    self.xml.element_leaf("meta", {"name": "fasm_features"}, " ".join(fasm_features))
                if any(fasm_params.values()):
                    self.xml.element_leaf("meta", {"name": "fasm_params"},
                        '\n'.join("{} = {}".format(p or FASM_NONE, param)
                            for param, p in fasm_params.items()))

                # if port.is_clock:
                #     continue
                # outputs_with_comb_path = set()
                # if port.direction.is_input:
                #     # TODO
                #     # combinational sinks
                #     for sink_name in getattr(port, "vpr_combinational_sinks", tuple()):
                #         sink = primitive.ports[sink_name]
                #         outputs_with_comb_path.add(sink)
                #         delay, max_of_max, min_of_min = {}, None, None
                #         for srcbit, sinkbit in product(port, sink):
                #             max_, min_ = self.timing.vpr_delay_of_primitive_path(srcbit, sinkbit, instance)
                #             delay[NetUtils._reference(srcbit), NetUtils._reference(sinkbit)] = max_, min_
                #             if max_ is not None and (max_of_max is None or max_ > max_of_max):
                #                 max_of_max = max_
                #             if min_ is not None and (min_of_min is None or min_ < min_of_min):
                #                 min_of_min = min_
                #         if max_of_max is None:
                #             raise PRGAInternalError("Max delay required for comb. path from '{}' to '{}' in '{}'"
                #                     .format(port, sink, instance))
                #         if bitwise_timing:
                #             for srcbit, sinkbit in product(port, sink):
                #                 max_, min_ = delay[NetUtils._reference(srcbit), NetUtils._reference(sinkbit)]
                #                 min_ = uno(min_, min_of_min)
                #                 attrs = {"max": uno(max_, max_of_max),
                #                         "in_port": self._net2vpr(srcbit, parent_name),
                #                         "out_port": self._net2vpr(sinkbit, parent_name), }
                #                 if min_ is not None:
                #                     attrs["min"] = min_
                #                 self.xml.element_leaf("delay_constant", attrs)
                #         else:
                #             attrs = {"max": max_of_max,
                #                     "in_port": self._net2vpr(port, parent_name),
                #                     "out_port": self._net2vpr(sink, parent_name), }
                #             if min_of_min is not None:
                #                 attrs["min"] = min_of_min
                #             self.xml.element_leaf("delay_constant", attrs)
                # # clocked?
                # if hasattr(port, "clock"):
                #     clock = primitive.ports[port.clock]
                #     # setup & hold
                #     if port.direction.is_input or port in outputs_with_comb_path:
                #         setup, max_setup = [], None
                #         for i, bit in enumerate(port):
                #             this_setup = self.timing.vpr_setup_time_of_primitive_port(bit, instance)
                #             setup.append(this_setup)
                #             if this_setup is not None and (max_setup is None or this_setup > max_setup):
                #                 max_setup = this_setup
                #         if max_setup is None:
                #             raise PRGAInternalError("Setup time required for seq. endpoint '{}' in '{}'"
                #                     .format(port, instance))
                #         if bitwise_timing:
                #             for i, bit in enumerate(port):
                #                 self.xml.element_leaf("T_setup", {
                #                     "port": self._net2vpr(bit, parent_name),
                #                     "value": uno(setup[i], max_setup),
                #                     "clock": clock.name, })
                #         else:
                #             self.xml.element_leaf("T_setup", {
                #                 "port": self._net2vpr(port, parent_name),
                #                 "value": max_setup,
                #                 "clock": clock.name, })
                #     # clk2q
                #     if port.direction.is_output or getattr(port, "vpr_combinational_sinks", False):
                #         clk2q, max_of_max, min_of_min = [], None, None
                #         for i, bit in enumerate(port):
                #             max_, min_ = self.timing.vpr_clk2q_time_of_primitive_port(port, instance)
                #             clk2q.append( (max_, min_) )
                #             if max_ is not None and (max_of_max is None or max_ > max_of_max):
                #                 max_of_max = max_
                #             if min_ is not None and (min_of_min is None or min_ < min_of_min):
                #                 min_of_min = min_
                #         if max_of_max is None:
                #             raise PRGAInternalError("Max clk-to-Q time required for seq. startpoint '{}' in '{}'"
                #                     .format(port, instance))
                #         if bitwise_timing:
                #             for i, bit in enumerate(port):
                #                 max_, min_ = clk2q[i]
                #                 min_ = uno(min_, min_of_min)
                #                 attrs = {"max": uno(max_, max_of_max),
                #                         "port": self._net2vpr(bit, parent_name),
                #                         "clock": clock.name, }
                #                 if min_ is not None:
                #                     attrs["min"] = min_
                #                 self.xml.element_leaf("T_clock_to_Q", attrs)
                #         else:
                #             attrs = {"max": max_of_max,
                #                     "port": self._net2vpr(port, parent_name),
                #                     "clock": clock.name, }
                #             if min_of_min is not None:
                #                 attrs["min"] = min_of_min
                #             self.xml.element_leaf("T_clock_to_Q", attrs)

    def _pb_type_lut(self, primitive, instances):
        lut_size = len(primitive.ports['in'])
        self.lut_sizes.add( lut_size )

        attrs, hierarchy, fasm_prefixes, fasm_features = self._hierarchy(primitive, instances)
        name = attrs["name"]

        with self.xml.element("pb_type", attrs):
            # 1. emit ports
            for port in primitive.ports.values():
                self.xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        {'name': port.name, "num_pins": len(port), })

            # 2. internal LUT pb_type
            internal_name = attrs["name"] + "_lut"
            with self.xml.element("pb_type", {
                "name": internal_name,
                "num_pb": 1,
                "blif_model": ".names",
                "class": "lut",
                }):

                self._pb_type_leaf_body(primitive, internal_name, hierarchy)

            # 3. interconnect
            with self.xml.element("interconnect"):
                for port in primitive.ports.values():
                    self.xml.element_leaf("direct", {
                        "name": "direct_" + port.name,
                        "input": "{}.{}".format(port.direction.case(name, internal_name), port.name),
                        "output": "{}.{}".format(port.direction.case(internal_name, name), port.name),
                        })

            # 4. FASM metadata
            with self.xml.element("metadata"):
                if fasm_prefixes:
                    self.xml.element_leaf('meta', {'name': 'fasm_prefix'}, fasm_prefixes)
                if fasm_features:
                    self.xml.element_leaf('meta', {'name': 'fasm_features'}, " ".join(fasm_features))
                self.xml.element_leaf("meta", {"name": "fasm_type"}, "LUT")
                self.xml.element_leaf("meta", {"name": "fasm_lut"},
                        "LUT[{}:0] = {}[0]".format(2 ** lut_size - 1, internal_name))

    def _pb_type_leaf(self, primitive, instances):
        attrs, hierarchy, fasm_prefixes, fasm_features = self._hierarchy(primitive, instances)

        # bitwise_timing = True
        if primitive.primitive_class.is_flipflop:
            attrs.update({"blif_model": ".latch", "class": "flipflop"})
        elif primitive.primitive_class.is_inpad:
            attrs.update({"blif_model": ".input"})
        elif primitive.primitive_class.is_outpad:
            attrs.update({"blif_model": ".output"})
        elif primitive.primitive_class.is_memory:
            self.active_primitives.add( primitive.key )
            # bitwise_timing = False
            attrs.update({"class": "memory",
                "blif_model": ".subckt " + primitive.vpr_model, })
        elif primitive.primitive_class in (PrimitiveClass.custom, PrimitiveClass.blackbox_memory):
            self.active_primitives.add( primitive.key )
            # bitwise_timing = getattr(primitive, "vpr_bitwise_timing", True)
            attrs.update({
                "blif_model": ".subckt " + primitive.vpr_model, })
        else:
            raise PRGAInternalError("Unknown primitive class: {}".format(primitive.primitive_class.name))

        with self.xml.element('pb_type', attrs):
            self._pb_type_leaf_body(primitive, attrs["name"], hierarchy, fasm_prefixes, fasm_features)

    def _pb_type_multimode(self, module, instances):
        attrs, hierarchy, fasm_prefixes, fasm_features = self._hierarchy(module, instances)

        # TODO: A more generic way to "emulate" other primitives
        for lut_size in getattr(module, "emulate_luts", []):
            self.lut_sizes.add( lut_size )

        with self.xml.element("pb_type", attrs):
            # 1. emit ports:
            for port in module.ports.values():
                self.xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        {'name': port.name, 'num_pins': len(port), })
            
            # 2. enumerate modes
            name = attrs["name"]
            for mode in module.modes.values():
                mode_name = "{}_{}".format(name, mode.key)

                with self.xml.element("mode", {"name": mode.key}):
                    # 2.1 mode-internal pb_type
                    with self.xml.element("pb_type", {"name": mode_name, "num_pb": 1}):
                        # 2.1.1 emit ports
                        for port in mode.ports.values():
                            self.xml.element_leaf(
                                    'clock' if port.is_clock else port.direction.case('input', 'output'),
                                    {'name': port.name, 'num_pins': len(port), })

                        # 2.1.2 body
                        self._pb_type_body(mode, mode_name, hierarchy, "@" + mode.key,
                                self.fasm.fasm_features_for_intrablock_module(mode, hierarchy))
                    
                    # 2.2 interconnects
                    with self.xml.element("interconnect"):
                        for port in mode.ports.values():
                            self.xml.element_leaf("direct", {
                                "name": "direct_" + port.name,
                                "input": "{}.{}".format(port.direction.case(name, mode_name), port.name),
                                "output": "{}.{}".format(port.direction.case(mode_name, name), port.name),
                                })

            # 3. FASM
            if fasm_prefixes or fasm_features:  # or any(fasm_luts.values()):
                with self.xml.element("metadata"):
                    if fasm_prefixes:
                        self.xml.element_leaf('meta', {'name': 'fasm_prefix'}, fasm_prefixes)
                    if fasm_features:
                        self.xml.element_leaf('meta', {'name': 'fasm_features'}, " ".join(fasm_features))

    def _pb_type_body(self, module, name, hierarchy, fasm_prefixes = None, fasm_features = None):
        # sub instances
        for instance in module.instances.values():
            sub_name, subs = instance.key, instance

            if (num_pb := getattr(instance, "vpr_num_pb", None)) is not None:
                if instance.key[1] != 0:
                    continue

                sub_name = instance.key[0]
                subs = tuple(module.instances[sub_name, i]._extend_hierarchy(above = hierarchy)
                        for i in range(num_pb))

            if instance.model.module_class.is_slice:
                self._pb_type(instance.model, subs)

            elif instance.model.module_class.is_primitive:
                if instance.model.primitive_class.is_multimode:
                    self._pb_type_multimode(instance.model, subs)

                elif instance.model.primitive_class.is_lut:
                    self._pb_type_lut(instance.model, subs)

                else:
                    self._pb_type_leaf(instance.model, subs)

        # interconnects
        with self.xml.element('interconnect'):
            for net in ModuleUtils._iter_nets(module):
                if not net.is_sink:
                    continue
                for sink in net:
                    self._interconnect(sink, name, hierarchy)

        # FASM
        if fasm_prefixes or fasm_features:  # or any(fasm_luts.values()):
            with self.xml.element("metadata"):
                if fasm_prefixes:
                    self.xml.element_leaf('meta', {'name': 'fasm_prefix'}, fasm_prefixes)
                if fasm_features:
                    self.xml.element_leaf('meta', {'name': 'fasm_features'}, " ".join(fasm_features))

    def _pb_type(self, module, instances = None):
        attrs, hierarchy, fasm_prefixes, fasm_features = self._hierarchy(module, instances)

        with self.xml.element("pb_type", attrs):
            # 1. emit ports:
            for port in module.ports.values():
                port_attrs = {'name': port.name, 'num_pins': len(port)}
                if not port.is_clock and hasattr(port, 'global_'):
                    port_attrs['is_non_clock_global'] = "true"
                if getattr(port, "vpr_equivalent_pins", False):
                    port_attrs["equivalent"] = "full"
                self.xml.element_leaf(
                        'clock' if port.is_clock else port.direction.case('input', 'output'),
                        port_attrs)

            # 2. emit pb_type body
            self._pb_type_body(module, attrs["name"], hierarchy, fasm_prefixes, fasm_features)

    def _model(self, primitive):
        with self.xml.element("model", {"name": primitive.vpr_model}):
            with self.xml.element("output_ports"):
                for port in primitive.ports.values():
                    if port.direction.is_input:
                        continue
                    attrs = {"name": port.name}
                    if port.is_clock:
                        attrs["is_clock"] = "1"
                    else:
                        for arc in NetUtils.get_timing_arcs(sink = port,
                                types = (TimingArcType.seq_start, TimingArcType.seq_end)):
                            if "clock" in attrs:
                                raise PRGAInternalError("{} is clocked by multiple clocks".format(port))
                            attrs["clock"] = arc.source.name
                    self.xml.element_leaf("port", attrs)
            with self.xml.element("input_ports"):
                for port in primitive.ports.values():
                    if port.direction.is_output:
                        continue
                    attrs = {"name": port.name}
                    if port.is_clock:
                        attrs["is_clock"] = "1"
                    else:
                        for arc in NetUtils.get_timing_arcs(sink = port,
                                types = (TimingArcType.seq_start, TimingArcType.seq_end)):
                            if "clock" in attrs:
                                raise PRGAInternalError("{} is clocked by multiple clocks".format(port))
                            attrs["clock"] = arc.source.name
                        sinks = []
                        for arc in NetUtils.get_timing_arcs(source = port,
                                types = (TimingArcType.comb_bitwise, TimingArcType.comb_matrix)):
                            sinks.append(arc.sink.name)
                        if sinks:
                            attrs["combinational_sink_ports"] = " ".join(sinks)
                    self.xml.element_leaf("port", attrs)

    def _direct(self, tunnel):
        vpr_offset = tunnel.source.position - tunnel.sink.position - tunnel.offset
        for from_tile, to_tile in product(self.active_blocks.get(tunnel.source.parent.key, tuple()),
                self.active_blocks.get(tunnel.sink.parent.key, tuple())):
            self.xml.element_leaf("direct", {
                "name": tunnel.name,
                "from_pin": "{}.{}".format(from_tile, tunnel.source.name),
                "to_pin": "{}.{}".format(to_tile, tunnel.sink.name),
                "x_offset": vpr_offset.x,
                "y_offset": vpr_offset.y,
                "z_offset": 0,
                })

    def run(self, context):
        # create and add VPR summary if not present
        if not hasattr(context.summary, 'vpr'):
            context.summary.vpr = {}
        # output file update to the VPR summary is done per subclass
        if isinstance(self.output_file, str):
            f = self.output_file
            os.makedirs(os.path.dirname(f), exist_ok = True)
            self._update_output_file(context.summary.vpr, f)
            if f.endswith(".gz"):
                self.output_file = gzip.open(f, "wb")
            else:
                self.output_file = open(f, "wb")
        else:
            f = self.output_file.name
            os.makedirs(os.path.dirname(f), exist_ok = True)
            self._update_output_file(context.summary.vpr, f)
            if f.endswith(".gz"):
                self.output_file = gzip.open(self.output_file, "wb")
        # FASM 
        if self.fasm is None:
             self.fasm = context.fasm_delegate
        self.fasm.reset()
        # timing
        # if self.timing is None:
        #     self.timing = TimingDelegate()  # fake timing
        # self.timing.reset()
        # link and reset context summary
        if self._update_summary:
            self.active_tiles = context.summary.active_tiles = {}
            self.active_blocks = context.summary.active_blocks = {}
            self.active_primitives = context.summary.active_primitives = set()
            self.lut_sizes = context.summary.lut_sizes = set()
        else:
            self.active_tiles = {}
            self.active_blocks = {}
            self.active_primitives = set()
            self.lut_sizes = set()
        # XML generation
        with XMLGenerator(self.output_file, True) as xml, xml.element("architecture"):
            self.xml = xml
            # layout: done per subclass
            with xml.element("layout"):
                self._layout(context)
            # physical tiles
            with xml.element("tiles"):
                for tile_key in self.active_tiles:
                    self._tile(context, context.database[ModuleView.abstract, tile_key])
            # complex blocks
            with xml.element("complexblocklist"):
                for block_key in self.active_blocks:
                    self._pb_type(context.database[ModuleView.abstract, block_key])
            # directs:
            if (active_tunnels := tuple(tunnel for tunnel in context.tunnels.values()
                if tunnel.source.parent.key in self.active_blocks and tunnel.sink.parent.key in self.active_blocks)):
                with xml.element("directlist"):
                    for tunnel in active_tunnels:
                        self._direct(tunnel)
            # models
            with xml.element("models"):
                generated = set()
                for model_key in self.active_primitives:
                    model = context.database[ModuleView.abstract, model_key]
                    if model.vpr_model not in generated:
                        generated.add(model.vpr_model)
                        self._model(model)
            # device: done per subclass
            with xml.element("device"):
                self._device(context)
            # switches: based on timing delegate
            with xml.element("switchlist"):
                # FIXME: fake switch
                xml.element_leaf("switch", {
                    "type": "mux",
                    "name": "default",
                    "R": 0.,
                    "Cin": 0.,
                    "Cout": 0.,
                    "Tdel": 1e-10,
                    "mux_trans_size": 0.,
                    "buf_size": 0.,
                    })
                # for switch in self.timing.vpr_switches:
                #     xml.element_leaf("switch", {
                #         "type": "mux",      # type forced to mux
                #         "name": switch.name,
                #         "R": switch.R,
                #         "Cin": switch.Cin,
                #         "Cout": switch.Cout,
                #         "Tdel": switch.Tdel,
                #         "mux_trans_size": switch.mux_trans_size,
                #         "buf_size": switch.buf_size,
                #         })
            # segments:
            with xml.element("segmentlist"):
                for segment in context.segments.values():
                    # FIXME: fake segment timing
                    with xml.element('segment', {
                        'name': segment.name,
                        'freq': 1.,
                        'length': segment.length,
                        'type': 'unidir',
                        'Rmetal': 0.,
                        'Cmetal': 0.,
                        }):
                        xml.element_leaf('mux', {'name': 'default'})
                        xml.element_leaf('sb', {'type': 'pattern'},
                                ' '.join(map(str, [1 for _ in range(segment.length + 1)])))
                        xml.element_leaf('cb', {'type': 'pattern'},
                                ' '.join(map(str, [1 for _ in range(segment.length)])))
                    # segment = self.timing.vpr_segment(segment)
                    # with xml.element('segment', {
                    #     'name': segment.name,
                    #     'freq': segment.freq,
                    #     'length': segment.length,
                    #     'type': 'unidir',   # type forced to unidir
                    #     'Rmetal': segment.Rmetal,
                    #     'Cmetal': segment.Cmetal,
                    #     }):
                    #     xml.element_leaf('mux', {'name': segment.mux})
                    #     xml.element_leaf('sb', {'type': 'pattern'},
                    #             ' '.join(map(str, segment.sb_pattern)))
                    #     xml.element_leaf('cb', {'type': 'pattern'},
                    #             ' '.join(map(str, segment.cb_pattern)))
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
        # This method must also update ``active_tiles``
        raise NotImplementedError

    @abstractmethod
    def _device(self, context):
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- VPR arch.xml Generation -------------------------------------------------
# ----------------------------------------------------------------------------
class VPRArchGeneration(_VPRArchGeneration):
    """Generate VPR's architecture description XML.
    
    Args:
        output_file (:obj:`str` of file-like object): The output file. If the file name ends with ".gz", the output
            file will be compressed using gzip

    Keyword Args:
        fasm (`FASMDelegate`): Overwrite the deafult fasm delegate provided by the context
    """
    # timing (`TimingDelegate`): Overwrite the default iming delegate provided by the context

    __slots__ = ['ios']

    @property
    def key(self):
        return "vpr.arch"

    @property
    def _update_summary(self):
        return True

    def _update_output_file(self, summary, output_file):
        summary["arch"] = output_file

    def _layout_array(self, array, globals_, hierarchy = None):
        position = Position(0, 0) if hierarchy is None else ArrayBuilder.hierarchical_position(hierarchy)
        for x, y in product(range(array.width), range(array.height)):
            if (subarray := array.instances.get( (x, y) )) is None:
                continue
            elif subarray.model.module_class.is_array:
                self._layout_array(subarray.model, globals_, subarray._extend_hierarchy(above = hierarchy))
            elif subarray.model.module_class.is_tile:
                self.active_tiles[subarray.model.key] = True
                for subtile, i in subarray.model.instances.items():
                    if not isinstance(subtile, int):
                        continue
                    if i.model.module_class.is_io_block:
                        io = i.model.instances["io"].model
                        self.ios.append( IO(
                            io.primitive_class.case(multimode = (PortDirection.input_, PortDirection.output),
                                inpad = (PortDirection.input_, ), outpad = (PortDirection.output, )),
                            position + (x, y),
                            subtile,
                            globals_.pop( (position + (x, y), subtile), None ),
                            ))
                attrs = { "priority": 1, "type": subarray.model.name, "x": position.x + x, "y": position.y + y, }
                if any(fasm_prefix := self.fasm.fasm_prefix_for_tile(subarray._extend_hierarchy(above = hierarchy))):
                    with self.xml.element('single', attrs), self.xml.element("metadata"):
                        self.xml.element_leaf("meta", {"name": "fasm_prefix"},
                                " ".join(prefix or FASM_NONE for prefix in fasm_prefix))
                else:
                    self.xml.element_leaf("single", attrs)

                attrs = {'priority': 1, 'x': position.x + x, 'y': position.y + y}
            else:
                raise PRGAInternalError("Unsupported module class: {:r}".format(subarray.model.module_class))

    def _layout(self, context):
        self.ios = context.summary.ios = []
        globals_ = { (glb.bound_to_position, glb.bound_to_subtile): glb
                for glb in context.globals_.values()
                if glb.bound_to_position is not None and glb.bound_to_subtile is not None }
        with self.xml.element("fixed_layout",
                {"name": context.top.name, "width": context.top.width, "height": context.top.height}):
            self._layout_array(context.top, globals_)

    def _device(self, context):
        # fake device
        self.xml.element_leaf('sizing', {'R_minW_nmos': '0.0', 'R_minW_pmos': '0.0'})
        # FIXME
        self.xml.element_leaf('connection_block', {'input_switch_name': "default"})
        # self.xml.element_leaf('connection_block', {'input_switch_name': self.timing.vpr_switches[0].name})
        self.xml.element_leaf('area', {'grid_logic_tile_area': '0.0'})
        self.xml.element_leaf('switch_block', {'type': 'wilton', 'fs': '3'})
        self.xml.element_leaf('default_fc',
                {'in_type': 'frac', 'in_val': '1.0', 'out_type': 'frac', 'out_val': '1.0'})
        with self.xml.element('chan_width_distr'):
            self.xml.element_leaf('x', {'distr': 'uniform', 'peak': '1.0'})
            self.xml.element_leaf('y', {'distr': 'uniform', 'peak': '1.0'})

# ----------------------------------------------------------------------------
# -- VPR Scalable arch.xml Generation ----------------------------------------
# ----------------------------------------------------------------------------
class VPRScalableArchGeneration(_VPRArchGeneration):
    """Generate a scalable version of VPR's architecture description XML.
    
    Args:
        output_file (:obj:`str` of file-like object): The output file. If the file name ends with ".gz", the output
            file will be compressed using gzip
        delegate (`VPRScalableDelegate`):

    Keyword Args:
        fasm (`FASMDelegate`): Overwrite the deafult fasm delegate provided by the context

    **WARNING**: The routing graph generated by VPR during FPGA sizing and routing channel fitting is almost
    always different than the one generated by PRGA. Use the scalable architecture description only for
    exploring, and then use fixed layout and channel width for your real chip.
    """

    # timing (`TimingDelegate`): Overwrite the default iming delegate provided by the context

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
        self.active_tiles = self.delegate.active_tiles
        # generate layout
        with self.xml.element("auto_layout", {"aspect_ratio": self.delegate.aspect_ratio}):
            for rule, attrs in self.delegate.layout_rules:
                self.xml.element_leaf(rule, attrs)

    def _device(self, context):
        # fake device
        self.xml.element_leaf('sizing', self.delegate.device.get("sizing",
            {'R_minW_nmos': 0., 'R_minW_pmos': 0.}))
        # FIXME
        self.xml.element_leaf('connection_block', self.delegate.device.get("connection_block",
            {'input_switch_name': "default"}))
        # self.xml.element_leaf('connection_block', self.delegate.device.get("connection_block",
        #     {'input_switch_name': self.timing.vpr_switches[0].name}))
        self.xml.element_leaf('area', self.delegate.device.get("area",
            {'grid_logic_tile_area': 0.}))
        self.xml.element_leaf('switch_block', self.delegate.device.get("switch_block",
            {'type': 'wilton', 'fs': '3'}))
        self.xml.element_leaf('default_fc', self.delegate.device.get("default_fc",
                {'in_type': 'frac', 'in_val': '1.0', 'out_type': 'frac', 'out_val': '1.0'}))
        with self.xml.element('chan_width_distr'):
            self.xml.element_leaf('x', {'distr': 'uniform', 'peak': '1.0'})
            self.xml.element_leaf('y', {'distr': 'uniform', 'peak': '1.0'})
