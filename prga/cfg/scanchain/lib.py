# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...core.common import NetClass, ModuleClass, ModuleView, Subtile
from ...core.context import Context
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...passes.translation import AbstractSwitchDatabase
from ...passes.vpr import FASMDelegate
from ...renderer.renderer import FileRenderer
from ...util import Object, uno

import os
from collections import OrderedDict

__all__ = ['Scanchain']

ADDITIONAL_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- Switch Database ---------------------------------------------------------
# ----------------------------------------------------------------------------
class ScanchainSwitchDatabase(Object, AbstractSwitchDatabase):
    """Switch database for scanchain configuration circuitry."""

    __slots__ = ["context", "cfg_width"]
    def __init__(self, context, cfg_width):
        self.context = context
        self.cfg_width = cfg_width

    def get_switch(self, width, module = None):
        key = (ModuleClass.switch, width)
        try:
            return self.context.database[ModuleView.logical, key]
        except KeyError:
            pass
        try:
            cfg_bitcount = (width - 1).bit_length()
        except AttributeError:
            cfg_bitcount = len(bin(width - 1).lstrip('-0b'))
        switch = Module('sw' + str(width), key = key, ports = OrderedDict(), allow_multisource = True,
                module_class = ModuleClass.switch, cfg_bitcount = cfg_bitcount,
                verilog_template = "switch.tmpl.v")
        # switch inputs/outputs
        i = ModuleUtils.create_port(switch, 'i', width, PortDirection.input_, net_class = NetClass.switch)
        o = ModuleUtils.create_port(switch, 'o', 1, PortDirection.output, net_class = NetClass.switch)
        NetUtils.connect(i, o, fully = True)
        # configuration circuits
        cfg_clk = ModuleUtils.create_port(switch, 'cfg_clk', 1, PortDirection.input_,
                is_clock = True, net_class = NetClass.cfg)
        cfg_e = ModuleUtils.create_port(switch, 'cfg_e', 1, PortDirection.input_, net_class = NetClass.cfg)
        cfg_i = ModuleUtils.create_port(switch, 'cfg_i', self.cfg_width, PortDirection.input_,
                net_class = NetClass.cfg)
        cfg_o = ModuleUtils.create_port(switch, 'cfg_o', self.cfg_width, PortDirection.output,
                net_class = NetClass.cfg)
        return self.context.database.setdefault((ModuleView.logical, key), switch)

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class ScanchainFASMDelegate(FASMDelegate):
    """FASM delegate for scanchain configuration circuitry.
    
    Args:
        context (`Context`):
    """

    __slots__ = ['context', '_elaborated', '_cache']
    def __init__(self, context):
        self.context = context
        self.reset()

    def __getstate__(self):
        return self.context

    def __setstate__(self, state):
        self.context = state
        self.reset()

    def _get_logical_module(self, user_module):
        if user_module.module_class.is_mode:
            return self.context.database[ModuleView.logical, user_module.parent.key].modes[user_module.key]
        else:
            return self.context.database[ModuleView.logical, user_module.key]

    def _hierarchical_bitoffset(self, hierarchical_instance):
        if not hierarchical_instance:
            return 0
        key = tuple(i.key for i in hierarchical_instance)
        try:
            return self._cache["hierarchy"][key]
        except KeyError:
            pass
        cfg_bitoffset = 0
        parent = self._get_logical_module(hierarchical_instance.parent)
        for inst in reversed(hierarchical_instance):
            try:    # when a multi-mode primitive is included in the hierarchy, discontinuity may exist
                inst = parent.instances[inst.key]
            except KeyError:
                if not inst.parent.module_class.is_mode:
                    raise PRGAInternalError("Broken hierarchy: {}".format(hierarchical_instance))
                parent = self._get_logical_module(inst.parent)
                inst = parent.instances[inst.key]
            inst_bitoffset = getattr(inst, 'cfg_bitoffset', None)
            if inst_bitoffset is None:
                return None
            cfg_bitoffset += inst_bitoffset
            parent = inst.model
        self._cache.setdefault("hierarchy", {}).setdefault(key, cfg_bitoffset)
        return cfg_bitoffset

    def _u2l(self, logical_model, user_ref):
        d = getattr(logical_model, "_logical_cp", None)
        if d:
            return d.get(user_ref, user_ref)
        else:
            return user_ref

    def _features_for_path(self, source, sink, instance = None):
        # find hierarchical bitoffset base
        cfg_bitoffset = self._hierarchical_bitoffset(instance)
        # check cache
        src_node, sink_node = map(NetUtils._reference, (source, sink))
        try:
            return tuple('b{}'.format(cfg_bitoffset + i)
                    for i in self._cache["path"][source.parent.key][src_node, sink_node])
        except KeyError:
            pass
        # cache miss. do the job in the right way
        # let's work in the logical domain
        if not (instance is None or instance.model is source.parent or
                (source.parent.module_class.is_mode and source.parent.parent is instance.model)):
            raise PRGAInternalError("Broken hierarchy: {} in {}".format(source, instance))
        user_model = source.parent
        if sink.parent is not user_model:
            raise PRGAInternalError("{} and {} are not in the same parent module".format(source, sink))
        logical_model = self._get_logical_module(user_model)
        if user_model.key not in self._elaborated:
            ModuleUtils.elaborate(logical_model, True)
            self._elaborated.add(logical_model.key)
        assert not logical_model._coalesce_connections
        logical_src, logical_sink = map(lambda x: self._u2l(logical_model, x), (src_node, sink_node))
        # find programmable switch paths
        features = []
        def stop(m, n):
            net = NetUtils._dereference(m, n)
            if not net.net_type.is_pin:
                return True
            bus = net.bus if net.bus_type.is_slice else net
            return not bus.model.net_class.is_switch
        def skip(m, n):
            net = NetUtils._dereference(m, n)
            if not net.net_type.is_pin:
                return True
            bus = net.bus if net.bus_type.is_slice else net
            return not bus.model.net_class.is_switch or bus.model.direction.is_output
        for i, path in enumerate(NetUtils._navigate_backwards(logical_model, logical_sink,
            yield_ = lambda m, n: n == logical_src, stop = stop, skip = skip)):
            if i > 0:
                raise PRGAInternalError("Multiple paths found from {} to {}".format(source, sink))
            for node in path:
                net = NetUtils._dereference(logical_model, node)
                # if net.model.direction.is_output:
                #     continue
                bus, index = (net.bus, net.index) if net.bus_type.is_slice else (net, 0)
                assert not bus.hierarchy.is_hierarchical
                for i in range(bus.hierarchy.model.cfg_bitcount):
                    if (index & (1 << i)):
                        features.append( bus.hierarchy.cfg_bitoffset + i )
        self._cache.setdefault("path", {}).setdefault(user_model.key, {}).setdefault(
                (src_node, sink_node), features )
        return tuple("b{}".format(cfg_bitoffset + i) for i in features)

    def reset(self):
        self._elaborated = set()
        self._cache = {}

    def fasm_mux_for_intrablock_switch(self, source, sink, instance = None):
        return self._features_for_path(source, sink, instance)

    def fasm_features_for_mode(self, instance, mode):
        if instance.model.primitive_class.is_iopad:
            if mode == "inpad":
                return tuple()
            cfg_bitoffset = self._hierarchical_bitoffset(instance[1:])
            if cfg_bitoffset is None:
                return tuple()
            parent = self._get_logical_module(instance[0].parent)
            return ("b{}".format(cfg_bitoffset + parent.instances["_cfg_oe"].cfg_bitoffset), )
        else:
            cfg_bitoffset = self._hierarchical_bitoffset(instance)
            if cfg_bitoffset is None:
                return tuple()
            multimode = self._get_logical_module(instance.model)
            return tuple("b{}".format(cfg_bitoffset + i) for i in multimode.modes[mode].cfg_mode_selection)

    def fasm_prefix_for_tile(self, instance):
        cfg_bitoffset = self._hierarchical_bitoffset(instance[1:])
        if cfg_bitoffset is None:
            return tuple()
        retval = []
        leaf_array = self.context.database[ModuleView.logical, instance[0].parent.key]
        for subblock in range(instance[0].model.capacity):
            blk_inst = leaf_array.instances[instance[0].key[0], subblock]
            inst_bitoffset = getattr(blk_inst, 'cfg_bitoffset', None)
            if inst_bitoffset is None:
                return tuple()
            retval.append( 'b{}'.format(cfg_bitoffset + inst_bitoffset) )
        return retval

    def fasm_lut(self, instance):
        cfg_bitoffset = self._hierarchical_bitoffset(instance)
        if cfg_bitoffset is None:
            return ''
        lut = self._get_logical_module(instance.model)
        return 'b{}[{}:0]'.format(str(cfg_bitoffset), lut.cfg_bitcount - 1)

    def fasm_params_for_primitive(self, instance):
        cfg_bitoffset = self._hierarchical_bitoffset(instance)
        if cfg_bitoffset is None:
            return ''
        primitive = self._get_logical_module(instance.model)
        params = getattr(primitive, "parameters", {})
        fasm_params = {}
        for key, value in iteritems(params):
            if isinstance(value, int):
                fasm_params[key] = "b{}[0:0]".format(cfg_bitoffset + value)
            else:
                fasm_params[key] = "b{}[{}:{}]".format(cfg_bitoffset, value.stop - 1, uno(value.start, 0))
        return fasm_params

    def fasm_features_for_routing_switch(self, source, sink, instance = None):
        return self._features_for_path(source, sink, instance)

