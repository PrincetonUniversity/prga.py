# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import (Global, Segment, ModuleClass, PrimitiveClass, PrimitivePortClass, ModuleView, OrientationTuple,
        DirectTunnel)
from .builder.primitive import LogicalPrimitiveBuilder, PrimitiveBuilder, MultimodeBuilder
from .builder.block import ClusterBuilder, IOBlockBuilder, LogicBlockBuilder
from .builder.box import ConnectionBoxBuilder, SwitchBoxBuilder
from .builder.array import LeafArrayBuilder, NonLeafArrayBuilder
from ..netlist.net.common import PortDirection
from ..netlist.module.module import Module
from ..netlist.module.util import ModuleUtils
from ..netlist.net.util import NetUtils
from ..util import Object, ReadonlyMappingProxy, uno
from ..exception import PRGAAPIError

from collections import OrderedDict

import sys
sys.setrecursionlimit(2**16)

try:
    import cPickle as pickle
except ImportError:
    import pickle

__all__ = ['ContextSummary', 'Context']

# ----------------------------------------------------------------------------
# -- FPGA Summary ------------------------------------------------------------
# ----------------------------------------------------------------------------
class ContextSummary(Object):
    """Summary of the FPGA."""

    __slots__ = [
            # generic summaries: updated by 'SummaryUpdate'
            'ios',                  # list of IOType, (x, y), subblock
            'active_blocks',        # dict of block keys to active orientations
            'active_primitives',    # set of primitive keys
            'lut_sizes',            # set of LUT sizes
            # pass-specific summaries: updated by each specific run
            'vpr',                  # updated by VPR-related passes
            'yosys',                # updated by Yosys-related passes
            'rtl',                  # updated by RTL-related passes
            # additional summaries
            '__dict__',
            ]

