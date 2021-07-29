# -*- encoding: ascii -*-

from .protocol import PktchainProtocol
from ..common import ProgDataBitmap
from ..scanchain.lib import Scanchain
from ...core.common import ModuleClass, ModuleView, NetClass, Orientation, Corner
from ...netlist import PortDirection, Const, Module, NetUtils, ModuleUtils
from ...passes.base import AbstractPass
from ...passes.translation import SwitchDelegate
from ...integration import Integration
from ...integration.common import SystemIntf
from ...integration.rxi_yami import IntegrationRXIYAMI
from ...exception import PRGAInternalError
from ...tools.ioplan import IOPlanner
from ...util import uno, Object, Enum

import os, logging
from itertools import product, count

_logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# -- Pktchain Programming Circuitry Main Entry -------------------------------
# ----------------------------------------------------------------------------
class Pktchain(Scanchain):
    """Entry point for pktchain programming circuitry."""

    @classmethod
    def materialize(cls, ctx, inplace = False, *,
            phit_width = 8, chain_width = 1, router_fifo_depth_log2 = 4):

        if phit_width not in (1, 2, 4, 8, 16, 32):
            raise PRGAAPIError("Unsupported programming phit width: {}. Supported values are: [1, 2, 4, 8, 16, 32]"
                    .format(phit_width))
        if chain_width not in (1, 2, 4):
            raise PRGAAPIError("Unsupported programming chain width: {}. Supported values are: [1, 2, 4]"
                    .format(chain_width))

        ctx = super().materialize(ctx, inplace = inplace, chain_width = chain_width)
        ctx.summary.pktchain = {
                "fabric": {
                    "phit_width": phit_width,
                    "router_fifo_depth_log2": router_fifo_depth_log2,
                    },
                "protocol": PktchainProtocol
                }
        ctx.summary.prog_support_magic_checker = True

        ctx.template_search_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
        ctx.add_verilog_header("pktchain.vh", "include/pktchain.tmpl.vh")
        ctx.add_verilog_header("pktchain_system.vh", "piton_v0/include/pktchain_system.tmpl.vh",
                "pktchain.vh", "prga_system.vh")
        cls.__install_cells(ctx, chain_width, phit_width)

        return ctx

    @classmethod
    def insert_prog_circuitry(cls, context, *,
            iter_instances = None, insert_delimiter = None):
        cls.buffer_prog_ctrl(context)
        branches = cls._insert_pktchain(context,
                iter_instances = iter_instances, insert_delimiter = insert_delimiter)

        # update summary
        context.summary.pktchain["fabric"]["branches"] = branches
        num_leaves = len(branches[0])
        for i, branch in enumerate(branches[1:]):
            if len(branch) != num_leaves:
                raise PRGAInternalError("Unbalanced branch. Branch No. {} has {} leaves but others have {}"
                        .format(i + 1, len(branch), num_leaves))

                _logger.info("Pktchain inserted: {} branches on primary backbone, {} leaves per branch"
                        .format(len(branches), num_leaves))

        total = 0
        for i, branch in enumerate(branches):
            _logger.info(" .. Branch No. {}:".format(i))
            for j, leaf in enumerate(branch):
                _logger.info("   .. Leaf No. {}: {} bits".format(j, leaf))
                total += leaf
        _logger.info(" .. Total effective bitstream bits: {}".format(total))

    class _PktchainRouterCtrl(Enum):
        _terminate_leaf = 0
        _terminate_branch = 1

    TERMINATE_LEAF      = _PktchainRouterCtrl._terminate_leaf
    TERMINATE_BRANCH    = _PktchainRouterCtrl._terminate_branch

    class DefaultInstanceIterator(Object):
        """Default implementation of ``iter_instances`` to be used by ``Pktchain.insert_prog_circuitry``.

        Args:
            context (`Context`):
        """

        __slots__ = ["context"]

        def __init__(self, context):
            self.context = context

        def __call__(self, module):
            if module.module_class.is_array:
                abstract = self.context.database[ModuleView.abstract, module.key]

                # traverse columns
                for x in range(module.width):
                    for y in range(module.height):

                        # southwest switch-box
                        if i := module.instances.get( ((x, y), Corner.southwest) ): yield i

                        # southeast switch-box
                        if i := module.instances.get( ((x, y), Corner.southeast) ): yield i

                        # tile or array
                        if (root := abstract._instances.get_root( (x, y) )) and root.key.y == y:
                            if root.model.module_class.is_array:
                                #     instance,                     sub-branch ID
                                yield (module.instances[root.key],  root.key.x - x)

                            elif root.key.x == x:
                                yield module.instances[root.key]

                        # northwest switch-box
                        if i := module.instances.get( ((x, y), Corner.northwest) ): yield i

                        # northeast switch-box
                        if i := module.instances.get( ((x, y), Corner.northeast) ): yield i

                        # insert router if ``root`` is None or ``root`` is a tile instance
                        if root is None or root.model.module_class.is_tile:
                            yield Pktchain.TERMINATE_LEAF

                    # terminate branch
                    yield Pktchain.TERMINATE_BRANCH

            elif module.module_class.is_tile:
                # south connection-boxes
                for x in reversed(range(module.width)):
                    if i := module.instances.get( (Orientation.south, x) ): yield i

                # west connection-boxes
                for y in range(module.height):
                    if i := module.instances.get( (Orientation.west, y) ): yield i

                # block instances
                blocks = []
                for i in count():
                    if instance := module.instances.get(i):
                        blocks.append(instance)
                    else:
                        break
                for block in reversed(blocks):
                    yield block

                # east connection-boxes
                for y in range(module.height):
                    if i := module.instances.get( (Orientation.east, y) ): yield i

                # north connection-boxes
                for x in reversed(range(module.width)):
                    if i := module.instances.get( (Orientation.north, x) ): yield i

            else:
                for i in module.instances.values():
                    yield i

    @classmethod
    def _insert_pktchain(cls, context, design_view = None, *,
            iter_instances = None, insert_delimiter = None, _not_top = False):
        """Inject pktchain network and routers in ``module``. This method should be called only on arrays.

        Args:
            context (`Context`):
            design_view (`Module`): The module (design view) in which pktchain network and routers are injected. If
                not specified, the top-level array in ``context`` is selected

        Keyword Args:
            iter_instances (:obj:`Callable` [`Module` ] -> :obj:`Iterable` [`Instance` ]): Custom ordering of
                the instances in a module. In addition, when the module is an array, `Pktchain.TERMINATE_LEAF` can
                be yielded to control pktchain router injection. Furthermore, `Pktchain.TERMINATE_BRANCH` can be
                yielded to terminate the current branch and attach the branch to the main programming backbone (chunk).
            insert_delimiter (:obj:`Function` [`Module` ] -> :obj:`bool`): Determine if ``we`` buffers are inserted at
                the beginning and end of the scanchain inside ``design_view``. By default, buffers are inserted in
                all logic/IO blocks and routing boxes.
            _not_top (:obj:`bool`): If set, the array is treated as a non-top level array. This is primarily used when
                this method calls itself recursively
        """
        phit_width = context.summary.pktchain["fabric"]["phit_width"]
        chain_width = context.summary.scanchain["chain_width"]
        lmod = uno(design_view, context.database[ModuleView.design, context.top.key])
        umod = context.database[ModuleView.abstract, lmod.key]
        iter_instances = uno(iter_instances, cls.DefaultInstanceIterator(context))

        # quick check
        if not lmod.module_class.is_array:
            raise PRGAInternalError("{} is not an Array".format(lmod))
        
        # chunk
        dispatcher, gatherer = None, None

        # branch
        branches, branch_prog_nets = [], {}

        # leaf
        leaves, leaf_prog_nets, scanchain_offset = [], {}, 0

        # traverse instances
        for linst in iter_instances(lmod):

            if linst is cls.TERMINATE_LEAF:
                cls._wrap_pktchain_leaf(context, lmod, len(branches),
                        branch_prog_nets, leaves, leaf_prog_nets, scanchain_offset)
                scanchain_offset = 0
                continue
            
            elif linst is cls.TERMINATE_BRANCH:
                dispatcher, gatherer = cls._wrap_pktchain_branch(context, lmod,
                        dispatcher, gatherer, branch_prog_nets, branches, leaves, _not_top)
                continue

            # get sub-branch ID
            try:
                linst, sub_branch_id = linst
            except (TypeError, ValueError):
                sub_branch_id = len(getattr(linst, "pktchain_branchmap", []))

            if linst.model.module_class.is_prog:
                raise PRGAInternalError("Existing programming cell found during programming cell insertion: {}"
                        .format(linst))
            elif linst.model.module_class.is_aux:
                # _logger.warning("Auxiliary cell found during programming cell insertion: {}"
                #         .format(linst))
                continue

            # insert programming circuitry into ``linst``
            if linst.model.module_class.is_array:
                if ((sub_branches := getattr(linst.model, "pktchain_branches", None)) is None
                        and getattr(linst.model, "scanchain_bitcount", None) is None):
                    sub_branches = cls._insert_pktchain(context, linst.model,
                            iter_instances = iter_instances, insert_delimiter = insert_delimiter, _not_top = True)

                if not sub_branches:
                    cls._connect_pktchain_leaf(context, lmod, linst, leaf_prog_nets)
                    
                    linst.scanchain_bitmap = ProgDataBitmap( (scanchain_offset, linst.model.scanchain_bitcount) )
                    linst.pktchain_branchmap = (len(branches), len(leaves)),

                    if (uinst := umod.instances.get(linst.key)) is not None:
                        uinst.scanchain_bitmap = linst.scanchain_bitmap
                        uinst.pktchain_branchmap = linst.pktchain_branchmap

                    scanchain_offset += linst.model.scanchain_bitcount

                else:
                    if scanchain_offset > 0 or leaf_prog_nets:
                        raise PRGAInternalError("Unterminated leaf before merging sub-branches in {}".format(linst))

                    # get branch map
                    if not 0 <= sub_branch_id < len(sub_branches):
                        raise PRGAInternalError("{} does not have branch No. {}".format(linst.model, sub_branch_id))

                    # update branch settings
                    if (branchmap := getattr(linst, "pktchain_branchmap", None)) is None:
                        branchmap = linst.pktchain_branchmap = []
                    if sub_branch_id >= len(branchmap):
                        branchmap.extend(None for _ in range(sub_branch_id - len(branchmap) + 1))
                    _logger.debug(("Adding {} leaves ({} bits, respectively) from {} to branch "
                        "No. {} ({} leaves before adding) in {}")
                        .format(len(sub_branches[sub_branch_id]), ', '.join(map(str, sub_branches[sub_branch_id])),
                            linst, len(branches), len(leaves), lmod))
                    branchmap[sub_branch_id] = len(branches), len(leaves)   # branch ID, leaf ID (offset)
                    leaves.extend( sub_branches[sub_branch_id] )

                    if (uinst := umod.instances.get(linst.key)) is not None:
                        uinst.pktchain_branchmap = branchmap

                    # connect
                    if "o" in branch_prog_nets:
                        NetUtils.connect(branch_prog_nets["o"],
                                linst.pins[cls._pktchain_phit_port_name("i", sub_branch_id)])
                        NetUtils.connect(branch_prog_nets["o_wr"],
                                linst.pins[cls._pktchain_phit_port_name("i_wr", sub_branch_id)])
                        NetUtils.connect(linst.pins[cls._pktchain_phit_port_name("i_full", sub_branch_id)],
                                branch_prog_nets["o_full"])
                    else:
                        branch_prog_nets.update(
                                **{k: linst.pins[cls._pktchain_phit_port_name(k, sub_branch_id)]
                                    for k in ("i", "i_wr", "i_full")})
                    branch_prog_nets.update(
                            **{k: linst.pins[cls._pktchain_phit_port_name(k, sub_branch_id)]
                                for k in ("o", "o_wr", "o_full")})

            else:
                scanchain_offset += cls._insert_pktchain_leaf(
                        context, lmod, linst, iter_instances, insert_delimiter,
                        leaf_prog_nets, scanchain_offset, len(branches), len(leaves))

        # end of traversal
        if leaves:
            dispatcher, gatherer = cls._wrap_pktchain_branch(context, lmod,
                    dispatcher, gatherer, branch_prog_nets, branches, leaves, _not_top)

        if branches:
            if leaf_prog_nets or scanchain_offset > 0:
                raise PRGAInternalError("Unterminated leaf after end of instance traversal in {}".format(lmod))
            assert not branch_prog_nets

            lmod.pktchain_branches = tuple(branches)

        elif leaf_prog_nets:
            prog_ports = cls._get_or_create_scanchain_prog_nets(lmod, chain_width)

            # prog_we
            for sink in leaf_prog_nets.get("prog_we", []):
                NetUtils.connect(prog_ports["prog_we"], sink)

            # prog_din & prog_dout
            NetUtils.connect(prog_ports["prog_din"], leaf_prog_nets["prog_din"])
            NetUtils.connect(leaf_prog_nets["prog_dout"], prog_ports["prog_dout"])

            # prog_we_o
            if (prog_we_o := leaf_prog_nets.get("prog_we_o")) is not None:
                NetUtils.connect(prog_we_o,
                        ModuleUtils.create_port(lmod, "prog_we_o", 1, PortDirection.output, net_class = NetClass.prog))

            lmod.scanchain_bitcount = scanchain_offset

        # no programming data needed inside this array
        else:
            _logger.warning("No programming data needed in array: {}".format(lmod))
            lmod.scanchain_bitcount = 0

        # tie the control pins of the last dispatcher/gatherer to constant values
        if not _not_top:
            assert dispatcher is not None
            NetUtils.connect(Const(1), dispatcher.pins["phit_ox_full"])
            NetUtils.connect(Const(0), gatherer.pins["phit_ix_wr"])

        return tuple(branches)

    @classmethod
    def __install_cells(cls, context, chain_width, phit_width):
        # alias
        mvl = ModuleView.design
        mcp = ModuleUtils.create_port
        mis = ModuleUtils.instantiate
        db = context._database

        # register pktchain clasp
        if True:
            mod = Module("pktchain_clasp",
                    is_cell = True,
                    view = mvl,
                    module_class = ModuleClass.prog,
                    chain_width = chain_width,
                    verilog_template = "pktchain_clasp.tmpl.v",
                    verilog_dep_headers = ("pktchain.vh", ))
            # we don't need to create ports for this module.
            db[mvl, "pktchain_clasp"] = mod

        # register pktchain router input fifo
        if True:
            mod = Module("pktchain_frame_assemble",
                    is_cell = True,
                    view = mvl,
                    module_class = ModuleClass.prog,
                    verilog_template = "pktchain_frame_assemble.tmpl.v",
                    verilog_dep_headers = ("pktchain.vh", ))
            # we don't need to create ports for this module.
            # sub-instances (hierarchy-only)
            mis(mod, db[mvl, "prga_fifo"], "fifo")
            mis(mod, db[mvl, "prga_fifo_resizer"], "resizer")
            db[mvl, "pktchain_frame_assemble"] = mod

        # register pktchain router output fifo
        if True:
            mod = Module("pktchain_frame_disassemble",
                    is_cell = True,
                    view = mvl,
                    module_class = ModuleClass.prog,
                    verilog_template = "pktchain_frame_disassemble.tmpl.v",
                    verilog_dep_headers = ("pktchain.vh", ))
            # we don't need to create ports for this module.
            # sub-instances (hierarchy-only)
            mis(mod, db[mvl, "prga_fifo_resizer"], "resizer")
            mis(mod, db[mvl, "prga_fifo"], "fifo")
            mis(mod, db[mvl, "prga_fifo_adapter"], "adapter")
            db[mvl, "pktchain_frame_disassemble"] = mod

        # register pktchain router
        if True:
            mod = Module("pktchain_router",
                    is_cell = True,
                    view = mvl,
                    module_class = ModuleClass.prog,
                    verilog_template = "pktchain_router.tmpl.v",
                    verilog_dep_headers = ("pktchain.vh", ))
            # create ports
            super()._get_or_create_scanchain_prog_nets(mod, chain_width, ["prog_done"])
            mcp(mod, "prog_we_o", 1, PortDirection.output, net_class = NetClass.prog)
            cls._get_or_create_pktchain_fifo_nets(mod, phit_width)

            # sub-instances (hierarchy-only)
            mis(mod, db[mvl, "pktchain_clasp"], "clasp")
            mis(mod, db[mvl, "pktchain_frame_assemble"], "ififo")
            mis(mod, db[mvl, "pktchain_frame_disassemble"], "ofifo")
            db[mvl, "pktchain_router"] = mod

        # register pktchain dispatcher
        if True:
            mod = Module("pktchain_dispatcher",
                    is_cell = True,
                    view = mvl,
                    module_class = ModuleClass.prog,
                    verilog_template = "pktchain_dispatcher.tmpl.v",
                    verilog_dep_headers = ("pktchain.vh", ))
            # create ports
            super()._get_or_create_scanchain_prog_nets(mod, chain_width, ["prog_done", "prog_we", "prog_din", "prog_dout"])
            cls._get_or_create_pktchain_fifo_nets(mod, phit_width, oxy = True)

            # sub-instances (hierarchy-only)
            mis(mod, db[mvl, "pktchain_frame_assemble"], "ififo")
            mis(mod, db[mvl, "pktchain_frame_disassemble"], "ox")
            mis(mod, db[mvl, "pktchain_frame_disassemble"], "oy")
            db[mvl, "pktchain_dispatcher"] = mod

        # register pktchain dispatcher
        if True:
            mod = Module("pktchain_gatherer",
                    is_cell = True,
                    view = mvl,
                    module_class = ModuleClass.prog,
                    verilog_template = "pktchain_gatherer.tmpl.v",
                    verilog_dep_headers = ("pktchain.vh", ))
            # create ports
            super()._get_or_create_scanchain_prog_nets(mod, chain_width, ["prog_done", "prog_we", "prog_din", "prog_dout"])
            cls._get_or_create_pktchain_fifo_nets(mod, phit_width, ixy = True)

            # sub-instances (hierarchy-only)
            mis(mod, db[mvl, "pktchain_frame_assemble"], "ix")
            mis(mod, db[mvl, "pktchain_frame_assemble"], "iy")
            mis(mod, db[mvl, "pktchain_frame_disassemble"], "ofifo")
            db[mvl, "pktchain_gatherer"] = mod

        # register generic programming controller
        if True:
            mod = Module("pktchain_ctrl",
                    is_cell = True,
                    view = mvl,
                    module_class = ModuleClass.aux,
                    verilog_template = "pktchain_ctrl.v",
                    verilog_dep_headers = ("pktchain.vh", ))
            # create ports
            Integration._create_intf_ports_syscon(mod, True)
            ModuleUtils.create_port(mod, "frame_i_rd", 1, "output")
            ModuleUtils.create_port(mod, "frame_i_empty", 1, "input")
            ModuleUtils.create_port(mod, "frame_i", 32, "input")
            ModuleUtils.create_port(mod, "err_resp_inval", 1, "output")
            ModuleUtils.create_port(mod, "err_bitstream_corrupted", 1, "output")
            ModuleUtils.create_port(mod, "err_bitstream_incomplete", 1, "output")
            ModuleUtils.create_port(mod, "err_bitstream_redundant", 1, "output")
            ModuleUtils.create_port(mod, "prog_rst", 1, PortDirection.output)
            ModuleUtils.create_port(mod, "prog_done", 1, PortDirection.output)
            cls._get_or_create_pktchain_fifo_nets(mod, phit_width)

            # sub-instances (hierarchy-only)
            mis(mod, db[mvl, "prga_ram_1r1w_byp"], "prga_ram_1r1w_byp")
            mis(mod, db[mvl, "pktchain_frame_disassemble"], "pktchain_frame_disassemble")
            mis(mod, db[mvl, "pktchain_frame_assemble"], "pktchain_frame_assemble")

            db[mvl, mod.name] = mod

        # register pktchain programming controller backend
        if True:
            mod = Module("prga_be_prog_pktchain",
                    is_cell = True,
                    view = mvl,
                    module_class = ModuleClass.aux,
                    verilog_template = "piton_v0/prga_be_prog_pktchain.tmpl.v",
                    verilog_dep_headers = ("pktchain_system.vh", ))
            # create ports
            Integration._create_intf_ports_syscon(mod, True)
            Integration._create_intf_ports_prog_piton(mod, True)
            ModuleUtils.create_port(mod, "prog_rst", 1, PortDirection.output)
            ModuleUtils.create_port(mod, "prog_done", 1, PortDirection.output)
            cls._get_or_create_pktchain_fifo_nets(mod, phit_width)

            # sub-instances (hierarchy-only)
            mis(mod, db[mvl, "prga_valrdy_buf"], "i_valrdy_buf")
            mis(mod, db[mvl, "prga_fifo"], "i_fifo")
            mis(mod, db[mvl, "prga_fifo_resizer"], "i_fifo_resizer")
            mis(mod, db[mvl, "prga_ram_1r1w_byp"], "i_ram_1r1w")
            mis(mod, db[mvl, "pktchain_frame_disassemble"], "i_frame_disassemble")
            mis(mod, db[mvl, "pktchain_frame_assemble"], "i_frame_assemble")

            db[mvl, "prga_be_prog_pktchain"] = mod

    @classmethod
    def _pktchain_phit_port_name(cls, type_, branch_id = None):
        if branch_id is None:
            return "phit_{}".format(type_)
        else:
            return "phit_{}_b{}".format(type_, branch_id)

    @classmethod
    def _get_or_create_pktchain_fifo_nets(cls, module, phit_width, branch_id = None, ixy = False, oxy = False):
        ports = {}

        # phit_i_wr & phit_o_full
        for type_ in ((("ox_full", "oy_full") if oxy else ("o_full", )) +
                      (("ix_wr", "iy_wr") if ixy else ("i_wr", ))):
            if (port := module.ports.get(name := cls._pktchain_phit_port_name(type_, branch_id))) is None:
                port = ModuleUtils.create_port(module, name, 1, PortDirection.input_,
                        net_class = NetClass.prog)
            ports[type_] = port

        # phit_i
        for type_ in (("ix", "iy") if ixy else ("i", )):
            if (port := module.ports.get(name := cls._pktchain_phit_port_name(type_, branch_id))) is None:
                port = ModuleUtils.create_port(module, name, phit_width, PortDirection.input_,
                        net_class = NetClass.prog)
            ports[type_] = port

        # phit_i_full & phit_o_wr
        for type_ in ((("ox_wr", "oy_wr") if oxy else ("o_wr", )) +
                      (("ix_full", "iy_full") if ixy else ("i_full", ))):
            if (port := module.ports.get(name := cls._pktchain_phit_port_name(type_, branch_id))) is None:
                port = ModuleUtils.create_port(module, name, 1, PortDirection.output,
                        net_class = NetClass.prog)
            ports[type_] = port

        # phit_o
        for type_ in (("ox", "oy") if oxy else ("o", )):
            if (port := module.ports.get(name := cls._pktchain_phit_port_name(type_, branch_id))) is None:
                port = ModuleUtils.create_port(module, name, phit_width, PortDirection.output,
                        net_class = NetClass.prog)
            ports[type_] = port

        return ports

    @classmethod
    def _wrap_pktchain_branch(cls, context, module,
            dispatcher, gatherer, branch_prog_nets, branches, leaves, _not_top):
        if _not_top:
            _logger.debug("Exposing branch No. {} ({} leaves) in {}"
                    .format(len(branches), len(leaves), module))

            phit_width = context.summary.pktchain["fabric"]["phit_width"]
            ports = cls._get_or_create_pktchain_fifo_nets(module, phit_width, len(branches))
            for key in ("i", "i_wr", "o_full"):
                NetUtils.connect(ports[key], branch_prog_nets[key])
            for key in ("o", "o_wr", "i_full"):
                NetUtils.connect(branch_prog_nets[key], ports[key])

        else:
            _logger.debug("Attaching branch No. {} ({} leaves) to the primary chunk"
                    .format(len(branches), len(leaves)))

            # create a new dispatcher
            new_dispatcher = ModuleUtils.instantiate(module,
                    context.database[ModuleView.design, "pktchain_dispatcher"],
                    "i_prog_dispatcher_b{}".format(len(branches)))

            # create a new gatherer
            new_gatherer = ModuleUtils.instantiate(module,
                    context.database[ModuleView.design, "pktchain_gatherer"],
                    "i_prog_gatherer_b{}".format(len(branches)))

            # connect standard programming ports
            prog_nets = cls._get_or_create_scanchain_prog_nets(module, None,
                    ["prog_done", "prog_we", "prog_din", "prog_dout"])
            for port, linst in product( ("prog_clk", "prog_rst"), (new_dispatcher, new_gatherer) ):
                NetUtils.connect(prog_nets[port], linst.pins[port])

            # connect primary chunk ports
            prog_fifo_nets = None
            if dispatcher is None:
                prog_fifo_nets = cls._get_or_create_pktchain_fifo_nets(module,
                        context.summary.pktchain["fabric"]["phit_width"])
            else:
                prog_fifo_nets = {
                        "i":        dispatcher.pins["phit_ox"],
                        "i_wr":     dispatcher.pins["phit_ox_wr"],
                        "i_full":   dispatcher.pins["phit_ox_full"],
                        "o":        gatherer.pins["phit_ix"],
                        "o_wr":     gatherer.pins["phit_ix_wr"],
                        "o_full":   gatherer.pins["phit_ix_full"],
                        }

            NetUtils.connect(prog_fifo_nets["i"],                   new_dispatcher.pins["phit_i"])
            NetUtils.connect(prog_fifo_nets["i_wr"],                new_dispatcher.pins["phit_i_wr"])
            NetUtils.connect(new_dispatcher.pins["phit_i_full"],    prog_fifo_nets["i_full"])
            NetUtils.connect(prog_fifo_nets["o_full"],              new_gatherer.pins["phit_o_full"])
            NetUtils.connect(new_gatherer.pins["phit_o"],           prog_fifo_nets["o"])
            NetUtils.connect(new_gatherer.pins["phit_o_wr"],        prog_fifo_nets["o_wr"])

            # connect branch ports
            NetUtils.connect(new_dispatcher.pins["phit_oy"],        branch_prog_nets["i"])
            NetUtils.connect(new_dispatcher.pins["phit_oy_wr"],     branch_prog_nets["i_wr"])
            NetUtils.connect(branch_prog_nets["i_full"],            new_dispatcher.pins["phit_oy_full"])
            NetUtils.connect(new_gatherer.pins["phit_iy_full"],     branch_prog_nets["o_full"])
            NetUtils.connect(branch_prog_nets["o"],                 new_gatherer.pins["phit_iy"])
            NetUtils.connect(branch_prog_nets["o_wr"],              new_gatherer.pins["phit_iy_wr"])

            dispatcher, gatherer = new_dispatcher, new_gatherer

        branches.append( tuple(leaves) )
        leaves.clear()
        branch_prog_nets.clear()

        return dispatcher, gatherer

    @classmethod
    def _connect_pktchain_leaf(cls, context, module, instance, leaf_prog_nets):

        chain_width = context.summary.scanchain["chain_width"]

        # connect programming nets
        # standard protocol
        if "prog_clk" not in leaf_prog_nets:
            leaf_prog_nets.update(cls._get_or_create_scanchain_prog_nets(module, chain_width,
                ["prog_we", "prog_din", "prog_dout"]))
        for key in ("prog_clk", "prog_rst", "prog_done"):
            if (src := NetUtils.get_source(instance.pins[key])) is None:
                NetUtils.connect(leaf_prog_nets[key], instance.pins[key])
        # chain enable
        if (prog_we_o := leaf_prog_nets.get("prog_we_o")) is None:
            leaf_prog_nets.setdefault("prog_we", []).append(instance.pins["prog_we"])
        else:
            NetUtils.connect(prog_we_o, instance.pins["prog_we"])
        if (prog_we_o := instance.pins.get("prog_we_o")) is not None:
            leaf_prog_nets["prog_we_o"] = prog_we_o
        # chain data
        if (prog_dout := leaf_prog_nets.get("prog_dout")) is None:
            leaf_prog_nets["prog_din"] = instance.pins["prog_din"]
        else:
            NetUtils.connect(prog_dout, instance.pins["prog_din"])
        leaf_prog_nets["prog_dout"] = instance.pins["prog_dout"]

    @classmethod
    def _insert_pktchain_leaf(cls, context, module, instance, iter_instances, insert_delimiter,
            leaf_prog_nets, scanchain_offset, branch_id, leaf_id):

        chain_width = context.summary.scanchain["chain_width"]
        _logger.debug("Inserting scanchain to {}".format(instance))

        # check if `instance` requires programming data
        ichain, bitcount = instance, 0
        if (prog_data := instance.pins.get("prog_data")) is None:
            if (bitcount := getattr(instance.model, "scanchain_bitcount", None)) is None:
                bitcount = cls._insert_scanchain(context, instance.model,
                        iter_instances = iter_instances, insert_delimiter = insert_delimiter)
            if bitcount == 0:
                return 0
        else:
            ichain = ModuleUtils.instantiate(module,
                    cls._get_or_create_scanchain_data_cell(context, len(prog_data)),
                    "i_prog_data_{}".format(instance.name))
            NetUtils.connect(ichain.pins["prog_data"], prog_data)
            bitcount = len(prog_data)

        # connect programming nets
        cls._connect_pktchain_leaf(context, module, ichain, leaf_prog_nets)

        # update
        instance.scanchain_bitmap = ProgDataBitmap( (scanchain_offset, bitcount) )
        instance.pktchain_branchmap = (branch_id, leaf_id),     # trailing comma converts this to a tuple

        if (uinst := context.database[ModuleView.abstract, module.key].instances.get(instance.key)) is not None:
            uinst.scanchain_bitmap = instance.scanchain_bitmap
            uinst.pktchain_branchmap = instance.pktchain_branchmap

        return bitcount

    @classmethod
    def _wrap_pktchain_leaf(cls, context, module, branch_id,
            branch_prog_nets, leaves, leaf_prog_nets, scanchain_bitcount):
        _logger.debug("Wrapping leaf No. {} on branch No. {} in {}"
                .format(len(leaves), branch_id, module))

        # instantiate router
        router = ModuleUtils.instantiate(module,
                context.database[ModuleView.design, "pktchain_router"],
                "i_prog_router_b{}l{}".format(branch_id, len(leaves)))

        # connect standard programming ports
        prog_nets = cls._get_or_create_scanchain_prog_nets(module, None,
                ["prog_done", "prog_we", "prog_din", "prog_dout"])
        for port in ("prog_clk", "prog_rst"):
            NetUtils.connect(prog_nets[port], router.pins[port])

        # connect scanchain to router
        if prog_dout := leaf_prog_nets.get("prog_dout"):
            NetUtils.connect(prog_dout, router.pins["prog_din"])
            NetUtils.connect(router.pins["prog_dout"], leaf_prog_nets["prog_din"])
        else:
            NetUtils.connect(router.pins["prog_dout"], router.pins["prog_din"])

        NetUtils.connect(leaf_prog_nets.get("prog_we_o", router.pins["prog_we_o"]), router.pins["prog_we"])
        for pin in leaf_prog_nets.get("prog_we", []):
            NetUtils.connect(router.pins["prog_we_o"], pin)

        # connect router to branch
        if "o" in branch_prog_nets:
            NetUtils.connect(branch_prog_nets["o"],         router.pins["phit_i"])
            NetUtils.connect(branch_prog_nets["o_wr"],      router.pins["phit_i_wr"])
            NetUtils.connect(router.pins["phit_i_full"],    branch_prog_nets["o_full"])
        else:
            branch_prog_nets.update(
                    **{k: router.pins["phit_" + k] for k in ("i", "i_wr", "i_full")})
        branch_prog_nets.update(
                **{k: router.pins["phit_" + k] for k in ("o", "o_wr", "o_full")})

        # update chain settings
        _logger.debug("Wrapping up leaf ({} bits) to router No. {} of branch No. {} in {}"
                .format(scanchain_bitcount, len(leaves), branch_id, module))
        leaves.append( scanchain_bitcount )
        leaf_prog_nets.clear()

    class BuildSystemPitonVanilla(AbstractPass):
        """Create a system for SoC integration, specifically for OpenPiton vanilla."""

        __slots__ = ["io_constraints_f", "name", "fabric_wrapper", "prog_be_in_wrapper"]

        def __init__(self, io_constraints_f = "io.pads", *,
                name = "prga_system", fabric_wrapper = None, prog_be_in_wrapper = False):

            if prog_be_in_wrapper and fabric_wrapper is None:
                raise PRGAAPIError("`fabric_wrapper` must be set when `prog_be_in_wrapper` is set")

            self.io_constraints_f = io_constraints_f
            self.name = name
            self.fabric_wrapper = fabric_wrapper
            self.prog_be_in_wrapper = prog_be_in_wrapper
            
        def run(self, context):
            renderer = context.renderer

            # build system
            Integration.build_system_piton_vanilla(context,
                    name = self.name, fabric_wrapper = self.fabric_wrapper)

            # get system module
            system = context.system_top

            # which backend should we connect?
            syscomplex_slave, syscomplex_prefix = None, ""
            prog_inst, prog_slave = None, None

            # check fabric wrapper
            if self.fabric_wrapper and self.prog_be_in_wrapper:
                core = system.instances["i_core"]
                fabric = core.model.instances["i_fabric"]

                syscomplex_slave, syscomplex_prefix, prog_slave = core, "prog_", fabric

                # create prog ports
                core_ports = Integration._create_intf_ports_syscon(core.model, True, "prog_")
                core_ports.update(Integration._create_intf_ports_prog_piton(core.model, True, syscomplex_prefix))

                # instantiate
                prog_inst = ModuleUtils.instantiate(core.model,
                        context.database[ModuleView.design, "prga_be_prog_pktchain"],
                        "i_prog_be")

                # connect prog backend with core ports
                for port_name, port in core_ports.items():
                    if port.direction.is_input:
                        NetUtils.connect(port, prog_inst.pins[port_name[5:]])
                    else:
                        NetUtils.connect(prog_inst.pins[port_name[5:]], port)

                # connect prog backend with fabric
                NetUtils.connect(core_ports["prog_clk"], fabric.pins["prog_clk"])

            else:
                if self.fabric_wrapper:
                    prog_slave = core = system.instances["i_core"]
                    fabric = core.model.instances["i_fabric"]

                    # expose fabric programming ports out of core
                    NetUtils.connect(
                            ModuleUtils.create_port(core.model, "prog_clk", 1, PortDirection.input_, is_clock = True),
                            fabric.pins["prog_clk"])
                    NetUtils.connect(system.ports["clk"], core.pins["prog_clk"])

                    for pin_name in ["prog_rst", "prog_done", "phit_o_full", "phit_i_wr", "phit_i"]:
                        pin = fabric.pins[pin_name]
                        NetUtils.connect(
                                ModuleUtils.create_port(core.model, pin_name, len(pin), PortDirection.input_),
                                pin)

                    for pin_name in ["phit_i_full", "phit_o_wr", "phit_o"]:
                        NetUtils.connect( (pin := fabric.pins[pin_name]),
                                ModuleUtils.create_port(core.model, pin_name, len(pin), PortDirection.input_))
                else:
                    prog_slave = system.instances["i_fabric"]
                    NetUtils.connect(system.ports["clk"], prog_slave.pins["prog_clk"])

                # instantiate
                syscomplex_slave = prog_inst = ModuleUtils.instantiate(system,
                        context.database[ModuleView.design, "prga_be_prog_pktchain"],
                        "i_prog_be")

            # connect programming backend with its slave
            NetUtils.connect(prog_inst.pins ["prog_rst"],       prog_slave.pins["prog_rst"])
            NetUtils.connect(prog_inst.pins ["prog_done"],      prog_slave.pins["prog_done"])
            NetUtils.connect(prog_inst.pins ["phit_i_full"],    prog_slave.pins["phit_o_full"])
            NetUtils.connect(prog_slave.pins["phit_o_wr"],      prog_inst.pins ["phit_i_wr"])
            NetUtils.connect(prog_slave.pins["phit_o"],         prog_inst.pins ["phit_i"])
            NetUtils.connect(prog_slave.pins["phit_i_full"],    prog_inst.pins ["phit_o_full"])
            NetUtils.connect(prog_inst.pins ["phit_o_wr"],      prog_slave.pins["phit_i_wr"])
            NetUtils.connect(prog_inst.pins ["phit_o"],         prog_slave.pins["phit_i"])

            # connect syscomplex with its slave
            syscomplex = system.instances["i_syscomplex"]
            NetUtils.connect(system.ports["clk"], syscomplex_slave.pins[syscomplex_prefix + "clk"])
            for pin_name in ["rst_n", "req_val", "req_addr", "req_strb", "req_data", "resp_rdy"]:
                NetUtils.connect(syscomplex.pins["prog_" + pin_name],
                        syscomplex_slave.pins[syscomplex_prefix + pin_name])
            for pin_name in ["status", "req_rdy", "resp_val", "resp_err", "resp_data"]:
                NetUtils.connect(syscomplex_slave.pins[syscomplex_prefix + pin_name],
                        syscomplex.pins["prog_" + pin_name])

            # print IO constraints
            IOPlanner.print_io_constraints(context.summary.integration["app_intf"], self.io_constraints_f)

        @property
        def key(self):
            return "system.pktchain.piton_vanilla"

        @property
        def dependences(self):
            return ("vpr", )

        @property
        def passes_after_self(self):
            return ("rtl", )

    class BuildSystemRXIYAMI(AbstractPass):
        """Create a system for SoC integration, using RXI/YAMI interfaces."""

        __slots__ = ["io_constraints_f", "name", "fabric_wrapper", "prog_be_in_wrapper",
                "rxi", "yami", "use_fake_clkgen"]

        def __init__(self, io_constraints_f = "io.pads", *,
                name = "prga_system", piton = False,
                fabric_wrapper = None, prog_be_in_wrapper = False,

                rxi_addr_width = 12, rxi_data_bytes_log2 = 3, num_yami = 1,

                yami_fmc_addr_width = 40, yami_fmc_data_bytes_log2 = 3,
                yami_mfc_addr_width = 16, yami_mfc_data_bytes_log2 = 4,
                yami_cacheline_bytes_log2 = 4,
                
                use_fake_clkgen = False,
                ):

            if prog_be_in_wrapper and fabric_wrapper is None:
                raise PRGAAPIError("`fabric_wrapper` must be set when `prog_be_in_wrapper` is set")

            self.io_constraints_f = io_constraints_f
            self.name = name
            self.fabric_wrapper = fabric_wrapper
            self.prog_be_in_wrapper = prog_be_in_wrapper

            self.rxi = SystemIntf.rxi(None, rxi_addr_width, rxi_data_bytes_log2, num_yami)

            if piton:
                self.yami = SystemIntf.yami_piton
            else:
                self.yami = SystemIntf.yami(None,
                        yami_fmc_addr_width,
                        yami_fmc_data_bytes_log2,
                        yami_mfc_addr_width,
                        yami_mfc_data_bytes_log2,
                        yami_cacheline_bytes_log2)

            self.use_fake_clkgen = use_fake_clkgen

        @property
        def key(self):
            return "system.pktchain.rxi_yami"

        @property
        def passes_after_self(self):
            return ("rtl", )

        def run(self, context):
            renderer = context.renderer

            # build system
            IntegrationRXIYAMI.build_system(context, self.rxi, self.yami,
                    name                        = self.name,
                    fabric_wrapper              = self.fabric_wrapper,
                    use_fake_clkgen             = self.use_fake_clkgen,
                    )

            # get system top module
            system = context.system_top

            # register prog_be header and module
            context.add_verilog_header("prga_rxi_pktchain.vh", "rxi/include/prga_rxi_pktchain.vh",
                    "prga_rxi.vh", "pktchain.vh")

            # create module
            m_be = context._add_module(Module("prga_rxi_be_prog_pktchain",
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "rxi/prga_rxi_be_prog_pktchain.tmpl.v",
                verilog_dep_headers = ("prga_rxi.vh", "prga_rxi_pktchain.vh")))

            # create ports
            IntegrationRXIYAMI._create_ports_syscon(m_be, slave = True)
            IntegrationRXIYAMI._create_ports_rxi(m_be, slave = True, prog = True, fabric = True,
                    prefix = "prog_", addr_width = 4, data_bytes_log2 = self.rxi.data_bytes_log2)
            Pktchain._get_or_create_pktchain_fifo_nets(m_be, context.summary.pktchain["fabric"]["phit_width"])

            # instantiate sub-instances
            for sub in ("prga_valrdy_buf", "prga_fifo", "prga_fifo_resizer", "pktchain_ctrl"):
                ModuleUtils.instantiate(m_be, context.database[ModuleView.design, sub], sub)

            rxi_slave = None
            prog_master, prog_slave = None, None

            # instantiate and connect
            if self.fabric_wrapper and self.prog_be_in_wrapper:
                core = rxi_slave = system.instances["i_core"]               # fabric wrapper
                fabric = prog_slave = core.model.instances["i_fabric"]      # fabric instance
                i_be = prog_master = ModuleUtils.instantiate(core.model, m_be, "i_be")

                # create programming ports in the wrapper
                core_ports = IntegrationRXIYAMI._create_ports_syscon(core.model, slave = True)
                core_ports.update(IntegrationRXIYAMI._create_ports_rxi(core.model, slave = True, prog = True,
                    prefix = "prog_", addr_width = 4, data_bytes_log2 = self.rxi.data_bytes_log2))

                # connect
                for name, port in core_ports.items():
                    if name in ("clk", "rst_n"):
                        NetUtils.connect(port, i_be.pins[name])
                    elif port.direction.is_input:
                        NetUtils.connect(port, i_be.pins["prog_" + name])
                    else:
                        NetUtils.connect(i_be.pins["prog_" + name], port)

                # ... and more connect!
                NetUtils.connect(system.ports["clk"], core.pins["clk"])
                NetUtils.connect(core_ports["clk"], fabric.pins["prog_clk"])

            elif self.fabric_wrapper:
                # instantiate backend
                i_be = rxi_slave = prog_master = ModuleUtils.instantiate(system, m_be, "i_be")
                core = prog_slave = system.instances["i_core"]
                fabric = core.model.instances["i_fabric"]

                # create pktchain ports
                ModuleUtils.create_port(core.model, "prog_clk",  1, "input", is_clock = True)
                ModuleUtils.create_port(core.model, "prog_rst",  1, "input")
                ModuleUtils.create_port(core.model, "prog_done", 1, "output")
                core_ports = Pktchain._get_or_create_pktchain_fifo_nets(core.model,
                        context.summary.pktchain["fabric"]["phit_width"])

                # connect
                NetUtils.connect(core.model.ports["prog_clk"],  fabric.pins["prog_clk"])
                NetUtils.connect(core.model.ports["prog_rst"],  fabric.pins["prog_rst"])
                NetUtils.connect(core.model.ports["prog_done"], fabric.pins["prog_done"])
                for name, port in core_ports.items():
                    if port.direction.is_input:
                        NetUtils.connect(port, fabric.pins["phit_" + name])
                    else:
                        NetUtils.connect(fabric.pins["phit_" + name], port)

                # ... and more connect!
                NetUtils.connect(system.ports["clk"], i_be.pins["clk"])
                NetUtils.connect(system.ports["clk"], core.pins["prog_clk"])

            else:
                rxi_slave = prog_master = ModuleUtils.instantiate(system, m_be, "i_be")
                prog_slave = system.instances["i_fabric"]

                # connect clocks
                NetUtils.connect(system.ports["clk"], rxi_slave.pins["clk"])
                NetUtils.connect(system.ports["clk"], prog_slave.pins["prog_clk"])

            # connect rxi master to rxi slave
            i_rxi = system.instances["i_rxi"]
            NetUtils.connect(i_rxi.pins["prog_rst_n"],          rxi_slave.pins["rst_n"])
            for name, pin in i_rxi.pins.items():
                if name.startswith("prog_") and name != "prog_rst_n":
                    if pin.model.direction.is_input:
                        NetUtils.connect(rxi_slave.pins[name], pin)
                    else:
                        NetUtils.connect(pin, rxi_slave.pins[name])

            # connect prog master to prog slave
            NetUtils.connect(prog_master.pins["prog_rst"],      prog_slave.pins["prog_rst"])
            NetUtils.connect(prog_master.pins["prog_done"],     prog_slave.pins["prog_done"])
            NetUtils.connect(prog_slave.pins["phit_o_wr"],      prog_master.pins["phit_i_wr"])
            NetUtils.connect(prog_slave.pins["phit_o"],         prog_master.pins["phit_i"])
            NetUtils.connect(prog_slave.pins["phit_i_full"],    prog_master.pins["phit_o_full"])
            NetUtils.connect(prog_master.pins["phit_o_wr"],     prog_slave.pins["phit_i_wr"])
            NetUtils.connect(prog_master.pins["phit_o"],        prog_slave.pins["phit_i"])
            NetUtils.connect(prog_master.pins["phit_i_full"],   prog_slave.pins["phit_o_full"])

            # print IO constraints
            IOPlanner.print_io_constraints(context.summary.integration["app_intf"], self.io_constraints_f)