# ----------------------------------------------------------------------------
# -- Scanchain Configuration Circuitry Main Entry ----------------------------
# ----------------------------------------------------------------------------
class Scanchain(object):
    """Scanchain configuration circuitry entry point."""

    @classmethod
    def _get_or_create_cfg_ports(cls, module, cfg_width, enable_only = False):
        try:
            if enable_only:
                return module.ports['cfg_e']
            else:
                return tuple(map(lambda x: module.ports[x], ("cfg_clk", "cfg_i", "cfg_o")))
        except KeyError:
            if enable_only:
                return ModuleUtils.create_port(module, 'cfg_e', 1, PortDirection.input_,
                        net_class = NetClass.cfg)
            else:
                cfg_clk = ModuleUtils.create_port(module, 'cfg_clk', 1, PortDirection.input_,
                        is_clock = True, net_class = NetClass.cfg)
                cfg_i = ModuleUtils.create_port(module, 'cfg_i', cfg_width, PortDirection.input_,
                        net_class = NetClass.cfg)
                cfg_o = ModuleUtils.create_port(module, 'cfg_o', cfg_width, PortDirection.output,
                        net_class = NetClass.cfg)
                return cfg_clk, cfg_i, cfg_o

    @classmethod
    def new_context(cls, cfg_width = 1):
        context = Context(cfg_width = cfg_width)
        context._switch_database = ScanchainSwitchDatabase(context, cfg_width)
        context._fasm_delegate = ScanchainFASMDelegate(context)

        # register luts
        for i in range(2, 9):
            lut = Module('lut' + str(i),
                    ports = OrderedDict(),
                    allow_multisource = True,
                    module_class = ModuleClass.primitive,
                    cfg_bitcount = 2 ** i,
                    verilog_template = "lut.tmpl.v")
            # user ports
            in_ = ModuleUtils.create_port(lut, 'in', i, PortDirection.input_, net_class = NetClass.primitive)
            out = ModuleUtils.create_port(lut, 'out', 1, PortDirection.output, net_class = NetClass.primitive)
            NetUtils.connect(in_, out, fully = True)

            # configuration ports
            ModuleUtils.create_port(lut, 'cfg_clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.cfg)
            ModuleUtils.create_port(lut, 'cfg_e', 1, PortDirection.input_,
                    clock = "cfg_clk", net_class = NetClass.cfg)
            ModuleUtils.create_port(lut, 'cfg_i', cfg_width, PortDirection.input_,
                    clock = "cfg_clk", net_class = NetClass.cfg)
            ModuleUtils.create_port(lut, 'cfg_o', cfg_width, PortDirection.output,
                    clock = "cfg_clk", net_class = NetClass.cfg)

            # elaborate
            ModuleUtils.elaborate(lut)
            context._database[ModuleView.logical, lut.key] = lut

        # register flipflops
        if True:
            flipflop = Module('flipflop',
                    ports = OrderedDict(),
                    allow_multisource = True,
                    module_class = ModuleClass.primitive,
                    verilog_template = "flipflop.tmpl.v")
            ModuleUtils.create_port(flipflop, 'clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.primitive)
            ModuleUtils.create_port(flipflop, 'D', 1, PortDirection.input_,
                    clock = 'clk', net_class = NetClass.primitive)
            ModuleUtils.create_port(flipflop, 'Q', 1, PortDirection.output,
                    clock = 'clk', net_class = NetClass.primitive)
            ModuleUtils.create_port(flipflop, 'cfg_e', 1, PortDirection.input_, net_class = NetClass.cfg)
            ModuleUtils.elaborate(flipflop)
            context._database[ModuleView.logical, flipflop.key] = flipflop

        # register single-bit configuration filler
        if True:
            cfg_bit = Module('cfg_bit',
                    ports = OrderedDict(),
                    allow_multisource = True,
                    module_class = ModuleClass.cfg,
                    cfg_bitcount = 1,
                    verilog_template = "cfg_bit.tmpl.v")
            ModuleUtils.create_port(cfg_bit, 'cfg_clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.cfg)
            ModuleUtils.create_port(cfg_bit, 'cfg_e', 1, PortDirection.input_,
                    clock = 'cfg_clk', net_class = NetClass.cfg)
            ModuleUtils.create_port(cfg_bit, 'cfg_i', cfg_width, PortDirection.input_,
                    clock = 'cfg_clk', net_class = NetClass.cfg)
            ModuleUtils.create_port(cfg_bit, 'cfg_o', cfg_width, PortDirection.output,
                    clock = 'cfg_clk', net_class = NetClass.cfg)
            ModuleUtils.create_port(cfg_bit, 'cfg_d', 1, PortDirection.output,
                    clock = 'cfg_clk', net_class = NetClass.cfg)
            ModuleUtils.elaborate(cfg_bit)
            context._database[ModuleView.logical, cfg_bit.key] = cfg_bit

        # register fracturable LUT6
        if True:
            # user view
            fraclut6 = context.create_multimode('fraclut6')
            fraclut6.create_input("in", 6)
            fraclut6.create_output("o6", 1)
            fraclut6.create_output("o5", 1)

            if True:
                mode = fraclut6.create_mode("lut6x1")
                inst = mode.instantiate(context.primitives["lut6"], "LUT6A")
                mode.connect(mode.ports["in"], inst.pins["in"])
                mode.connect(inst.pins["out"], mode.ports["o6"], pack_patterns = ("lut6_dff", ))
                mode.commit()

            if True:
                mode = fraclut6.create_mode("lut5x2")
                inst = mode.instantiate(context.primitives["lut5"], "LUT5A")
                mode.connect(mode.ports["in"][:5], inst.pins["in"])
                mode.connect(inst.pins["out"], mode.ports["o6"], pack_patterns = ("lut5A_dff", ))
                inst = mode.instantiate(context.primitives["lut5"], "LUT5B")
                mode.connect(mode.ports["in"][:5], inst.pins["in"], pack_patterns = ("lut5B_dff", ))
                mode.connect(inst.pins["out"], mode.ports["o5"])
                mode.commit()

            fraclut6 = fraclut6.create_logical_counterpart(
                    cfg_bitcount = 65, verilog_template = "fraclut6.tmpl.v")

            # combinational paths
            fraclut6.add_combinational_path(fraclut6.ports["in"], fraclut6.ports["o6"])
            fraclut6.add_combinational_path(fraclut6.ports["in"][:5], fraclut6.ports["o5"])

            # configuration ports
            fraclut6.create_cfg_port('cfg_clk', 1, PortDirection.input_, is_clock = True)
            fraclut6.create_cfg_port('cfg_e', 1, PortDirection.input_, clock = 'cfg_clk')
            fraclut6.create_cfg_port('cfg_i', cfg_width, PortDirection.input_, clock = 'cfg_clk')
            fraclut6.create_cfg_port('cfg_o', cfg_width, PortDirection.output, clock = 'cfg_clk')

            if True:
                mode = fraclut6.edit_mode("lut6x1", cfg_mode_selection = (64, ))
                inst = mode.instantiate(context._database[ModuleView.logical, 'lut6'], "LUT6A")
                mode.connect(mode.ports["in"], inst.pins["in"])
                mode.connect(inst.pins["out"], mode.ports["o6"])
                inst.cfg_bitoffset = 0
                mode.commit()

            if True:
                mode = fraclut6.edit_mode("lut5x2", cfg_mode_selection = tuple())
                inst = mode.instantiate(context._database[ModuleView.logical, 'lut5'], "LUT5A")
                mode.connect(mode.ports["in"][:5], inst.pins["in"])
                mode.connect(inst.pins["out"], mode.ports["o6"])
                inst.cfg_bitoffset = 0
                inst = mode.instantiate(context._database[ModuleView.logical, 'lut5'], "LUT5B")
                mode.connect(mode.ports["in"][:5], inst.pins["in"])
                mode.connect(inst.pins["out"], mode.ports["o5"])
                inst.cfg_bitoffset = 32
                mode.commit()

            fraclut6.commit()

        # register multi-mode flipflop
        if True:
            # user view
            mdff = context.create_primitive("mdff",
                    techmap_template = "mdff.techmap.tmpl.v",
                    premap_commands = (
                        "simplemap t:$dff t:$dffe t:$dffsr",
                        "dffsr2dff",
                        "dff2dffe",
                        "opt -full",
                        ),
                    parameters = {
                        "ENABLE_CE": "1'b0",
                        "ENABLE_SR": "1'b0",
                        "SR_SET": "1'b0",
                        })
            mdff.create_clock("clk")
            mdff.create_input("D", 1, clock = "clk")
            mdff.create_output("Q", 1, clock = "clk")
            mdff.create_input("ce", 1, clock = "clk")
            mdff.create_input("sr", 1, clock = "clk")

            # logical view
            mdff = mdff.create_logical_counterpart(
                    cfg_bitcount = 3,
                    verilog_template = "mdff.tmpl.v",
                    parameters = {
                        "ENABLE_CE": 0,
                        "ENABLE_SR": 1,
                        "SR_SET": 2,
                        })
            mdff.create_cfg_port('cfg_clk', 1, PortDirection.input_, is_clock = True)
            mdff.create_cfg_port('cfg_e', 1, PortDirection.input_, clock = 'cfg_clk')
            mdff.create_cfg_port('cfg_i', cfg_width, PortDirection.input_, clock = 'cfg_clk')
            mdff.create_cfg_port('cfg_o', cfg_width, PortDirection.output, clock = 'cfg_clk')
            mdff.commit()

        return context

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        r = FileRenderer()
        r.template_search_paths.insert(0, ADDITIONAL_TEMPLATE_SEARCH_PATH)
        r.template_search_paths.extend(additional_template_search_paths)
        return r

    @classmethod
    def complete_scanchain(cls, context, module):
        """Complete the scanchain."""
        # special process needed for IO blocks (output enable)
        if module.module_class.is_io_block:
            oe = module.ports.get('_oe')
            if oe is not None:
                inst = ModuleUtils.instantiate(module, context.database[ModuleView.logical, 'cfg_bit'], '_cfg_oe')
                NetUtils.connect(inst.pins["cfg_d"], oe)
        # connecting scanchain ports
        cfg_bitoffset = 0
        cfg_clk, cfg_e, cfg_i, cfg_o = (None, ) * 4
        for instance in itervalues(module.instances):
            if instance.model.module_class not in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.cfg):
                if not hasattr(instance.model, 'cfg_bitcount'):
                    cls.complete_scanchain(context, instance.model)
            # enable pin
            inst_cfg_e = instance.pins.get('cfg_e')
            if inst_cfg_e is None:
                continue
            cfg_e = cls._get_or_create_cfg_ports(module, context.cfg_width, True)
            NetUtils.connect(cfg_e, inst_cfg_e)
            # actual bitstream loading pin
            inst_cfg_i = instance.pins.get('cfg_i')
            if inst_cfg_i is None:
                continue
            assert len(inst_cfg_i) == context.cfg_width
            if cfg_clk is None:
                cfg_clk, cfg_i, cfg_o = cls._get_or_create_cfg_ports(module, context.cfg_width)
            instance.cfg_bitoffset = cfg_bitoffset
            NetUtils.connect(cfg_clk, instance.pins['cfg_clk'])
            NetUtils.connect(cfg_i, inst_cfg_i)
            cfg_i = instance.pins['cfg_o']
            cfg_bitoffset += instance.model.cfg_bitcount
        if cfg_i is not None:
            NetUtils.connect(cfg_i, cfg_o)
        module.cfg_bitcount = cfg_bitoffset
        ModuleUtils.elaborate(module)
        if module.key == context.top.key:
            context.summary.bitstream_size = cfg_bitoffset