# ----------------------------------------------------------------------------
# -- Architecture Context ----------------------------------------------------
# ----------------------------------------------------------------------------
class Context(Object):
    """The main interface to PRGA architecture description.

    Architecture context manages all resources created/added to the FPGA, including all modules, the
    routing graph, configration circuitry and more.

    Args:
        cfg_type (:obj:`str`): Configuration type

    Keyword Args:
        database (:obj:`MutableMapping` [:obj:`Hashable`, `AbstractModule` ]): The module database. If not set, a new
            database is created
        **kwargs: Custom attributes assigned to the created context 
    """

    __slots__ = [
            "_cfg_type",            # configuration type
            '_globals',             # global wires
            '_tunnels',             # direct inter-block tunnels
            '_segments',            # wire segments
            '_database',            # module database
            '_top',                 # logical top
            '_switch_database',     # switch database
            '_fasm_delegate',       # FASM delegate
            '_verilog_headers',     # Verilog header rendering tasks
            'summary',              # FPGA summary
            '__dict__']

    def __init__(self, cfg_type, *, database = None, **kwargs):
        self._cfg_type = cfg_type
        self._globals = OrderedDict()
        self._tunnels = OrderedDict()
        self._segments = OrderedDict()
        if database is None:
            self._new_database()
        else:
            self._database = database
        self._top = None
        self._verilog_headers = OrderedDict()
        self._add_verilog_header("prga_utils.vh", "stdlib/include/prga_utils.tmpl.vh")
        self.summary = ContextSummary()
        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def _new_database(self):
        database = self._database = OrderedDict()

        # 1. register built-in modules: LUTs
        for i in range(2, 9):
            lut = Module('lut' + str(i),
                    view = ModuleView.user,
                    is_cell = True,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.lut)
            in_ = ModuleUtils.create_port(lut, 'in', i, PortDirection.input_,
                    port_class = PrimitivePortClass.lut_in, vpr_combinational_sinks = ("out", ))
            out = ModuleUtils.create_port(lut, 'out', 1, PortDirection.output,
                    port_class = PrimitivePortClass.lut_out)
            NetUtils.connect(in_, out, fully = True)
            database[ModuleView.user, lut.key] = lut

        # 2. register built-in modules: D-flipflop
        if True:
            flipflop = Module('flipflop',
                    view = ModuleView.user,
                    is_cell = True,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.flipflop)
            clk = ModuleUtils.create_port(flipflop, 'clk', 1, PortDirection.input_,
                    is_clock = True, port_class = PrimitivePortClass.clock)
            D = ModuleUtils.create_port(flipflop, 'D', 1, PortDirection.input_,
                    port_class = PrimitivePortClass.D, clock = "clk")
            Q = ModuleUtils.create_port(flipflop, 'Q', 1, PortDirection.output,
                    port_class = PrimitivePortClass.Q, clock = "clk")
            NetUtils.connect(clk, [D, Q], fully = True)
            database[ModuleView.user, flipflop.key] = flipflop

        # 3. register built-in modules: I/O
        for class_ in (PrimitiveClass.inpad, PrimitiveClass.outpad):
            pad = Module(class_.name,
                    view = ModuleView.user,
                    is_cell = True,
                    module_class = ModuleClass.primitive,
                    primitive_class = class_)
            if class_.is_inpad:
                ModuleUtils.create_port(pad, 'inpad', 1, PortDirection.output)
            else:
                ModuleUtils.create_port(pad, 'outpad', 1, PortDirection.input_)
            database[ModuleView.user, pad.key] = pad

        # 4. register dual-mode I/O
        if True:
            pad = self.create_multimode("iopad")
            pad.create_input("outpad", 1)
            pad.create_output("inpad", 1)

            mode = pad.create_mode("inpad")
            inst = mode.instantiate(self.primitives["inpad"], "pad")
            mode.connect(inst.pins["inpad"], mode.ports["inpad"])
            mode.commit()

            mode = pad.create_mode("outpad")
            inst = mode.instantiate(self.primitives["outpad"], "pad")
            mode.connect(mode.ports["outpad"], inst.pins["outpad"])
            mode.commit()
            database[ModuleView.user, "iopad"] = pad.commit()

        # 5. register stdlib logical designs
        # TODO: add as physical designs as well
        for d in ("prga_ram_1r1w", "prga_fifo", "prga_fifo_resizer", "prga_fifo_lookahead_buffer",
                "prga_fifo_adapter", "prga_byteaddressable_reg"):
            self._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    verilog_template = "stdlib/{}.v".format(d))
        ModuleUtils.instantiate(self._database[ModuleView.logical, "prga_fifo"],
                self._database[ModuleView.logical, "prga_ram_1r1w"], "ram")
        ModuleUtils.instantiate(self._database[ModuleView.logical, "prga_fifo_resizer"],
                self._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(self._database[ModuleView.logical, "prga_fifo_adapter"],
                self._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")

    def _add_verilog_header(self, f, template, **parameters):
        """Add a Verilog header. This rendering task will be collected via the `VerilogCollection` pass."""
        self._verilog_headers[f] = template, parameters

    # == low-level API =======================================================
    @property
    def database(self):
        """:obj:`Mapping` [:obj:`tuple` [`ModuleView`, :obj:`Hashable` ], `AbstractModule` ]: Module database."""
        return ReadonlyMappingProxy(self._database)

    @property
    def switch_database(self):
        """`AbstractSwitchDatabase`: Switch database."""
        try:
            return self._switch_database
        except AttributeError:
            raise PRGAInternalError("Switch database not set.\n"
                    "Possible cause: the context is not created by a configuration circuitry entry point.")

    @property
    def fasm_delegate(self):
        """`FASMDelegate`: FASM delegate for bitstream generation."""
        try:
            return self._fasm_delegate
        except AttributeError:
            raise PRGAInternalError("FASM delegate not set.\n"
                    "Possible cause: the context is not created by a configuration circuitry entry point.")

    def create_multimode(self, name, **kwargs):
        """Create a multi-mode primitive builder.

        Args:
            name (:obj:`str`): Name of the multi-mode primitive

        Keyword Args:
            **kwargs: Additional attributes to be associated with the primitive
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        primitive = self._database[ModuleView.user, name] = MultimodeBuilder.new(name, **kwargs)
        return MultimodeBuilder(self, primitive)

    def create_logical_primitive(self, name, *, is_cell = True, **kwargs):
        """`LogicalPrimitiveBuilder`: Create a logical primitive builder.

        Args:
            name (:obj:`str`): Name of the logical primitive

        Keyword Args:
            cell (:obj:`str`): If unset, the logical module is not a leaf cell
            **kwargs: Additional attributes to be associated with the primitive
        """
        if (ModuleView.logical, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        user_view = self._database.get( (ModuleView.user, name) )
        if user_view:
            primitive = self._database[ModuleView.logical, name] = LogicalPrimitiveBuilder.new_from_user_view(
                    user_view, is_cell = is_cell, **kwargs)
            return LogicalPrimitiveBuilder(self, primitive, user_view)
        else:
            primitive = self._database[ModuleView.logical, name] = LogicalPrimitiveBuilder.new(
                    name, is_cell = is_cell, **kwargs)
            return LogicalPrimitiveBuilder(self, primitive)

    # == high-level API ======================================================
    # -- Global Wires --------------------------------------------------------
    @property
    def globals(self):
        """:obj:`Mapping` [:obj:`str`, `Global` ]: A mapping from names to global wires."""
        return ReadonlyMappingProxy(self._globals)

    def create_global(self, name, width = 1, *,
            is_clock = False, bind_to_position = None, bind_to_subblock = None):
        """Create a global wire.

        Args:
            name (:obj:`str`): Name of the global wire
            width (:obj:`int`): Number of bits in the global wire

        Keyword Args:
            is_clock (:obj:`bool`): If this global wire is a clock. A global clock must be 1-bit wide
            bind_to_position (:obj:`Position`): Assign the IOB at the position as the driver of this global wire. If
                not specified, use `Global.bind` to bind later
            bind_to_subblock (:obj:`int`): Assign the IOB with the sub-block ID as the driver of this global wire. If
                ``bind_to_position`` is specified, ``bind_to_subblock`` is ``0`` by default

        Returns:
            `Global`: The created global wire
        """
        if name in self._globals:
            raise PRGAAPIError("Global wire named '{}' is already created".format(name))
        elif width != 1:
            raise PRGAAPIError("Only 1-bit wide global wires are supported now")
        global_ = self._globals.setdefault(name, Global(name, width, is_clock))
        if bind_to_position is not None:
            global_.bind(bind_to_position, uno(bind_to_subblock, 0))
        return global_

    # -- Segments ------------------------------------------------------------
    @property
    def segments(self):
        """:obj:`Mapping` [:obj:`str`, `Global` ]: A mapping from names to global wires."""
        return ReadonlyMappingProxy(self._segments)

    def create_segment(self, name, width, length = 1):
        """Create a segment.

        Args:
            name (:obj:`str`): Name of the segment
            width (:obj:`int`): Number of instances of this segment per channel
            length (:obj:`int`): Length of the segment
        """
        if name in self._segments:
            raise PRGAAPIError("Segment named '{}' is already created".format(name))
        return self._segments.setdefault(name, Segment(name, width, length))

    # -- Direct Inter-Block Tunnels ------------------------------------------
    @property
    def tunnels(self):
        """:obj:`Mapping` [:obj:`str`, `DirectTunnel` ]: A mapping from names to direct inter-block tunnels."""
        return ReadonlyMappingProxy(self._tunnels)

    def create_tunnel(self, name, source, sink, offset):
        """Create a direct inter-block tunnel.

        Args:
            name (:obj:`str`): Name of the tunnel
            source (`Port`): Source of the tunnel. Must be a logic block output port
            sink (`Port`): Sink of the tunnel. Must be a logic block input port
            offset (:obj:`tuple` [:obj:`int`, :obj:`int`] ): Position of the source port relative to the sink port
                This definition is the opposite of how VPR defines a ``direct`` tag. In addition, ``offset`` is
                defined based on the position of the ports, not the blocks
        """
        if name in self._tunnels:
            raise PRGAAPIError("Direct tunnel named '{}' is already created".format(name))
        elif not source.parent.module_class.is_logic_block or not source.direction.is_output:
            raise PRGAAPIError("Source '{}' is not a logic block output port".format(source))
        elif not sink.parent.module_class.is_logic_block or not sink.direction.is_input:
            raise PRGAAPIError("Sink '{}' is not a logic block input port".format(source))
        return self._tunnels.setdefault(name, DirectTunnel(name, source, sink, offset))

    # -- Primitives ----------------------------------------------------------
    @property
    def primitives(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractModule` ]: A mapping from names to primitives."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_primitive,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    def create_primitive(self, name, **kwargs):
        """PrimitiveBuilder`: Create a primitive builder."""
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        primitive = self._database[ModuleView.user, name] = PrimitiveBuilder.new(name, **kwargs)
        return PrimitiveBuilder(self, primitive)

    def create_memory(self, name, addr_width, data_width, *, single_port = False, **kwargs):
        """Create a memory builder.

        Args:
            name (:obj:`str`): Name of the memory
            addr_width (:obj:`int`): Number of bits of the address ports
            data_width (:obj:`int`): Number of bits of the data ports

        Keyword Args:
            single_port (:obj:`bool`): Create one read/write port instead of two
            **kwargs: Additional attributes to be associated with the primitive
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        primitive = self._database[ModuleView.user, name] = PrimitiveBuilder.new_memory(name,
                addr_width, data_width, single_port = single_port, **kwargs)
        return PrimitiveBuilder(self, primitive)

    # -- Clusters ------------------------------------------------------------
    @property
    def clusters(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractModule` ]: A mapping from names to clusters."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_cluster,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    def create_cluster(self, name):
        """`ClusterBuilder`: Create a cluster builder."""
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        cluster = self._database[ModuleView.user, name] = ClusterBuilder.new(name)
        return ClusterBuilder(self, cluster)

    # -- IO Blocks -----------------------------------------------------------
    @property
    def io_blocks(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractModule` ]: A mapping from names to IO blocks."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_io_block,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    def create_io_block(self, name, capacity = 1, *, no_input = False, no_output = False):
        """`IOBlockBuilder`: Create an IO block builder."""
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        io_primitive = None
        if not no_input and not no_output:
            io_primitive = self.primitives['iopad']
        elif not no_input:
            io_primitive = self.primitives['inpad']
        elif not no_output:
            io_primitive = self.primitives['outpad']
        else:
            raise PRGAAPIError("At least one of 'no_input' and 'no_output' must be False.")
        iob = self._database[ModuleView.user, name] = IOBlockBuilder.new(name, capacity)
        builder = IOBlockBuilder(self, iob)
        builder.instantiate(io_primitive, 'io')
        return builder

    # -- Logic Blocks --------------------------------------------------------
    @property
    def logic_blocks(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractModule` ]: A mapping from names to logic blocks."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_logic_block,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    def create_logic_block(self, name, width = 1, height = 1):
        """`LogicBlockBuilder`: Create a logic block builder."""
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        clb = self._database[ModuleView.user, name] = LogicBlockBuilder.new(name, width, height)
        return LogicBlockBuilder(self, clb)

    # -- Connection Boxes ----------------------------------------------------
    def get_connection_box(self, block, orientation, position = None, *, identifier = None, dont_create = False):
        """Get the connection box at a specific location near ``block``.

        Args:
            block (`AbstractModule`): A logic/io block
            orientation (`Orientation`): One side of the block which the connection box is at
            position (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Position of the block which the connection box is at

        Keyword Args:
            identifier (:obj:`str`): If different connection boxes are needed for the same location near ``block``,
                use identifier to differentiate them
            dont_create (:obj:`bool`): If set, return ``None`` when the requested connection box is not already created
                instead of create it

        Return:
            `ConnectionBoxBuilder`:
        """
        key = ConnectionBoxBuilder._cbox_key(block, orientation, position, identifier)
        try:
            return ConnectionBoxBuilder(self, self._database[ModuleView.user, key])
        except KeyError:
            if dont_create:
                return None
            else:
                return ConnectionBoxBuilder(self, self._database.setdefault((ModuleView.user, key),
                        ConnectionBoxBuilder.new(block, orientation, position, identifier = identifier)))

    # -- Switch Boxes --------------------------------------------------------
    def get_switch_box(self, corner, *, identifier = None, dont_create = False):
        """Get the switch box at a specific corner.

        Args:
            corner (`Corner`): On which corner of a tile is the switch box

        Keyword Args:
            identifier (:obj:`str`): If different switches boxes are needed for the same corner of a tile,
                use identifier to differentiate them
            dont_create (:obj:`bool`): If set, return ``None`` when the requested switch box is not already created
                instead of create it

        Return:
            `SwitchBoxBuilder`:
        """
        key = SwitchBoxBuilder._sbox_key(corner, identifier)
        try:
            return SwitchBoxBuilder(self, self._database[ModuleView.user, key])
        except KeyError:
            if dont_create:
                return None
            else:
                return SwitchBoxBuilder(self, self._database.setdefault((ModuleView.user, key),
                    SwitchBoxBuilder.new(corner, identifier = identifier)))

    # -- Arrays --------------------------------------------------------------
    @property
    def arrays(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractModule` ]: A mapping from names to arrays."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_array,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    @property
    def top(self):
        """`AbstractModule`: Logical top-level array."""
        return self._top

    @top.setter
    def top(self, v):
        self._top = v

    def create_array(self, name, width = 1, height = 1, *,
            set_as_top = None, edge = None, hierarchical = False):
        """`LeafArrayBuilder`: Create an leaf array builder."""
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        builder_factory = NonLeafArrayBuilder if hierarchical else LeafArrayBuilder
        set_as_top = uno(set_as_top, self._top is None)
        edge = uno(edge, OrientationTuple(True) if set_as_top else OrientationTuple(False))
        if set_as_top and not all(edge):
            raise PRGAAPIError("Top array must have an all-True 'edge' settings")
        array = self._database[ModuleView.user, name] = builder_factory.new(name, width, height, edge = edge)
        if set_as_top:
            self._top = array
        return builder_factory(self, array)

    # -- Serialization -------------------------------------------------------
    def pickle(self, file_):
        """Pickle the architecture context into a file.

        Args:
            file_ (:obj:`str` or file-like object): output file or its name
        """
        if isinstance(file_, basestring):
            pickle.dump(self, open(file_, OpenMode.wb))
        else:
            pickle.dump(self, file_)

    def pickle_summary(self, file_):
        """Pickle the summary into a binary file.

        Args:
            file_ (:obj:`str` or file-like object): output file or its name
        """
        if isinstance(file_, basestring):
            pickle.dump(self.summary, open(file_, OpenMode.wb))
        else:
            pickle.dump(self.summary, file_)

    @classmethod
    def unpickle(cls, file_):
        """Unpickle a pickled architecture context.

        Args:
            file_ (:obj:`str` or file-like object): the pickled file
        """
        if isinstance(file_, basestring):
            return pickle.load(open(file_, OpenMode.rb))
        else:
            return pickle.load(file_)
