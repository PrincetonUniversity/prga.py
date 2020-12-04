# -*- encoding: ascii -*-

from ..common import AbstractProgCircuitryEntry
from ...core.common import NetClass, ModuleClass, ModuleView
from ...core.context import Context
from ...passes.base import AbstractPass
from ...passes.translation import SwitchDelegate
from ...passes.vpr.delegate import FASMDelegate
from ...prog import ProgDataBitmap
from ...netlist import Module, ModuleUtils, PortDirection, NetUtils
from ...renderer import FileRenderer
from ...util import uno
from ...exception import PRGAInternalError

import os, logging

_logger = logging.getLogger(__name__)

ADDITIONAL_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class ScanchainFASMDelegate(FASMDelegate):
    """FASM delegate for scanchain programming circuitry.
    
    Args:
        context (`Context`):
    """

    _none = object()

    __slots__ = ['context']
    def __init__(self, context):
        self.context = context

    @classmethod
    def __hierarchy_prefix(cls, hierarchy = None):
        if hierarchy is None:
            return ""
        else:
            return ".".join(cls.__bitmap(i.prog_bitmap) for i in reversed(hierarchy.hierarchy))

    @classmethod
    def __bitmap(cls, bitmap, allow_alternative = False):
        if allow_alternative and len(bitmap._bitmap) == 2:
            range_ = bitmap._bitmap[0][1]
            return "[{}:{}]".format(range_.offset + range_.length - 1, range_.offset)
        else:
            return "".join("+{}#{}".format(o, l) for _, (o, l) in bitmap._bitmap[:-1])

    @classmethod
    def __value(cls, value, breakdown = False, prefix = None):
        if breakdown:
            if prefix is None:
                return tuple("+{}#{}.~{}'h{:x}".format(o, l, l, v)
                        for v, (o, l) in value.breakdown())
            else:
                return tuple("{}.+{}#{}.~{}'h{:x}".format(prefix, o, l, l, v)
                        for v, (o, l) in value.breakdown())
        else:
            if prefix is None:
                return cls.__bitmap(value.bitmap) + ".~{}'h{:x}".format(
                        value.bitmap._bitmap[-1][0], value.value)
            else:
                return prefix + "." + cls.__bitmap(value.bitmap) + ".~{}'h{:x}".format(
                        value.bitmap._bitmap[-1][0], value.value)

    def fasm_mux_for_intrablock_switch(self, source, sink, hierarchy = None):
        conn = NetUtils.get_connection(source, sink, skip_validations = True)
        if (prog_enable := getattr(conn, "prog_enable", self._none)) is not self._none:
            if prog_enable is None:
                return tuple()
            else:
                return self.__value(prog_enable, True)
        fasm_features = []
        for net in getattr(conn, "logical_path", tuple()):
            bus, idx = (net.bus, net.index) if net.net_type.is_bit else (net, 0)
            fasm_features.extend(self.__value(bus.instance.model.prog_enable[idx], True,
                "+{}#{}".format(bus.instance.scanchain_offset, len(bus.instance.pins["prog_data"]))))
        return tuple(fasm_features)

    def fasm_params_for_primitive(self, instance):
        leaf = instance.hierarchy[0]
        if (parameters := getattr(leaf, "prog_parameters", self._none)) is self._none:
            if (parameters := getattr(leaf.model, "prog_parameters", self._none)) is self._none:
                return {}
        return {k: bitmap for k, v in uno(parameters, {}).items()
                if (bitmap := self.__bitmap(v, True))}

    def fasm_prefix_for_intrablock_module(self, module, hierarchy = None):
        if hierarchy:
            leaf = hierarchy.hierarchy[0]
            if (prog_bitmap := getattr(leaf, "prog_bitmap", None)) is not None:
                return self.__bitmap(prog_bitmap)
            else:
                return None
        else:
            return None

    def fasm_features_for_intrablock_module(self, module, hierarchy = None):
        if (module.module_class.is_mode
                or hierarchy is None
                or (prog_enable := getattr(hierarchy.hierarchy[0], "prog_enable", self._none)) is self._none):
            prog_enable = getattr(module, "prog_enable", None)
        if prog_enable is None:
            return tuple()
        else:
            return self.__value(prog_enable, True)

    def fasm_lut(self, instance):
        leaf = instance.hierarchy[0]
        if (parameters := getattr(leaf, "prog_parameters", self._none)) is self._none:
            if (parameters := getattr(leaf.model, "prog_parameters", self._none)) is self._none:
                return None
        if (bitmap := parameters.get("lut")) is not None:
            if len(bitmap._bitmap) != 2:
                raise PRGAInternalError("Invalid bitmap for LUT: {}".format(instance.model))
            return self.__bitmap(bitmap, True)
        else:
            return None

    def fasm_prefix_for_tile(self, instance):
        retval = []
        for subtile, blkinst in instance.model.instances.items():
            if not isinstance(subtile, int):
                continue
            elif subtile >= len(retval):
                retval.extend(None for _ in range(subtile - len(retval) + 1))
            retval[subtile] = self.__hierarchy_prefix(blkinst._extend_hierarchy(above = instance))
        return tuple(retval)

    def fasm_features_for_interblock_switch(self, source, sink, hierarchy = None):
        if (features := self.fasm_mux_for_intrablock_switch(source, sink, hierarchy)):
            if prefix := self.__hierarchy_prefix(hierarchy):
                return tuple(prefix + "." + feature for feature in features)
            else:
                return features
        else:
            return tuple()

