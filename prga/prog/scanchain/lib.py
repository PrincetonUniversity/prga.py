# -*- encoding: ascii -*-

from ..common import AbstractProgCircuitryEntry, ProgDataBitmap
from ...core.common import NetClass, ModuleClass, ModuleView
from ...passes.translation import SwitchDelegate
from ...netlist import Module, ModuleUtils, PortDirection, NetUtils
from ...renderer import BuiltinCellLibrary, OnDemandCellLibrary
from ...util import uno
from ...exception import PRGAInternalError

import os, logging

_logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# -- Scanchain Programming Circuitry Main Entry ------------------------------
# ----------------------------------------------------------------------------
class Scanchain(AbstractProgCircuitryEntry):
    """Entry point for scanchain programming circuitry."""

    @classmethod
    def materialize(cls, ctx, inplace = False, *,
            chain_width = 1):

        ctx = super().materialize(ctx, inplace = inplace)
        ctx._switch_delegate = SwitchDelegate(ctx)

        BuiltinCellLibrary.install_stdlib(ctx)
        BuiltinCellLibrary.install_design(ctx)
        OnDemandCellLibrary.install_design(ctx)

        ctx.template_search_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
        ctx.renderer = None

        ctx.summary.scanchain = {"chain_width": chain_width}
        ctx.summary.prog_support_magic_checker = True
        cls.__install_cells(ctx)

        return ctx

    @classmethod
    def insert_prog_circuitry(cls, context, *,
            iter_instances = None, insert_delimiter = None):
        cls.buffer_prog_ctrl(context)
        context.summary.scanchain["bitstream_size"] = cls._insert_scanchain(context,
                iter_instances = iter_instances, insert_delimiter = insert_delimiter)

    @classmethod
    def _insert_scanchain(cls, context, design_view = None, *,
            iter_instances = None, insert_delimiter = None):
        """Insert the scanchain.
        
        Args:
            context (`Context`):
            design_view (`Module`): The module (design view) in which scanchain is inserted. If not specified, the
                top-level array in ``context`` is selected

        Keyword Args:
            iter_instances (:obj:`Function` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module
            insert_delimiter (:obj:`Function` [`Module` ] -> :obj:`bool`): Determine if ``we`` buffers are inserted at
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
                    bitcount = cls._insert_scanchain(context, linst.model, iter_instances = iter_instances)
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
            linst.scanchain_bitmap = ProgDataBitmap( (offset, bitcount) )
            if (uinst := umod.instances.get(linst.key)) is not None:
                uinst.scanchain_bitmap = linst.scanchain_bitmap
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
    def __install_cells(cls, context):
        # register scanchain delimeter
        delim = context._add_module(Module("scanchain_delim",
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.prog,
                verilog_template = "scanchain_delim.tmpl.v"))
        cls._get_or_create_scanchain_prog_nets(delim, context.summary.scanchain["chain_width"])
        ModuleUtils.create_port(delim, "prog_we_o", 1, PortDirection.output, net_class = NetClass.prog)

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
        excludes = set(uno(excludes, []))
        nets = cls._get_or_create_prog_nets(module, excludes)

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
