# -*- encoding: ascii -*-

from .protocol import FrameProtocol
from ..common import AbstractProgCircuitryEntry, ProgDataBitmap
from ...core.common import NetClass, ModuleClass, ModuleView, Corner, Orientation, Dimension
from ...netlist import Module, ModuleUtils, PortDirection, NetUtils, Const
from ...passes.translation import SwitchDelegate
from ...renderer.lib import BuiltinCellLibrary
from ...util import uno, Object
from ...exception import PRGAInternalError

import os, logging
from itertools import chain, product, count
from copy import copy

_logger = logging.getLogger(__name__)

__all__ = ["Frame"]

# ----------------------------------------------------------------------------
# -- Frame Programming Circuitry Main Entry ----------------------------------
# ----------------------------------------------------------------------------
class Frame(AbstractProgCircuitryEntry):
    """Entry point for frame programming circuitry."""

    class _FrameDecoderTreeLeaf(Object):

        __slots__ = ['instance']
        def __init__(self, instance):
            self.instance = instance

        @property
        def addr_width(self):
            return len(p) if (p := self.instance.pins.get("prog_addr")) else 0
        
        @property
        def is_leaf(self):
            return True

    class _FrameDecoderTreeNode(Object):

        __slots__ = ["children", "child_addr_width", "parent"]
        def __init__(self, first_child, parent = None):
            self.children = [first_child]
            self.child_addr_width = first_child.addr_width
            self.parent = parent

        @property
        def addr_width(self):
            return self.child_addr_width + (len(self.children) - 1).bit_length()

        @property
        def is_leaf(self):
            return False

        def add_node(self, node):
            if node.addr_width > self.child_addr_width:
                return False

            if node.addr_width < self.child_addr_width:
                # check if any of my children is able to accomodate this node
                for child in self.children:
                    if not child.is_leaf and child.add_node(node):
                        return True

            # none of my children is able to accomodate this node. what about myself?
            if (self.parent is None # well I'm the root, I can do whatever I want. Yoooo!
                                    # or.. I have enough space left at my expense
                    or len(self.children) < 2 ** (self.parent.child_addr_width - self.child_addr_width)):

                if node.is_leaf and node.addr_width < self.child_addr_width:
                    self.children.append(type(self)(node, self))
                else:
                    self.children.append(node)

                return True
            
            return False

    @classmethod
    def materialize(cls, ctx, inplace = False, *, word_width = 1):

        ctx = super().materialize(ctx, inplace = inplace)
        ctx._switch_delegate = SwitchDelegate(ctx)

        BuiltinCellLibrary.install_stdlib(ctx)

        ctx.summary.frame = {
                "word_width": word_width,
                "protocol": FrameProtocol,
                }
        ctx.summary.prog_support_magic_checker = True
        ctx.template_search_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
        ctx.add_verilog_header("prga_frame.vh", "include/prga_frame.tmpl.vh")
        ctx.renderer = None

        cls.__install_cells(ctx)
        BuiltinCellLibrary.install_design(ctx)

        return ctx

    @classmethod
    def insert_prog_circuitry(cls, context):
        dtop = context.database[ModuleView.design, context.top.key]
        if "prga_frame.vh" not in (deps := getattr(dtop, "verilog_dep_headers", tuple())):
            dtop.verilog_dep_headers = deps + ("prga_frame.vh", )

        # distribute programming clock, buffer programming reset and done
        cls.buffer_prog_ctrl(context)

        # insert configuration circuitry into all blocks and routing boxes
        maxes = cls._traverse_and_insert_leaves(context)
        max_blk_aw, max_num_blk, max_cbox_aw, max_num_cbox, max_sbox_aw = maxes

        # build hierarchical address mapping
        # subblock_id width
        subblock_id_width = (max_num_blk - 1).bit_length()

        # cbox_id width
        cbox_id_width = (max_num_cbox - 1).bit_length()

        # sbox_id width (constant 2 for 4 corners)
        sbox_id_width = 2

        # tile address width
        tile_aw = max(
                1 + sbox_id_width + max_sbox_aw,    # 1'b0, corner,  sbox_addr
                2 + subblock_id_width + max_blk_aw, # 2'b10, subblock_id, blk_addr
                2 + cbox_id_width + max_cbox_aw,    # 2'b11, cbox_id, cbox_addr
                )

        # top-level array
        x_width = (context.top.width - 1).bit_length()
        y_width = (context.top.height - 1).bit_length()

        # final address mapping
        context.summary.frame["addr_width"] = {
                "fabric":       x_width + y_width + tile_aw,
                "x":            x_width,
                "y":            y_width,

                "block":        tile_aw - 2 - subblock_id_width,
                "cbox":         tile_aw - 2 - cbox_id_width,
                "sbox":         tile_aw - 1 - sbox_id_width,
                "tile":         tile_aw,

                "subblock_id":  subblock_id_width,
                "cbox_id":      cbox_id_width,
                "sbox_id":      sbox_id_width,
                }

        _logger.info((
                "Address mapping:\n"
                " - fabric:      {fabric}\n"
                " - x:           {x}\n"
                " - y:           {y}\n"
                " - block:       {block}\n"
                " - cbox:        {cbox}\n"
                " - sbox:        {sbox}\n"
                " - tile:        {tile}\n"
                " - subblock_id: {subblock_id}\n"
                " - cbox_id:     {cbox_id}\n"
                " - sbox_id:     {sbox_id}"
                ).format(**context.summary.frame["addr_width"]))

        cls._insert_frame_array(context)

    @classmethod
    def __install_cells(cls, context):
        # install `prga_frame_and`
        cell = context._add_module(Module("prga_frame_and",
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.prog,
            verilog_template = "prga_frame_and.v"))
        ModuleUtils.create_port(cell, "ix", 1, "input",  net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "iy", 1, "input",  net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "o",  1, "output", net_class = NetClass.prog)

        # create design views for 1r1w_init memories
        word_width = context.summary.frame["word_width"]
        for abstract in list(context.primitives.values()):  # snapshot
            if (abstract.primitive_class.is_multimode
                    and getattr(abstract, "memory_type", None) == "1r1w_init"):
                lbdr = context.build_design_view_primitive(abstract.name,
                        key = abstract.key,
                        verilog_template = "1r1w.init.sim.tmpl.v",
                        verilog_dep_headers = ("prga_utils.vh", ))
                lbdr.instantiate(
                        context.database[ModuleView.design, "prga_ram_1r1w_byp"],
                        "i_ram")

                dwidth = len(abstract.ports["din"])
                num_slices = dwidth // word_width + (1 if dwidth % word_width > 0 else 0)
                diff_addr_width = (num_slices - 1).bit_length()

                cls._get_or_create_frame_prog_nets(lbdr.module, word_width,
                        len(abstract.ports["waddr"]) + diff_addr_width)

                abstract.modes["init"].instances["i_ram"].prog_parameters = {
                        "INIT": ProgDataBitmap(
                            (i * word_width << diff_addr_width, dwidth)
                            for i in range(1 << len(abstract.ports["waddr"]))
                            ),
                        }
                abstract.modes["init"].instances["i_ram"].prog_magic_ignore = True

                lbdr.commit()

    @classmethod
    def _get_or_create_frame_prog_nets(cls, module, word_width, addr_width, excludes = None):
        excludes = set(uno(excludes, []))
        nets = cls._get_or_create_prog_nets(module)

        # prog_ce and prog_we
        for key in ("prog_ce", "prog_we"):
            if key not in excludes:
                if (port := module.ports.get(key)) is None:
                    port = ModuleUtils.create_port(module, key, 1, PortDirection.input_,
                            net_class = NetClass.prog)
                nets[key] = port

        # prog_addr
        if "prog_addr" not in excludes and addr_width > 0:
            if (port := module.ports.get("prog_addr")) is None:
                port = ModuleUtils.create_port(module, "prog_addr", addr_width, PortDirection.input_,
                        net_class = NetClass.prog)
            nets["prog_addr"] = port

        # prog_din and prog_dout
        for key, direction in zip(("prog_din", "prog_dout"), PortDirection):
            if key not in excludes:
                if (port := module.ports.get(key)) is None:
                    port = ModuleUtils.create_port(module, key, word_width, direction,
                            net_class = NetClass.prog)
                nets[key] = port
        
        return nets

    @classmethod
    def _get_or_create_frame_data_cell(cls, context, data_width):
        name = "prga_frame_sramdata_d{}".format(data_width)
        if cell := context.database.get( (ModuleView.design, name) ):
            return cell

        word_width = context.summary.frame["word_width"]
        word_count = data_width // word_width + (1 if data_width % word_width > 0 else 0);
        addr_width = (word_count - 1).bit_length();

        tmpl = "prga_frame_sramdata_singleword.tmpl.v" if addr_width == 0 else "prga_frame_sramdata.tmpl.v"
        cell = context._add_module(Module(name,
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.prog,
            verilog_template = tmpl))
        cls._get_or_create_frame_prog_nets(cell, word_width, addr_width)
        ModuleUtils.create_port(cell, "prog_data_o", data_width, PortDirection.output, net_class = NetClass.prog)

        return cell

    @classmethod
    def _get_or_create_frame_buffer(cls, context, data_width):
        name = "prga_frame_buf_d{}".format(data_width)
        if cell := context.database.get( (ModuleView.design, name) ):
            return cell

        cell = context._add_module(Module(name,
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.prog,
            verilog_template = "prga_frame_buf.tmpl.v"))
        cls._get_or_create_prog_nets(cell, excludes = ["prog_done"])
        ModuleUtils.create_port(cell, "i", data_width, PortDirection.input_, net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "o", data_width, PortDirection.output, net_class = NetClass.prog)

        return cell

    @classmethod
    def _get_or_create_frame_wldec(cls, context, addr_width, num_sinks):
        name = "prga_frame_wldec_n{}a{}".format(num_sinks, addr_width)
        if cell := context.database.get( (ModuleView.design, name) ):
            return cell

        cell = context._add_module(Module(name,
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.prog,
            verilog_template = "prga_frame_wldec.tmpl.v"))
        ModuleUtils.create_port(cell, "ce_i",   1,          PortDirection.input_, net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "we_i",   1,          PortDirection.input_, net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "addr_i", addr_width, PortDirection.input_, net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "ce_o",   num_sinks,  PortDirection.output, net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "we_o",   num_sinks,  PortDirection.output, net_class = NetClass.prog)

        return cell

    @classmethod
    def _get_or_create_frame_rbmerge(cls, context, num_sources, num_stages):
        name = "prga_frame_rbmerge_n{}s{}".format(num_sources, num_stages)
        if cell := context.database.get( (ModuleView.design, name) ):
            return cell

        word_width = context.summary.frame["word_width"]
        cell = context._add_module(Module(name,
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.prog,
            num_stages = num_stages,
            verilog_template = "prga_frame_rbmerge.tmpl.v"))
        cls._get_or_create_prog_nets(cell, excludes = ["prog_done"])
        ModuleUtils.create_port(cell, "dout", word_width,  PortDirection.output, net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "ce",   num_sources, PortDirection.input_, net_class = NetClass.prog)
        for i in range(num_sources):
            ModuleUtils.create_port(cell, "din"+str(i), word_width, PortDirection.input_, net_class = NetClass.prog)

        return cell

    @classmethod
    def _instantiate_buffer(cls, context, module, nets, addr_width, *,
            suffix = ""):
        word_width = context.summary.frame["word_width"]

        # buffer write request
        ibuf = ModuleUtils.instantiate(module,
                cls._get_or_create_frame_buffer(context, addr_width + word_width + 2),
                "i_frame_ibuf" + suffix)

        NetUtils.connect(nets["prog_clk"], ibuf.pins["prog_clk"])
        NetUtils.connect(nets["prog_rst"], ibuf.pins["prog_rst"])

        if addr_width > 0:
            NetUtils.connect(
                    [nets["prog_ce"], nets["prog_we"], nets["prog_addr"], nets["prog_din"]],
                    ibuf.pins["i"])
            nets["prog_addr"] = ibuf.pins["o"][2:2+addr_width]
        else:
            NetUtils.connect(
                    [nets["prog_ce"], nets["prog_we"], nets["prog_din"]],
                    ibuf.pins["i"])

        nets["prog_ce"]   = ibuf.pins["o"][0]
        nets["prog_we"]   = ibuf.pins["o"][1]
        nets["prog_din"]  = ibuf.pins["o"][2+addr_width:]

        # buffer read-back response
        obuf = ModuleUtils.instantiate(module,
                cls._get_or_create_frame_buffer(context, word_width),
                "i_frame_obuf" + suffix)

        NetUtils.connect(nets["prog_clk"], obuf.pins["prog_clk"])
        NetUtils.connect(nets["prog_rst"], obuf.pins["prog_rst"])

        if n := nets.get("prog_dout"):
            NetUtils.connect(obuf.pins["o"], n)

        nets["prog_dout"] = obuf.pins["i"]

    @classmethod
    def _instantiate_decoder(cls, context, module, nets, subnets, addrnet, *,
            suffix = "", merger_stage = 1, dont_connect_subnets = False):

        decoder = ModuleUtils.instantiate(module,
                cls._get_or_create_frame_wldec(context, len(addrnet), len(subnets)),
                "i_frame_wldec" + suffix)
        merger = ModuleUtils.instantiate(module,
                cls._get_or_create_frame_rbmerge(context, len(subnets), merger_stage),
                "i_frame_rbmerger" + suffix)

        for i, subnet in enumerate(subnets):
            if "prog_ce" in subnet:
                NetUtils.connect(decoder.pins["ce_o"][i], subnet["prog_ce"])
                NetUtils.connect(decoder.pins["we_o"][i], subnet["prog_we"])
                NetUtils.connect(subnet["prog_dout"], merger.pins["din" + str(i)])

                if not dont_connect_subnets and (p := subnet.get("prog_addr")):
                    NetUtils.connect(nets["prog_addr"][:len(p)], p)

                if not dont_connect_subnets and (p := subnet.get("prog_din")):
                    NetUtils.connect(nets["prog_din"], p)

            else:
                NetUtils.connect(Const(0, len(merger.pins["dout"])), merger.pins["din" + str(i)])

        NetUtils.connect(addrnet, decoder.pins["addr_i"])
        NetUtils.connect(decoder.pins["ce_o"], merger.pins["ce"])
        NetUtils.connect(nets["prog_clk"], merger.pins["prog_clk"])
        NetUtils.connect(nets["prog_rst"], merger.pins["prog_rst"])

        return {"prog_we":   decoder.pins["we_i"],
                "prog_ce":   decoder.pins["ce_i"],
                "prog_dout": merger.pins["dout"]
                }

    @classmethod
    def _construct_decoder_tree(cls, context, module, nets, node, *,
            _treenets = None, baseaddr = 0):

        word_width = context.summary.frame["word_width"]
        amod = context.database[ModuleView.abstract, module.key]
        _treenets = uno(_treenets, [])

        # leaf node
        if node.is_leaf:
            if ((prog_clk := node.instance.pins.get("prog_clk"))
                    and NetUtils.get_source(prog_clk) is None):
                NetUtils.connect(nets["prog_clk"],  node.instance.pins["prog_clk"])
                NetUtils.connect(nets["prog_rst"],  node.instance.pins["prog_rst"])
                NetUtils.connect(nets["prog_done"], node.instance.pins["prog_done"])

            if prog_addr := node.instance.pins.get("prog_addr"):
                NetUtils.connect(nets["prog_addr"][:len(prog_addr)], prog_addr)
            NetUtils.connect(nets["prog_din"], node.instance.pins["prog_din"])

            node.instance.frame_baseaddr = baseaddr
            if ainst := amod.instances.get(node.instance.key):
                ainst.frame_baseaddr = node.instance.frame_baseaddr

            return node.instance.pins

        # non-leaf node
        addr_width = node.addr_width if node.parent is None else node.parent.child_addr_width

        if addr_width > node.child_addr_width:

            subnets = [cls._construct_decoder_tree(context, module, nets, child,
                _treenets = _treenets, baseaddr = baseaddr + (i << node.child_addr_width))
                for i, child in enumerate(node.children)]

            treenet = cls._instantiate_decoder( context, module, nets, subnets,
                    nets["prog_addr"][node.child_addr_width:addr_width],
                    suffix = "_i{}".format(len(_treenets)),
                    dont_connect_subnets = True,
                    )

            _treenets.append(treenet)
            return treenet

        else:
            return cls._construct_decoder_tree(context, module, nets, node.children[0],
                    _treenets = _treenets, baseaddr = baseaddr)

    @classmethod
    def _traverse_and_insert_leaves(cls, context, *, dmod = None, _visited = None):
        _visited = uno(_visited, set())

        dmod = uno(dmod, context.database[ModuleView.design, context.top.key])
        _visited.add(dmod.key)

        if dmod.module_class.is_array:
            maxes = tuple(0 for _ in range(5))

            for (x, y) in product(range(dmod.width), range(dmod.height)):
                if (dinst := dmod.instances.get( (x, y) )) and dinst.model.key not in _visited:
                    this_maxes = cls._traverse_and_insert_leaves(context,
                            dmod = dinst.model, _visited = _visited)
                    maxes = tuple(map(max, zip(maxes, this_maxes)))

                for corner in Corner:
                    if (dinst := dmod.instances.get( ((x, y), corner) )) and dinst.model.key not in _visited:
                        sbox_aw = cls._insert_frame_leaf(context, dinst.model, _visited)
                        maxes = maxes[:4] + (max(maxes[4], sbox_aw), )

            return maxes

        else:
            max_blk_aw, num_blk, max_cbox_aw, num_cbox = (0, ) * 4

            assert dmod.module_class.is_tile
            for k, dinst in dmod.instances.items():
                if dinst.model.module_class.is_block:
                    num_blk += 1

                    if dinst.model.key not in _visited:
                        max_blk_aw = max(max_blk_aw,
                                cls._insert_frame_leaf(context, dinst.model, _visited))

                elif dinst.model.module_class.is_connection_box:
                    num_cbox += 1

                    if dinst.model.key not in _visited:
                        max_cbox_aw = max(max_cbox_aw,
                                cls._insert_frame_leaf(context, dinst.model, _visited))

            return max_blk_aw, num_blk, max_cbox_aw, num_cbox, 0

    @classmethod
    def _insert_frame_array(cls, context, *, dmod = None, _visited = None):
        """Insert frame-based programming circuitry hierarchically.

        Args:
            context (`Context`):

        Keyword Args:
            dmod (`Module`): Design-view of the array in which programming circuitry is to be inserted
            _visited (:obj:`dict` [:obj:`Hashable`, :obj:`int` ]): Mapping from module keys to levels of buffering
                inside that module. Blocks and routing boxes, i.e. leaf-level modules, are buffered for one level.
                That is, a read access returns after three cycles \(1 cycle request buffering, 1 cycle read, 1 cycle
                read-back merging\)

        Returns:
            :obj:`int`: Levels of buffering in ``dmod``
        """
        _visited = uno(_visited, {})
        dmod = uno(dmod, context.database[ModuleView.design, context.top.key])
        amod = context.database[ModuleView.abstract, dmod.key]
        word_width = context.summary.frame["word_width"]
        addr_widths = context.summary.frame["addr_width"]
        andcell = context.database[ModuleView.design, "prga_frame_and"]

        maxlvl = -1
        for (x, y) in product(range(dmod.width), range(dmod.height)):

            # sub-tile or array
            if (dinst := dmod.instances.get( (x, y) )):
                if (lvl := (_visited.get(dinst.model.key))) is None:

                    if dinst.model.module_class.is_tile:
                        cls._insert_frame_tile(context, dinst.model)
                        lvl = _visited[dinst.model.key] = 1
                        # tile itself is 0, but we will buffer once before splitting between tile/sbox

                    else:
                        lvl = cls._insert_frame_array(context,
                                dmod = dinst.model, _visited = _visited)

                maxlvl = max(maxlvl, lvl)

            # sbox
            if maxlvl == -1:
                for corner in Corner:
                    if dinst := dmod.instances.get( ((x, y), corner) ):
                        # sbox itself is 0, but we will buffer once before splitting between tile/sbox
                        maxlvl = 1
                        break

        _visited[dmod.key] = maxlvl + 1     # we will buffer for one extra level in the array
        if maxlvl == -1:
            # logging
            _logger.info("Frame-based programming circuitry inserted into {}. No programming data needed"
                    .format(dmod))

            return 0

        nets = None
        if amod is context.top: # top-level array
            context.summary.frame["readback_latency"] = 2 * (maxlvl + 1) + 1

            x_width = addr_widths["x"]
            y_width = addr_widths["y"]
            fabric_width = addr_widths["fabric"]

            nets = cls._get_or_create_frame_prog_nets(dmod, word_width, fabric_width)

            # buffer write request and read-back response once at the fabric level
            cls._instantiate_buffer(context, dmod, nets, fabric_width, suffix = "_l{}".format(maxlvl))

            # decode x
            xdec = ModuleUtils.instantiate(dmod,
                    cls._get_or_create_frame_wldec(context, x_width, dmod.width),
                    "i_frame_wldec_xtop")
            NetUtils.connect(nets["prog_ce"], xdec.pins["ce_i"])
            NetUtils.connect(nets["prog_we"], xdec.pins["we_i"])
            NetUtils.connect(nets["prog_addr"][fabric_width - x_width:], xdec.pins["addr_i"])
            nets["prog_cex"] = xdec.pins["ce_o"]
            nets["prog_wex"] = xdec.pins["we_o"]

            # decode y
            ydec = ModuleUtils.instantiate(dmod,
                    cls._get_or_create_frame_wldec(context, y_width, dmod.height),
                    "i_frame_wldec_ytop")
            NetUtils.connect(nets["prog_ce"], ydec.pins["ce_i"])
            NetUtils.connect(nets["prog_we"], ydec.pins["we_i"])
            NetUtils.connect(nets["prog_addr"][addr_widths["tile"]:fabric_width - x_width], ydec.pins["addr_i"])
            nets["prog_cey"] = ydec.pins["ce_o"]
            nets["prog_wey"] = ydec.pins["we_o"]

            # adjust ``nets``
            del nets["prog_ce"]
            del nets["prog_we"]
            nets["prog_addr"] = nets["prog_addr"][:addr_widths["tile"]]

        else:                   # not top-level array
            nets = cls._get_or_create_frame_prog_nets(dmod, word_width, addr_widths["tile"], ["prog_ce", "prog_we"])

            # buffer cex/wex, cey/wey
            for dim in Dimension:
                bits = dim.case(dmod.width, dmod.height)

                ce = ModuleUtils.create_port(dmod, "prog_ce" + dim.name, bits, "input", net_class = NetClass.prog)
                we = ModuleUtils.create_port(dmod, "prog_we" + dim.name, bits, "input", net_class = NetClass.prog)

                nets_ce = nets["prog_ce" + dim.name] = []
                nets_we = nets["prog_we" + dim.name] = []

                for i in range(bits):
                    ibuf = ModuleUtils.instantiate(dmod,
                            cls._get_or_create_frame_buffer(context, 2),
                            "i_frame_ibuf_e{}{}_l{}".format(dim.name, i, maxlvl))
                    NetUtils.connect(nets["prog_clk"], ibuf.pins["prog_clk"])
                    NetUtils.connect(nets["prog_rst"], ibuf.pins["prog_rst"])
                    NetUtils.connect([ce[i], we[i]], ibuf.pins["i"])
                    nets_ce.append(ibuf.pins["o"][0])
                    nets_we.append(ibuf.pins["o"][1])

            # buffer addr/din
            ibuf = ModuleUtils.instantiate(dmod,
                    cls._get_or_create_frame_buffer(context, word_width + addr_widths["tile"]),
                    "i_frame_ibuf_l{}".format(maxlvl))
            NetUtils.connect(nets["prog_clk"], ibuf.pins["prog_clk"])
            NetUtils.connect(nets["prog_rst"], ibuf.pins["prog_rst"])
            NetUtils.connect([nets["prog_addr"], nets["prog_din"]], ibuf.pins["i"])
            nets["prog_addr"] = ibuf.pins["o"][:addr_widths["tile"]]
            nets["prog_din"] = ibuf.pins["o"][addr_widths["tile"]:]

            # buffer dout
            obuf = ModuleUtils.instantiate(dmod,
                    cls._get_or_create_frame_buffer(context, word_width),
                    "i_frame_obuf_l{}".format(maxlvl))
            NetUtils.connect(nets["prog_clk"], obuf.pins["prog_clk"])
            NetUtils.connect(nets["prog_rst"], obuf.pins["prog_rst"])
            NetUtils.connect(obuf.pins["o"],   nets["prog_dout"])
            nets["prog_dout"] = obuf.pins["i"]

        # merge x
        xmerge = ModuleUtils.instantiate(dmod,
                cls._get_or_create_frame_rbmerge(context, dmod.width, 2 * maxlvl + 1),
                "i_frame_rbmerge_xtop")
        NetUtils.connect(nets["prog_clk"], xmerge.pins["prog_clk"])
        NetUtils.connect(nets["prog_rst"], xmerge.pins["prog_rst"])
        NetUtils.connect(nets["prog_cex"], xmerge.pins["ce"])
        NetUtils.connect(xmerge.pins["dout"], nets["prog_dout"])

        nets["prog_dout"] = []

        # merge y
        for x in range(dmod.width):
            ymerge = ModuleUtils.instantiate(dmod,
                    cls._get_or_create_frame_rbmerge(context, dmod.height, 2 * maxlvl + 1),
                    "i_frame_rbmerge_ytop_x{}".format(x))
            NetUtils.connect(nets["prog_clk"], ymerge.pins["prog_clk"])
            NetUtils.connect(nets["prog_rst"], ymerge.pins["prog_rst"])
            NetUtils.connect(nets["prog_cey"], ymerge.pins["ce"])
            NetUtils.connect(ymerge.pins["dout"], xmerge.pins["din" + str(x)])
            nets["prog_dout"].append( tuple(ymerge.pins["din" + str(y)]
                for y in range(dmod.height)) )

        nets["prog_dout"] = tuple(iter(nets["prog_dout"]))

        # traverse tiles and sboxes again
        for x, y in product( range(dmod.width), range(dmod.height) ):
            xwls, ywls = 1, 1

            # additional buffering?
            minlvl = 1
            subnets = []
            if (dinst := dmod.instances.get((x, y))) and dinst.model.module_class.is_array:
                if (minlvl := _visited[dinst.model.key]) == 0:
                    continue    # well it turns out this tile does not require any programming data!

                xwls, ywls = dinst.model.width, dinst.model.height

            # if ``dinst`` is not an array, or is an empty tile
            # find all the switch boxes
            elif (ainst := amod._instances.get_root( (x, y) )) is None or not ainst.model.module_class.is_array:
                for corner in Corner:
                    if sbox := dmod.instances.get( ((x, y), corner) ):
                        if ((prog_clk := sbox.pins.get("prog_clk"))
                                and NetUtils.get_source(prog_clk) is None):
                            NetUtils.connect(nets["prog_clk"],  sbox.pins["prog_clk"])
                            NetUtils.connect(nets["prog_rst"],  sbox.pins["prog_rst"])
                            NetUtils.connect(nets["prog_done"], sbox.pins["prog_done"])

                        amod.instances[sbox.key].frame_id = sbox.frame_id = len(subnets)
                        subnets.append( sbox.pins )

                    else:
                        subnets.append({})

            # shortcut
            if dinst is None and not any(subnets):
                continue

            # local copy of nets
            gridnets = {
                    "prog_clk":  nets["prog_clk"],
                    "prog_rst":  nets["prog_rst"],
                    "prog_done": nets["prog_done"],
                    "prog_cex":  nets["prog_cex"][x:x+xwls],
                    "prog_wex":  nets["prog_wex"][x:x+xwls],
                    "prog_cey":  nets["prog_cey"][y:y+ywls],
                    "prog_wey":  nets["prog_wey"][y:y+ywls],
                    "prog_addr": nets["prog_addr"],
                    "prog_din":  nets["prog_din"],
                    "prog_dout": tuple( nets["prog_dout"][xx][yy]
                        for xx, yy in product(range(x, x + xwls), range(y, y + ywls)) ),
                    }

            # match buffering levels
            for lvl in reversed(range(minlvl, maxlvl)):
                # buffer cex/wex, cey/wey
                for dim in Dimension:
                    nets_ce, nets_we = [], []

                    for i in dim.case(range(xwls), range(ywls)):
                        iname = "i_frame_ibuf_e{}{}_l{}".format(dim.name, i + dim.case(x, y), lvl)
                        if (ibuf := dmod.instances.get(iname)) is None:
                            ibuf = ModuleUtils.instantiate(dmod, cls._get_or_create_frame_buffer(context, 2), iname)
                            NetUtils.connect(gridnets["prog_clk"], ibuf.pins["prog_clk"])
                            NetUtils.connect(gridnets["prog_rst"], ibuf.pins["prog_rst"])
                            NetUtils.connect(
                                    [gridnets["prog_ce" + dim.name][i], gridnets["prog_we" + dim.name][i]],
                                    ibuf.pins["i"])
                        nets_ce.append(ibuf.pins["o"][0])
                        nets_we.append(ibuf.pins["o"][1])

                    gridnets["prog_ce" + dim.name] = nets_ce
                    gridnets["prog_we" + dim.name] = nets_we

                # buffer addr/din (if needed)
                if (ibuf := dmod.instances.get(ibuf_name := "i_frame_ibuf_l{}".format(lvl))) is None:
                    ibuf = ModuleUtils.instantiate(dmod,
                            cls._get_or_create_frame_buffer(context, word_width + addr_widths["tile"]),
                            ibuf_name)
                    NetUtils.connect(gridnets["prog_clk"], ibuf.pins["prog_clk"])
                    NetUtils.connect(gridnets["prog_rst"], ibuf.pins["prog_rst"])
                    NetUtils.connect([gridnets["prog_addr"], gridnets["prog_din"]], ibuf.pins["i"])

                gridnets["prog_addr"] = ibuf.pins["o"][:addr_widths["tile"]]
                gridnets["prog_din"]  = ibuf.pins["o"][addr_widths["tile"]:]

                # buffer dout
                obuf = ModuleUtils.instantiate(dmod,
                        cls._get_or_create_frame_buffer(context, word_width),
                        "i_frame_obuf_x{}y{}_l{}".format(x, y, lvl))
                NetUtils.connect(gridnets["prog_clk"], obuf.pins["prog_clk"])
                NetUtils.connect(gridnets["prog_rst"], obuf.pins["prog_rst"])
                for dout in gridnets["prog_dout"]:
                    NetUtils.connect(obuf.pins["o"], dout)
                gridnets["prog_dout"] = (obuf.pins["i"], )

            # connect if ``dinst`` is an array
            if dinst and dinst.model.module_class.is_array:
                NetUtils.connect(gridnets["prog_cex"],  dinst.pins["prog_cex"])
                NetUtils.connect(gridnets["prog_wex"],  dinst.pins["prog_wex"])
                NetUtils.connect(gridnets["prog_cey"],  dinst.pins["prog_cey"])
                NetUtils.connect(gridnets["prog_wey"],  dinst.pins["prog_wey"])
                NetUtils.connect(gridnets["prog_addr"], dinst.pins["prog_addr"])
                NetUtils.connect(gridnets["prog_din"],  dinst.pins["prog_din"])
                for dout in gridnets["prog_dout"]:
                    NetUtils.connect(dinst.pins["prog_dout"], dout)
                continue

            # buffer before splitting between tile and sbox
            # instantiate and(cex, cey), and(wex, wey) first
            for e in ("ce", "we"):
                iand = ModuleUtils.instantiate(dmod, andcell, "i_frame_and{}_x{}y{}".format(e, x, y))
                NetUtils.connect(gridnets["prog_" + e + "x"][0], iand.pins["ix"])
                NetUtils.connect(gridnets["prog_" + e + "y"][0], iand.pins["iy"])
                gridnets["prog_" + e] = iand.pins['o']

            assert len(gridnets["prog_dout"]) == 1
            gridnets["prog_dout"] = gridnets["prog_dout"][0]

            # instantiate buffer
            cls._instantiate_buffer(context, dmod, gridnets, len(gridnets["prog_addr"]),
                    suffix = "_x{}y{}_l0".format(x, y))

            # instantiate a decoder for the switch boxes
            sboxnets = {}
            if any(subnets):
                sboxnets = cls._instantiate_decoder(context, dmod, gridnets, subnets,
                        gridnets["prog_addr"][addr_widths["sbox"]:addr_widths["tile"] - 1],
                        suffix = "_x{}y{}_sbox".format(x, y))

            # annotate tile instance
            tilenets = {}
            if dinst is not None:
                tilenets = dinst.pins

            # instantiate a decoder between tile and sboxes
            rootnets = cls._instantiate_decoder(context, dmod, gridnets,
                    [sboxnets, tilenets],
                    gridnets["prog_addr"][-1:],
                    suffix = "_x{}y{}_tile".format(x, y))

            # connect last-level buffer with the root decoder
            NetUtils.connect(gridnets["prog_ce"],   rootnets["prog_ce"])
            NetUtils.connect(gridnets["prog_we"],   rootnets["prog_we"])
            NetUtils.connect(rootnets["prog_dout"], gridnets["prog_dout"])

        # logging
        _logger.info("Frame-based programming circuitry inserted into {}"
                .format(dmod))
        return maxlvl + 1

    @classmethod
    def _insert_frame_tile(cls, context, dmod):
        """Insert frame-based programming circuitry hierarchically.

        Args:
            context (`Context`):
            dmod (`Module`): Design-view of the tile in which programming circuitry is to be inserted
            _visited (:obj:`dict` [:obj:`Hashable`, :obj:`int` ]): Mapping from module keys to levels of buffering
                inside that module. Blocks and routing boxes, i.e. leaf-level modules, are buffered for one level.
                That is, a read access returns after three cycles \(1 cycle request buffering, 1 cycle read, 1 cycle
                read-back merging\)
        """
        amod = context.database[ModuleView.abstract, dmod.key]
        word_width = context.summary.frame["word_width"]
        addr_widths = context.summary.frame["addr_width"]

        subblock_id = slice(addr_widths["block"], addr_widths["tile"] - 2)
        cbox_id     = slice(addr_widths["cbox"],  addr_widths["tile"] - 2)

        nets = cls._get_or_create_frame_prog_nets(dmod, word_width, addr_widths["tile"] - 1)

        # find all the sub-blocks
        subnets = []
        for i in count():
            if dinst := dmod.instances.get( i ):
                if ((prog_clk := dinst.pins.get("prog_clk"))
                        and NetUtils.get_source(prog_clk) is None):
                    NetUtils.connect(nets["prog_clk"],  dinst.pins["prog_clk"])
                    NetUtils.connect(nets["prog_rst"],  dinst.pins["prog_rst"])
                    NetUtils.connect(nets["prog_done"], dinst.pins["prog_done"])

                subnets.append( dinst.pins )
            else:
                break

        # instantiate a decoder for the subblocks
        blknets = {}
        if any("prog_ce" in subnet for subnet in subnets):
            blknets = cls._instantiate_decoder(context, dmod, nets, subnets,
                    nets["prog_addr"][subblock_id],
                    suffix = "_blk")

        # find all the connection boxes
        subnets = []
        for key in chain(
                product( (Orientation.south, Orientation.north), range(dmod.width)),
                product( (Orientation.west,  Orientation.east),  range(dmod.height)) ):

            if (dinst := dmod.instances.get( key )) is None:
                continue

            if ((prog_clk := dinst.pins.get("prog_clk"))
                    and NetUtils.get_source(prog_clk) is None):
                NetUtils.connect(nets["prog_clk"],  dinst.pins["prog_clk"])
                NetUtils.connect(nets["prog_rst"],  dinst.pins["prog_rst"])
                NetUtils.connect(nets["prog_done"], dinst.pins["prog_done"])

            amod.instances[key].frame_id = dinst.frame_id = len(subnets)
            subnets.append( dinst.pins )

        # instantiate a decoder for the connection boxes
        cboxnets = {}
        if any("prog_ce" in subnet for subnet in subnets):
            cboxnets = cls._instantiate_decoder(context, dmod, nets, subnets,
                    nets["prog_addr"][cbox_id],
                    suffix = "_cbox")

        # instantiate root decoder
        rootnets = cls._instantiate_decoder(context, dmod, nets, [blknets, cboxnets],
                nets["prog_addr"][addr_widths["tile"] - 2:addr_widths["tile"] - 1],
                suffix = "_tile")

        # connect tree root
        NetUtils.connect(nets["prog_ce"],       rootnets["prog_ce"])
        NetUtils.connect(nets["prog_we"],       rootnets["prog_we"])
        NetUtils.connect(rootnets["prog_dout"], nets["prog_dout"])

    @classmethod
    def _insert_frame_leaf(cls, context, dmod, visited, *, _not_top = False):
        """Insert frame-based programming circuitry into logic/io blocks and switch/connection boxes.

        Returns:
            :obj:`int`: addr_width needed for this leaf
        """
        visited.add(dmod.key)
        if dmod.module_class in (ModuleClass.primitive, ModuleClass.switch):
            return 0

        _logger.debug("Inserting frame-based programming circuitry into {}".format(dmod))

        # traverse and categorize programmable instances
        inst_ims = []   # list[instance]: instances with internal memory spaces
        inst_pds = []   # list[instance]: instances with programming data but no internal memory spaces
        inst_dos = []   # list[instance]: instances with prog_done interface but no programming ports

        for dinst in dmod.instances.values():
            if dinst.model.module_class.is_prog:
                raise PRGAInternalError("Existing programming cell found during programming cell insertion: {}"
                        .format(dinst))

            elif dinst.model.module_class.is_aux:
                continue

            elif dinst.model.key not in visited:
                cls._insert_frame_leaf(context, dinst.model, visited, _not_top = True)

            if "prog_ce" in dinst.pins:     # instance with internal memory space
                inst_ims.append(dinst)

            elif "prog_data" in dinst.pins: # instance with programming data but no internal memory space
                inst_pds.append(dinst)

            elif "prog_done" in dinst.pins: # instance with prog_done interface but no programming ports 
                inst_dos.append(dinst)

        # shortcut
        if not (inst_ims or inst_pds or inst_dos):
            # logging
            _logger.info("Frame-based programming circuitry inserted into {}. No programming data needed"
                    .format(dmod))
            return 0

        # get the basic programming interface
        nets = cls._get_or_create_prog_nets(dmod)

        # connect easy wires
        for dinst in chain(inst_pds, inst_dos):
            for key in ("prog_clk", "prog_rst", "prog_done"):
                if pin := dinst.pins.get(key):
                    NetUtils.connect(nets[key], pin)

        # another shortcut
        if not (inst_ims or inst_pds):
            # logging
            _logger.info("Frame-based programming circuitry inserted into {}. No programming data needed"
                    .format(dmod))
            return 0

        # abstract view of `dmod`
        amod = context.database[ModuleView.abstract, dmod.key]

        # plain data bits
        plain_bits = sum(len(dinst.pins["prog_data"]) for dinst in inst_pds)
        leaf_data_cell = None

        # process `inst_pds`
        if plain_bits > 0:
            prog_data = None

            # case 1: we need to instantiate sram data for `inst_pds`
            if inst_ims or not _not_top:
                leaf_data_cell = ModuleUtils.instantiate(dmod,
                        cls._get_or_create_frame_data_cell(context, plain_bits),
                        "i_frame_data")
                inst_ims.append(leaf_data_cell)
                prog_data = leaf_data_cell.pins["prog_data_o"]

            # case 2: we need to create a "prog_data" port in `dmod` for `inst_pds`
            else:
                prog_data = ModuleUtils.create_port(dmod, "prog_data", plain_bits, PortDirection.input_,
                        net_class = NetClass.prog)

            # connect and update bitmap for each instance in `inst_pds`
            offset = 0
            for dinst in inst_pds:
                p = dinst.pins["prog_data"]
                NetUtils.connect(prog_data[offset:offset+len(p)], p)

                dinst.frame_bitmap = ProgDataBitmap( (offset, len(p)) )
                if ainst := amod.instances.get(dinst.key):
                    ainst.frame_bitmap = dinst.frame_bitmap

                offset += len(p)

        # one more shortcut
        if not inst_ims:
            # logging
            _logger.info("Frame-based programming circuitry inserted into {}. {} bits exposed to parent modules"
                    .format(dmod, plain_bits))
            return 0

        # process `inst_ims`
        # arrange memory space. put larger memory spaces in lower addresses.
        inst_ims = sorted(inst_ims,
                key = lambda i: len(p) if (p := i.pins.get("prog_addr")) else 0,
                reverse = True)

        # construct decoder tree
        tree = None
        for dinst in inst_ims:
            # construct tree
            if tree is None:
                tree = cls._FrameDecoderTreeNode(cls._FrameDecoderTreeLeaf(dinst))
            else:
                tree.add_node(cls._FrameDecoderTreeLeaf(dinst))

        # create ports specific to frame-based programming circuitry
        word_width = context.summary.frame["word_width"]
        nets = cls._get_or_create_frame_prog_nets(dmod, word_width, tree.addr_width)

        # instantiate buffer for block/box
        if not _not_top:
            cls._instantiate_buffer(context, dmod, nets, tree.addr_width, suffix = "_l0")

        # instantiate decoders and mergers for the decoder tree
        assert tree is not None
        treenets = cls._construct_decoder_tree(context, dmod, nets, tree)

        # connect tree root
        NetUtils.connect(nets["prog_ce"],       treenets["prog_ce"])
        NetUtils.connect(nets["prog_we"],       treenets["prog_we"])
        NetUtils.connect(treenets["prog_dout"], nets["prog_dout"])

        # annotate address maps
        for dinst in inst_ims:
            if dinst is leaf_data_cell:
                frame_baseaddr = dinst.frame_baseaddr

                for dinst in inst_pds:
                    dinst.frame_baseaddr = frame_baseaddr
                    if ainst := amod.instances.get(dinst.key):
                        ainst.frame_baseaddr = frame_baseaddr

            elif ainst := amod.instances.get(dinst.key):
                ainst.frame_baseaddr = dinst.frame_baseaddr

        # logging
        _logger.info("Frame-based programming circuitry inserted into {}. Address width: {} ({} {}b words)"
                .format(dmod, tree.addr_width, 2 ** tree.addr_width, word_width))

        return tree.addr_width