# ----------------------------------------------------------------------------
# -- Scanchain Programming Circuitry Main Entry ------------------------------
# ----------------------------------------------------------------------------
class Scanchain(AbstractProgCircuitryEntry):
    """Entry point for scanchain programming circuitry."""

    @classmethod
    def new_context(cls, chain_width = 1):
        ctx = Context("scanchain")
        ctx.summary.scanchain = {"chain_width": chain_width}
        ctx._switch_delegate = SwitchDelegate(ctx)
        ctx._fasm_delegate = ScanchainFASMDelegate(ctx)
        cls._register_cells(ctx)
        return ctx

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        """Create a new file renderer.

        Args:
            additional_template_search_paths (:obj:`Sequence` [:obj:`str` ]): Additional paths where the renderer
                should search for template files

        Returns:
            `FileRenderer`:
        """
        r = FileRenderer(*additional_template_search_paths, ADDITIONAL_TEMPLATE_SEARCH_PATH)
        return r

    @classmethod
    def _get_or_create_prog_nets(cls, module, chain_width):
        nets = {}

        # prog_clk
        if (prog_clk := module.ports.get("prog_clk")) is None:
            prog_clk = ModuleUtils.create_port(module, "prog_clk", 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.prog)
        nets["prog_clk"] = prog_clk

        # prog_rst
        if (buf := module.instances.get("i_buf_prog_rst_l0")) is None:
            if (port := module.ports.get("prog_rst")) is None:
                port = ModuleUtils.create_port(module, "prog_rst", 1, PortDirection.input_,
                        net_class = NetClass.prog)
            nets["prog_rst"] = port
        else:
            nets["prog_rst"] = buf.pins["Q"]

        # prog_done
        if (buf := module.instances.get("i_buf_prog_done_l0")) is None:
            if (port := module.ports.get("prog_done")) is None:
                port = ModuleUtils.create_port(module, "prog_done", 1, PortDirection.input_,
                        net_class = NetClass.prog)
            nets["prog_done"] = port
        else:
            nets["prog_done"] = buf.pins["Q"]

        # prog_we
        if (delim := module.instances.get("i_scanchain_head")) is None:
            if (port := module.ports.get("prog_we")) is None:
                port = ModuleUtils.create_port(module, "prog_we", 1, PortDirection.input_,
                        net_class = NetClass.prog)
            nets["prog_we"] = port
        else:
            nets["prog_we"] = delim.pins["prog_we_o"]

        # prog_din, prog_dout
        for key, direction in zip(("prog_din", "prog_dout"), PortDirection):
            if (port := module.ports.get(key)) is None:
                port = ModuleUtils.create_port(module, key, chain_width, direction,
                        net_class = NetClass.prog)
            nets[key] = port
        
        return nets

    @classmethod
    def _register_cells(cls, context):
        # register scanchain delimeter
        delim = Module("scanchain_delim",
                is_cell = True,
                view = ModuleView.logical,
                module_class = ModuleClass.prog,
                verilog_template = "scanchain_delim.tmpl.v")
        cls._get_or_create_prog_nets(delim, context.summary.scanchain["chain_width"])
        ModuleUtils.create_port(delim, "prog_we_o", 1, PortDirection.output, net_class = NetClass.prog)

        context._database[ModuleView.logical, "scanchain_delim"] = delim

    @classmethod
    def _get_prog_data_cell(cls, context, data_width):
        """Get the programming data module for ``data_width`` bits.

        Args:
            context (`Context`):
            data_width (:obj:`int`):

        Returns:
            `Module`:
        """
        key = ("scanchain_data", data_width)

        if (module := context.database.get( (ModuleView.logical, key) )) is None:
            module = Module("scanchain_data_d{}".format(data_width),
                    is_cell = True,
                    view = ModuleView.logical,
                    module_class = ModuleClass.prog,
                    verilog_template = "scanchain_data.tmpl.v",
                    key = key)

            cls._get_or_create_prog_nets(module, context.summary.scanchain["chain_width"])
            ModuleUtils.create_port(module, "prog_data", data_width, PortDirection.output, net_class = NetClass.prog)

            context._database[ModuleView.logical, key] = module

        return module

    @classmethod
    def insert_scanchain(cls, context, logical_module = None, *,
            iter_instances = None):
        """Insert the scanchain.
        
        Args:
            context (`Context`):
            logical_module (`Module`): The module (logical view) in which scanchain is inserted. If not specified, the
                top-level array in ``context`` is selected

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module

        This method calls itself recursively to process all the instances (sub-modules).
        """

        chain_width = context.summary.scanchain["chain_width"]
        lmod = uno(logical_module, context.database[ModuleView.logical, context.top.key])
        umod = context.database[ModuleView.user, lmod.key]
        iter_instances = uno(iter_instances, lambda m: m.instances.values())

        # quick check
        if lmod.module_class.is_primitive:
            raise PRGAInternalError("No programming information about module: {}"
                    .format(lmod))

        # traverse programmable instances, instantiate programming cells and connect stuff
        offset = 0
        prog_nets = None
        instances_snapshot = tuple(iter_instances(lmod))

        for linst in instances_snapshot:
            if linst.model.module_class.is_prog:
                raise PRGAInternalError("Existing programming cell found during programming cell insertion: {}"
                        .format(linst))
            elif linst.model.module_class.is_aux:
                # _logger.warning("Auxiliary cell found during programming cell insertion: {}"
                #         .format(linst))
                continue

            # check if `linst` requires programming data
            if (prog_data := linst.pins.get("prog_data")) is None:
                if (bitcount := getattr(linst.model, "scanchain_bitcount", None)) is None:
                    bitcount = cls.insert_scanchain(context, linst.model, iter_instances = iter_instances)
                if bitcount == 0:
                    continue

            # if we haven't initialize programming nets in this module, do it now
            if not prog_nets:
                prog_nets = cls._get_or_create_prog_nets(lmod, chain_width)

                # insert delimeter if necessary
                if lmod.module_class.is_block or lmod.module_class.is_routing_box:
                    if (delim := lmod.instances.get("i_scanchain_head")) is None:
                        delim = ModuleUtils.instantiate(lmod,
                                context.database[ModuleView.logical, "scanchain_delim"], "i_scanchain_head")
                        for key in ("prog_clk", "prog_rst", "prog_done", "prog_we", "prog_din"):
                            NetUtils.connect(prog_nets[key], delim.pins[key])

                    prog_nets["prog_we"] = delim.pins["prog_we_o"]
                    prog_nets["prog_we_o"] = True
                    prog_nets["prog_din"] = delim.pins["prog_dout"]

            # data loading: 2 types
            idata, bitcount = None, None

            # type (A): Embedded programming. `prog_we`, `prog_din` and `prog_dout` ports
            if prog_data is None:
                idata, bitcount = linst, linst.model.scanchain_bitcount

            # type (B): External programming. `prog_data` ports
            else:
                idata = ModuleUtils.instantiate(lmod,
                        cls._get_prog_data_cell(context, len(prog_data)),
                        "i_prog_data_{}".format(linst.name))
                NetUtils.connect(idata.pins["prog_data"], prog_data)
                bitcount = len(prog_data)

            # connect
            for key in ("prog_clk", "prog_rst", "prog_done"):
                if (src := NetUtils.get_source(idata.pins[key])) is None:
                    NetUtils.connect(prog_nets[key], idata.pins[key])
            for key in ("prog_we", "prog_din"):
                NetUtils.connect(prog_nets[key], idata.pins[key])
            if (prog_we_o := idata.pins.get("prog_we_o")) is not None:
                prog_nets["prog_we"] = prog_we_o
                prog_nets["prog_we_o"] = True
            prog_nets["prog_din"] = idata.pins["prog_dout"]

            # update
            linst.scanchain_offset = offset
            if (uinst := umod.instances.get(linst.key)) is not None:
                uinst.prog_bitmap = ProgDataBitmap( (offset, bitcount) )
            offset += bitcount

        # close this segment
        if prog_nets:

            # insert delimeter if necessary
            if lmod.module_class.is_block or lmod.module_class.is_routing_box:
                # align to `chain_width`
                if offset % chain_width != 0:
                    remainder = chain_width - (offset % chain_width)
                    idata = ModuleUtils.instantiate(lmod,
                            cls._get_prog_data_cell(context, remainder),
                            "i_prog_align")
                    for key in ("prog_clk", "prog_rst", "prog_done", "prog_we", "prog_din"):
                        NetUtils.connect(prog_nets[key], idata.pins[key])
                    prog_nets["prog_din"] = idata.pins["prog_dout"]
                    offset += remainder

                # insert trailing delimeter
                if (delim := lmod.instances.get("i_scanchain_tail")) is None:
                    delim = ModuleUtils.instantiate(lmod,
                            context.database[ModuleView.logical, "scanchain_delim"], "i_scanchain_tail")
                    for key in ("prog_clk", "prog_rst", "prog_done", "prog_we", "prog_din"):
                        NetUtils.connect(prog_nets[key], delim.pins[key])
                    prog_nets["prog_din"] = delim.pins["prog_dout"]
                    prog_nets["prog_we"] = delim.pins["prog_we_o"]
                    prog_nets["prog_we_o"] = True

            # connect outputs
            NetUtils.connect(prog_nets["prog_din"], prog_nets["prog_dout"])
            if "prog_we_o" in prog_nets:
                if (prog_we_o := lmod.ports.get("prog_we_o")) is None:
                    prog_we_o = ModuleUtils.create_port(lmod, "prog_we_o", 1, PortDirection.output,
                            net_class = NetClass.prog)
                NetUtils.connect(prog_nets["prog_we"], prog_we_o)

        # update module
        lmod.scanchain_bitcount = offset
        _logger.info("Scanchain inserted to {}. Total bits: {}".format(lmod, offset))

        if lmod.key == context.top.key:
            context.summary.scanchain["bitstream_size"] = offset

        return offset

    class InsertProgCircuitry(AbstractPass):
        """Insert programming circuitry.

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module
        
        """

        __slots__ = ["iter_instances"]

        def __init__(self, *, iter_instances = None):
            self.iter_instances = iter_instances

        def run(self, context, renderer = None):
            AbstractProgCircuitryEntry.buffer_prog_ctrl(context)
            Scanchain.insert_scanchain(context)

        @property
        def key(self):
            return "prog.insertion.scanchain"

        @property
        def dependences(self):
            return ("annotation.logical_path", )

        @property
        def passes_after_self(self):
            return ("rtl", )
