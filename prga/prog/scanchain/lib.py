# -*- encoding: ascii -*-

from ..common import AbstractProgCircuitryEntry, ProgDataBitmap
from ...core.common import NetClass, ModuleClass, ModuleView
from ...core.context import Context
from ...passes.base import AbstractPass
from ...passes.translation import SwitchDelegate
from ...passes.vpr.delegate import FASMDelegate
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
            return ".".join(cls._bitmap(i.prog_bitmap) for i in reversed(hierarchy.hierarchy))

    def fasm_mux_for_intrablock_switch(self, source, sink, hierarchy = None):
        conn = NetUtils.get_connection(source, sink, skip_validations = True)
        if (prog_enable := getattr(conn, "prog_enable", self._none)) is not self._none:
            if prog_enable is None:
                return tuple()
            else:
                return self._value(prog_enable, True)
        fasm_features = []
        for net in getattr(conn, "switch_path", tuple()):
            bus, idx = (net.bus, net.index) if net.net_type.is_bit else (net, 0)
            fasm_features.extend("+{}#{}.{}".format(
                bus.instance.scanchain_offset, len(bus.instance.pins["prog_data"]), v)
                for v in self._value(bus.instance.model.prog_enable[idx], True))
        return tuple(fasm_features)

    def fasm_params_for_primitive(self, instance):
        leaf = instance.hierarchy[0]
        if (parameters := getattr(leaf, "prog_parameters", self._none)) is self._none:
            if (parameters := getattr(leaf.model, "prog_parameters", self._none)) is self._none:
                return {}
        return {k: bitmap for k, v in uno(parameters, {}).items()
                if (bitmap := self._bitmap(v, True))}

    def fasm_prefix_for_intrablock_module(self, module, hierarchy = None):
        if hierarchy:
            leaf = hierarchy.hierarchy[0]
            if (prog_bitmap := getattr(leaf, "prog_bitmap", None)) is not None:
                return self._bitmap(prog_bitmap)
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
            return self._value(prog_enable, True)

    def fasm_lut(self, instance):
        leaf = instance.hierarchy[0]
        if (parameters := getattr(leaf, "prog_parameters", self._none)) is self._none:
            if (parameters := getattr(leaf.model, "prog_parameters", self._none)) is self._none:
                return None
        if (bitmap := parameters.get("lut")) is not None:
            if len(bitmap._bitmap) != 2:
                raise PRGAInternalError("Invalid bitmap for LUT: {}".format(instance.model))
            return self._bitmap(bitmap, True)
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
        return FileRenderer(*additional_template_search_paths, ADDITIONAL_TEMPLATE_SEARCH_PATH)

    @classmethod
    def insert_scanchain(cls, context, design_view = None, *,
            iter_instances = None, insert_delimiter = None):
        """Insert the scanchain.
        
        Args:
            context (`Context`):
            design_view (`Module`): The module (design view) in which scanchain is inserted. If not specified, the
                top-level array in ``context`` is selected

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module
            insert_delimiter (:obj:`Function` [`Module` ] -> :obj:`bool`): Determine if `we` buffers are inserted at
                the beginning and end of the scanchain inside ``design_view``. By default, buffers are inserted in
                all logic/IO blocks and routing boxes.

        This method calls itself recursively to process all the instances (sub-modules).
        """

        chain_width = context.summary.scanchain["chain_width"]
        lmod = uno(design_view, context.database[ModuleView.design, context.top.key])
        umod = context.database[ModuleView.abstract, lmod.key]
        iter_instances = uno(iter_instances, lambda m: m.instances.values())
        insert_delimiter = uno(insert_delimiter, lambda m: m.module_class.is_block or m.module_class.is_routing_box)

        # quick check
        if lmod.module_class.is_primitive:
            return 0
            # raise PRGAInternalError("No programming information about module: {}"
            #         .format(lmod))

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
                prog_nets = cls._get_or_create_scanchain_prog_nets(lmod, chain_width)

                # insert delimeter if necessary
                if insert_delimiter(lmod):
                    if (delim := lmod.instances.get("i_scanchain_head")) is None:
                        delim = ModuleUtils.instantiate(lmod,
                                context.database[ModuleView.design, "scanchain_delim"], "i_scanchain_head")
                        for key in ("prog_clk", "prog_rst", "prog_done", "prog_we", "prog_din"):
                            NetUtils.connect(prog_nets[key], delim.pins[key])

                    prog_nets["prog_we"] = delim.pins["prog_we_o"]
                    prog_nets["prog_we_o"] = True
                    prog_nets["prog_din"] = delim.pins["prog_dout"]

            # data loading: 2 types
            ichain, bitcount = None, None

            # type (A): Embedded programming. `prog_we`, `prog_din` and `prog_dout` ports
            if prog_data is None:
                ichain, bitcount = linst, linst.model.scanchain_bitcount

            # type (B): External programming. `prog_data` ports
            else:
                ichain = ModuleUtils.instantiate(lmod,
                        cls._get_or_create_scanchain_data_cell(context, len(prog_data)),
                        "i_prog_data_{}".format(linst.name))
                NetUtils.connect(ichain.pins["prog_data"], prog_data)
                bitcount = len(prog_data)

            # connect
            for key in ("prog_clk", "prog_rst", "prog_done"):
                if (src := NetUtils.get_source(ichain.pins[key])) is None:
                    NetUtils.connect(prog_nets[key], ichain.pins[key])
            for key in ("prog_we", "prog_din"):
                NetUtils.connect(prog_nets[key], ichain.pins[key])
            if (prog_we_o := ichain.pins.get("prog_we_o")) is not None:
                prog_nets["prog_we"] = prog_we_o
                prog_nets["prog_we_o"] = True
            prog_nets["prog_din"] = ichain.pins["prog_dout"]

            # update
            linst.scanchain_offset = offset
            if (uinst := umod.instances.get(linst.key)) is not None:
                uinst.prog_bitmap = ProgDataBitmap( (offset, bitcount) )
            offset += bitcount

        # close this segment
        if prog_nets:

            # insert delimeter if necessary
            if insert_delimiter(lmod):
                # align to `chain_width`
                if offset % chain_width != 0:
                    remainder = chain_width - (offset % chain_width)
                    ichain = ModuleUtils.instantiate(lmod,
                            cls._get_or_create_scanchain_data_cell(context, remainder),
                            "i_prog_align")
                    for key in ("prog_clk", "prog_rst", "prog_done", "prog_we", "prog_din"):
                        NetUtils.connect(prog_nets[key], ichain.pins[key])
                    prog_nets["prog_din"] = ichain.pins["prog_dout"]
                    offset += remainder

                # insert trailing delimeter
                if (delim := lmod.instances.get("i_scanchain_tail")) is None:
                    delim = ModuleUtils.instantiate(lmod,
                            context.database[ModuleView.design, "scanchain_delim"], "i_scanchain_tail")
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

        return offset

    @classmethod
    def _register_cells(cls, context):
        # register scanchain delimeter
        delim = Module("scanchain_delim",
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.prog,
                verilog_template = "scanchain_delim.tmpl.v")
        cls._get_or_create_scanchain_prog_nets(delim, context.summary.scanchain["chain_width"])
        ModuleUtils.create_port(delim, "prog_we_o", 1, PortDirection.output, net_class = NetClass.prog)

        context._database[ModuleView.design, "scanchain_delim"] = delim

    @classmethod
    def _get_or_create_scanchain_data_cell(cls, context, data_width):
        """Get the programming data module for ``data_width`` bits.

        Args:
            context (`Context`):
            data_width (:obj:`int`):

        Returns:
            `Module`:
        """
        key = ("scanchain_data", data_width)

        if (module := context.database.get( (ModuleView.design, key) )) is None:
            module = Module("scanchain_data_d{}".format(data_width),
                    is_cell = True,
                    view = ModuleView.design,
                    module_class = ModuleClass.prog,
                    verilog_template = "scanchain_data.tmpl.v",
                    key = key)

            cls._get_or_create_scanchain_prog_nets(module, context.summary.scanchain["chain_width"])
            ModuleUtils.create_port(module, "prog_data", data_width, PortDirection.output, net_class = NetClass.prog)

            context._database[ModuleView.design, key] = module

        return module

    @classmethod
    def _get_or_create_scanchain_prog_nets(cls, module, chain_width, excludes = None):
        nets = {}
        excludes = set(uno(excludes, []))

        # prog_clk
        if "prog_clk" not in excludes:
            if (prog_clk := module.ports.get("prog_clk")) is None:
                prog_clk = ModuleUtils.create_port(module, "prog_clk", 1, PortDirection.input_,
                        is_clock = True, net_class = NetClass.prog)
            nets["prog_clk"] = prog_clk

        # prog_rst
        if "prog_rst" not in excludes:
            if (buf := module.instances.get("i_buf_prog_rst_l0")) is None:
                if (port := module.ports.get("prog_rst")) is None:
                    port = ModuleUtils.create_port(module, "prog_rst", 1, PortDirection.input_,
                            net_class = NetClass.prog)
                nets["prog_rst"] = port
            else:
                nets["prog_rst"] = buf.pins["Q"]

        # prog_done
        if "prog_done" not in excludes:
            if (buf := module.instances.get("i_buf_prog_done_l0")) is None:
                if (port := module.ports.get("prog_done")) is None:
                    port = ModuleUtils.create_port(module, "prog_done", 1, PortDirection.input_,
                            net_class = NetClass.prog)
                nets["prog_done"] = port
            else:
                nets["prog_done"] = buf.pins["Q"]

        # prog_we
        if "prog_we" not in excludes:
            if (delim := module.instances.get("i_scanchain_head")) is None:
                if (port := module.ports.get("prog_we")) is None:
                    port = ModuleUtils.create_port(module, "prog_we", 1, PortDirection.input_,
                            net_class = NetClass.prog)
                nets["prog_we"] = port
            else:
                nets["prog_we"] = delim.pins["prog_we_o"]

        # prog_din, prog_dout
        for key, direction in zip(("prog_din", "prog_dout"), PortDirection):
            if key not in excludes:
                if (port := module.ports.get(key)) is None:
                    port = ModuleUtils.create_port(module, key, chain_width, direction,
                            net_class = NetClass.prog)
                nets[key] = port
        
        return nets

    class InsertProgCircuitry(AbstractPass):
        """Insert programming circuitry.

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module
            insert_delimiter (:obj:`Function` [`Module` ] -> :obj:`bool`): Determine if `we` buffers are inserted at
                the beginning and end of the scanchain inside ``design_view``. By default, buffers are inserted in
                all logic/IO blocks and routing boxes.
        
        """

        __slots__ = ["iter_instances", "insert_delimiter"]

        def __init__(self, *, iter_instances = None, insert_delimiter = None):
            self.iter_instances = iter_instances
            self.insert_delimiter = insert_delimiter

        def run(self, context, renderer = None):
            Scanchain.buffer_prog_ctrl(context)
            context.summary.scanchain["bitstream_size"] = Scanchain.insert_scanchain(context,
                    iter_instances = self.iter_instances, insert_delimiter = self.insert_delimiter)

        @property
        def key(self):
            return "prog.insertion.scanchain"

        @property
        def dependences(self):
            return ("annotation.switch_path", )

        @property
        def passes_after_self(self):
            return ("rtl", )
