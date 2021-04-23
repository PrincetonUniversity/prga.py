# -*- encoding: ascii -*-

from ..common import AbstractProgCircuitryEntry, ProgDataBitmap
from ...core.common import NetClass, ModuleClass, ModuleView
from ...netlist import Module, ModuleUtils, PortDirection, NetUtils
from ...passes.translation import SwitchDelegate
from ...renderer.lib import BuiltinCellLibrary
from ...util import uno, Object
from ...exception import PRGAInternalError

import os, logging
from itertools import chain
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
            return len(self.instance.pins["prog_addr"])
        
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
            if len(self.children) == 1:
                return self.child_addr_width
            else:
                return self.child_addr_width + (len(self.children) - 1).bit_length()

        @property
        def is_leaf(self):
            return False

        def add_node(self, node):
            assert node.addr_width <= self.child_addr_width

            if node.addr_width < self.child_addr_width:
                # check if any of my children is able to accomodate this node
                for child in self.children:
                    if not child.is_leaf and child.add_node(node):
                        return True

            # none of my children is able to accomodate this node. what about myself?
            if (self.parent is None # well I'm the root, I can do whatever I want. Yoooo!
                                    # or.. I have enough space left at my expense
                    or len(self.children) < 2 ** (self.parent.child_addr_width - self.child_addr_width)):

                if node.addr_width < self.child_addr_width:
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
        cls.buffer_prog_ctrl(context)
        cls._insert_frame(context)

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
        if "prog_addr" not in excludes:
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

        cell = context._add_module(Module(name,
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.prog,
            verilog_template = "prga_frame_sramdata.tmpl.v"))
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
    def _get_or_create_frame_wldec(cls, context, addr_width, data_width):
        name = "prga_frame_wldec_d{}".format(data_width)
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
        ModuleUtils.create_port(cell, "ce_o",   data_width, PortDirection.output, net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "we_o",   data_width, PortDirection.output, net_class = NetClass.prog)

        return cell

    @classmethod
    def _get_or_create_frame_rbmerge(cls, context, addr_width, num_sources, num_stages):
        name = "prga_frame_rbmerge_a{}n{}s{}".format(addr_width, num_sources, num_stages)
        if cell := context.database.get( (ModuleView.design, name) ):
            return cell

        word_width = context.summary.frame["word_width"]
        cell = context._add_module(Module(name,
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.prog,
            num_sources = num_sources,
            num_stages = num_stages,
            verilog_template = "prga_frame_wldec.tmpl.v"))
        cls._get_or_create_prog_nets(cell, excludes = ["prog_done"])
        ModuleUtils.create_port(cell, "addr", addr_width, PortDirection.input_, net_class = NetClass.prog)
        for i in range(num_sources):
            ModuleUtils.create_port(cell, "din"+str(i), word_width, PortDirection.input_, net_class = NetClass.prog)
        ModuleUtils.create_port(cell, "dout", word_width, PortDirection.output, net_class = NetClass.prog)

        return cell

    @classmethod
    def _construct_decoder_tree(cls, context, module, node, nets, *,
            stages = 1, decoders = None, mergers = None, baseaddr = 0):

        word_width = context.summary.frame["word_width"]
        decoders = uno(decoders, [])
        mergers = uno(mergers, [])

        # leaf node
        if node.is_leaf:
            node.instance.frame_addrmap = ProgDataBitmap(
                    (baseaddr, (2 ** len(node.instance.pins["prog_addr"]))) )

            NetUtils.connect(nets["prog_clk"],  node.instance.pins["prog_clk"])
            NetUtils.connect(nets["prog_rst"],  node.instance.pins["prog_rst"])
            NetUtils.connect(nets["prog_done"], node.instance.pins["prog_done"])
            NetUtils.connect(nets["prog_addr"], node.instance.pins["prog_addr"])
            NetUtils.connect(nets["prog_din"],  node.instance.pins["prog_din"])
            NetUtils.connect(nets["prog_ce"],   node.instance.pins["prog_ce"])
            NetUtils.connect(nets["prog_we"],   node.instance.pins["prog_we"])

            return node.instance.pins["prog_dout"]

        # non-leaf node
        addr_width = node.addr_width if node.parent is None else node.parent.child_addr_width
        readbacks = []

        if addr_width > node.child_addr_width:
            decoder = ModuleUtils.instantiate(module,
                    cls._get_or_create_frame_wldec(context, addr_width - node.child_addr_width, len(node.children)),
                    "i_frame_wldec_i{}".format(len(decoders)))
            decoders.append(decoder)

            NetUtils.connect(nets["prog_ce"], decoder.pins["ce_i"])
            NetUtils.connect(nets["prog_we"], decoder.pins["we_i"])
            NetUtils.connect(nets["prog_addr"][node.child_addr_width:addr_width], decoder.pins["addr_i"])

            for i, child in enumerate(node.children):
                curnets = copy(nets)
                curnets["prog_addr"] = nets["prog_addr"][:node.child_addr_width]
                curnets["prog_ce"] = decoder.pins["ce_o"][i]
                curnets["prog_we"] = decoder.pins["we_o"][i]
                readbacks.append( cls._construct_decoder_tree(context, module, child, curnets,
                    stages = stages, decoders = decoders, mergers = mergers,
                    baseaddr = baseaddr + 2 ** node.child_addr_width) )

        elif node.children:
            readbacks.append( cls._construct_decoder_tree(context, module, node.children[0], nets,
                stages = stages, decoders = decoders, mergers = mergers, baseaddr = baseaddr) )

        # read-back mergers
        assert len(readbacks) >= 1
        if len(readbacks) == 1:     # no merge needed
            return readbacks[0]

        merger = ModuleUtils.instantiate(module,
                cls._get_or_create_frame_rbmerge(context, addr_width - node.child_addr_width, len(readbacks), stages),
                "i_frame_rbmerge_i{}".format(len(mergers)))
        mergers.append(merger)

        NetUtils.connect(nets["prog_clk"], merger.pins["prog_clk"])
        NetUtils.connect(nets["prog_rst"], merger.pins["prog_rst"])
        NetUtils.connect(nets["prog_addr"][node.child_addr_width:addr_width], merger.pins["addr"])

        for i, readback in enumerate(readbacks):
            NetUtils.connect(readback, merger.pins["din" + str(i)])

        return merger.pins["dout"]

    @classmethod
    def _insert_frame(cls, context, design_view = None, *, _visited = None):
        """Insert frame-based programming circuitry.

        Args:
            context (`Context`):
            design_view (`Module`): The module (design view) in which frame-based programming circuitry is inserted.
                If not specified, the top-level array in ``context`` is selected

        This method calls itself recursively to process all the instances (sub-modules).
        """
        _visited = uno(_visited, set())
        dmod = uno(design_view, context.database[ModuleView.design, context.top.key])

        if dmod.key in _visited or dmod.module_class.is_primitive:
            return

        _visited.add(dmod.key)
        amod = context.database[ModuleView.abstract, dmod.key]

        # traverse programmable instances, instantiate programming cells and connect stuff
        addr = 0            # address
        offset = 0          # bit offset
        prog_nets = None
        instances_snapshot = tuple(dmod.instances.values())

        for dinst in instances_snapshot:
            if dinst.model.module_class.is_prog:
                raise PRGAInternalError("Existing programming cell found during programming cell insertion: {}"
                        .format(dinst))

            elif dinst.model.module_class.is_aux:
                continue

            # XXX: reach leaf as soon as possible!
            elif dinst.model.module_class in (ModuleClass.logic_block, ModuleClass.io_block,
                    ModuleClass.switch_box, ModuleClass.connection_box):
                if dinst.model.key not in _visited:
                    cls._insert_frame_leaf(context, dinst.model, _visited)

            else:
                cls._insert_frame(context, dinst.model, _visited = _visited)

    @classmethod
    def _insert_frame_leaf(cls, context, dmod, visited, *, _not_top = False):
        """Insert frame-based programming circuitry into logic/io blocks and switch/connection boxes."""
        visited.add(dmod.key)
        if dmod.module_class in (ModuleClass.primitive, ModuleClass.switch):
            return

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

            if "prog_addr" in dinst.pins:   # instance with internal memory space
                inst_ims.append(dinst)

            elif "prog_data" in dinst.pins: # instance with programming data but no internal memory space
                inst_pds.append(dinst)

            elif "prog_done" in dinst.pins: # instance with prog_done interface but no programming ports 
                inst_dos.append(dinst)

        # shortcut
        if not (inst_ims or inst_pds or inst_dos):
            return

        # get the basic programming interface
        nets = cls._get_or_create_prog_nets(dmod)

        # connect easy wires
        for dinst in chain(inst_pds, inst_dos):
            for key in ("prog_clk", "prog_rst", "prog_done"):
                if pin := dinst.pins.get(key):
                    NetUtils.connect(nets[key], pin)

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

        # shortcut
        if not inst_ims:
            return

        # process `inst_ims`
        # arrange memory space. put larger memory spaces in lower addresses.
        inst_ims = sorted(inst_ims, key = lambda i: len(i.pins["prog_addr"]), reverse = True)

        # construct decoder tree
        tree = None
        for dinst in inst_ims:
            if tree is None:
                tree = cls._FrameDecoderTreeNode(cls._FrameDecoderTreeLeaf(dinst))
            else:
                tree.add_node(cls._FrameDecoderTreeLeaf(dinst))

        # instantiate buffer, word-line decoder, and read-back merger
        word_width = context.summary.frame["word_width"]
        nets = cls._get_or_create_frame_prog_nets(dmod, word_width, tree.addr_width)

        # instantiate buffer for block/box
        if not _not_top:
            ibuf = ModuleUtils.instantiate(dmod,
                    cls._get_or_create_frame_buffer(context, tree.addr_width + word_width + 2),
                    "i_frame_rqbuf")
            NetUtils.connect(nets["prog_clk"], ibuf.pins["prog_clk"])
            NetUtils.connect(nets["prog_rst"], ibuf.pins["prog_rst"])
            NetUtils.connect(
                    [nets["prog_ce"], nets["prog_we"], nets["prog_addr"], nets["prog_din"]],
                    ibuf.pins["i"])
            nets["prog_ce"]     = ibuf.pins["o"][0]
            nets["prog_we"]     = ibuf.pins["o"][1]
            nets["prog_addr"]   = ibuf.pins["o"][2:tree.addr_width+2]
            nets["prog_din"]    = ibuf.pins["o"][tree.addr_width+2:]

        # instantiate word-line decoders
        NetUtils.connect(
                cls._construct_decoder_tree(context, dmod, tree, nets),
                nets["prog_dout"])

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
