# -*- encoding: ascii -*-

from ..common import AbstractProgCircuitryEntry, ProgDataBitmap
from ...core.common import NetClass, ModuleClass, ModuleView, Corner, Orientation
from ...netlist import Module, ModuleUtils, PortDirection, NetUtils
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
        BuiltinCellLibrary.install_design(ctx)

        ctx.template_search_paths.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'))
        ctx.renderer = None

        ctx.summary.frame = {"word_width": word_width}

        return ctx

    @classmethod
    def insert_prog_circuitry(cls, context):
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

        # final address mapping
        addrmap = {
                # widths
                "tile":         tile_aw,
                "sbox":         max_sbox_aw,
                "block":        max_blk_aw,
                "cbox":         max_cbox_aw,

                # ranges
                "sbox_id":      slice(tile_aw - 1 - sbox_id_width,      tile_aw - 1),
                "subblock_id":  slice(tile_aw - 2 - subblock_id_width,  tile_aw - 2),
                "cbox_id":      slice(tile_aw - 2 - cbox_id_width,      tile_aw - 2),
                "subtile":      slice(tile_aw - 2,                      tile_aw - 1),
                }

        cls._insert_frame_hier(context, addrmap)

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
    def _instantiate_frame_buffer(cls, context, dmod, nets, addr_width, *,
            suffix = None, inplace = False):

        rq_name  = "i_frame_rqbuf" + ("" if suffix is None else ("_" + suffix))
        rsp_name  = "i_frame_rspbuf" + ("" if suffix is None else ("_" + suffix))

        word_width = context.summary.frame["word_width"]
        ibuf = ModuleUtils.instantiate(dmod,
                cls._get_or_create_frame_buffer(context, addr_width + word_width + 2),
                rq_name)
        obuf = ModuleUtils.instantiate(dmod,
                cls._get_or_create_frame_buffer(context, word_width),
                rsp_name)

        if not inplace:
            nets = copy(nets)

        NetUtils.connect(nets["prog_clk"], ibuf.pins["prog_clk"])
        NetUtils.connect(nets["prog_rst"], ibuf.pins["prog_rst"])

        if addr_width > 0:
            NetUtils.connect(
                    [nets["prog_ce"], nets["prog_we"], nets["prog_addr"], nets["prog_din"]],
                    ibuf.pins["i"])
            nets["prog_addr"]   = ibuf.pins["o"][2:2+addr_width]
        else:
            NetUtils.connect(
                    [nets["prog_ce"], nets["prog_we"], nets["prog_din"]],
                    ibuf.pins["i"])

        nets["prog_ce"]     = ibuf.pins["o"][0]
        nets["prog_we"]     = ibuf.pins["o"][1]
        nets["prog_din"]    = ibuf.pins["o"][2+addr_width:]

        NetUtils.connect(nets["prog_clk"], obuf.pins["prog_clk"])
        NetUtils.connect(nets["prog_rst"], obuf.pins["prog_rst"])
        NetUtils.connect(obuf.pins["o"],   nets["prog_dout"])

        nets["prog_dout"]   = obuf.pins["i"]

        return nets

    @classmethod
    def _instantiate_decoder(cls, context, module, nets, subnets, addrnet, *,
            suffix = None, merger_stage = 1, dont_connect_subnets = False):

        decoder_name = "i_frame_wldec" + ("" if suffix is None else ("_" + suffix))
        merger_name = "i_frame_rbmerge" + ("" if suffix is None else ("_" + suffix))

        decoder = ModuleUtils.instantiate(module,
                cls._get_or_create_frame_wldec(context, len(addrnet), len(subnets)),
                decoder_name)
        merger = ModuleUtils.instantiate(module,
                cls._get_or_create_frame_rbmerge(context, len(subnets), merger_stage),
                merger_name)

        for i, subnet in enumerate(subnets):
            if "prog_ce" in subnet:
                NetUtils.connect(decoder.pins["ce_o"][i], subnet["prog_ce"])
                NetUtils.connect(decoder.pins["we_o"][i], subnet["prog_we"])
                NetUtils.connect(subnet["prog_dout"], merger.pins["din" + str(i)])

                if not dont_connect_subnets and (p := subnet.get("prog_addr")):
                    NetUtils.connect(nets["prog_addr"][:len(p)], p)

                if not dont_connect_subnets and (p := subnet.get("prog_din")):
                    NetUtils.connect(nets["prog_din"], p)

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

            node.instance.frame_addrmap = ProgDataBitmap(
                    (baseaddr, (2 ** (len(p) if (p := node.instance.pins.get("prog_addr")) else 0)) ) )
            if ainst := amod.instances.get(node.instance.key):
                ainst.frame_addrmap = node.instance.frame_addrmap

            return node.instance.pins

        # non-leaf node
        addr_width = node.addr_width if node.parent is None else node.parent.child_addr_width

        if addr_width > node.child_addr_width:

            subnets = [cls._construct_decoder_tree(context, module, nets, child,
                _treenets = _treenets, baseaddr = baseaddr + (i << node.child_addr_width))
                for i, child in enumerate(node.children)]

            treenet = cls._instantiate_decoder( context, module, nets, subnets,
                    nets["prog_addr"][node.child_addr_width:addr_width],
                    suffix = "i{}".format(len(_treenets)),
                    dont_connect_subnets = True,
                    )

            _treenets.append(treenet)
            return treenet

        else:
            return cls._construct_decoder_tree(context, module, nets, node.children[0],
                    _treenets = _treenets, baseaddr = baseaddr)

    @classmethod
    def _insert_frame_hier(cls, context, addrmap, *, dmod = None, _visited = None, _not_top = False):
        """Insert frame-based programming circuitry hierarchically.

        Args:
            context (`Context`):
            addrmap (:obj:`dict` [:obj:`str`, :obj:`tuple` [:obj:`int`, :obj:`int`]]):

        Keyword Args:
            dmod (`Module`): Design-view of the array or tile in which programming circuitry is to be inserted
            _visited (:obj:`dict` [:obj:`Hashable`, :obj:`int` ]): Mapping from module keys to levels of buffering
                inside that module. Blocks and routing boxes, i.e. leaf-level modules, are buffered for one level.
                That is, a read access returns after three cycles \(1 cycle request buffering, 1 cycle read, 1 cycle
                read-back merging\)
            _not_top (:obj:`bool`): Marks ``dmod`` as not the top-level array

        Returns:
            :obj:`int`: Levels of buffering in ``dmod``
        """
        _visited = uno(_visited, {})
        dmod = uno(dmod, context.database[ModuleView.design, context.top.key])
        amod = context.database[ModuleView.abstract, dmod.key]
        word_width = context.summary.frame["word_width"]

        # tile
        if dmod.module_class.is_tile:
            nets = cls._get_or_create_frame_prog_nets(dmod, word_width, addrmap["tile"] - 1)

            # buffer request
            cls._instantiate_frame_buffer(context, dmod, nets, addrmap["tile"] - 1, inplace = True)

            # find all the sub-blocks
            subnets = []
            for i in count():
                if dinst := dmod.instances.get( i ):
                    if ((prog_clk := dinst.pins.get("prog_clk"))
                            and NetUtils.get_source(prog_clk) is None):
                        NetUtils.connect(nets["prog_clk"],  dinst.pins["prog_clk"])
                        NetUtils.connect(nets["prog_rst"],  dinst.pins["prog_rst"])
                        NetUtils.connect(nets["prog_done"], dinst.pins["prog_done"])

                    dinst.frame_addrmap = ProgDataBitmap( (i << addrmap["block"], 1 << addrmap["block"]) )
                    amod.instances[i].frame_addrmap = dinst.frame_addrmap
                    subnets.append( dinst.pins )
                else:
                    break

            # instantiate a decoder for the subblocks
            blknets = {}
            if any("prog_ce" in subnet for subnet in subnets):
                blknets = cls._instantiate_decoder(context, dmod, nets, subnets,
                        nets["prog_addr"][addrmap["subblock_id"]],
                        suffix = "blk", merger_stage = 3)

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

                dinst.frame_addrmap = ProgDataBitmap(
                        ((0x1 << (addrmap["tile"] - 2)) + (len(subnets) << addrmap["cbox"]),
                            1 << addrmap["cbox"]) )
                amod.instances[key].frame_addrmap = dinst.frame_addrmap
                subnets.append( dinst.pins )

            # instantiate a decoder for the connection boxes
            cboxnets = {}
            if any("prog_ce" in subnet for subnet in subnets):
                cboxnets = cls._instantiate_decoder(context, dmod, nets, subnets,
                        nets["prog_addr"][addrmap["cbox_id"]],
                        suffix = "cbox", merger_stage = 3)

            # instantiate root decoder
            rootnets = cls._instantiate_decoder(context, dmod, nets, [blknets, cboxnets],
                    nets["prog_addr"][addrmap["subtile"]],
                    suffix = "tile", merger_stage = 3)

            # connect tree root
            NetUtils.connect(nets["prog_ce"],       rootnets["prog_ce"])
            NetUtils.connect(nets["prog_we"],       rootnets["prog_we"])
            NetUtils.connect(rootnets["prog_dout"], nets["prog_dout"])

            _visited[dmod.key] = 2  # always 2 levels of buffering (one leve in tile, one level in block/cbox)
            return 2

        # array
        for (x, y) in product(range(dmod.width), range(dmod.height)):
            if (dinst := dmod.instances.get( (x, y) )) and dinst.model.key not in _visited:
                cls._insert_frame_hier(context, addrmap,
                        dmod = dinst.model, _visited = _visited, _not_top = True)

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
            cls._instantiate_frame_buffer(context, dmod, nets, tree.addr_width, inplace = True)

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
                frame_addrmap = dinst.frame_addrmap

                for dinst in inst_pds:
                    dinst.frame_addrmap = frame_addrmap
                    if ainst := amod.instances.get(dinst.key):
                        ainst.frame_addrmap = frame_addrmap

            elif ainst := amod.instances.get(dinst.key):
                ainst.frame_addrmap = dinst.frame_addrmap

        return tree.addr_width
