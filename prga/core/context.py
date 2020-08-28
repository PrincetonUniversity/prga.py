# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import (Global, Segment, ModuleClass, PrimitiveClass, PrimitivePortClass, ModuleView, OrientationTuple,
        DirectTunnel)
from .builder import (LogicalPrimitiveBuilder, PrimitiveBuilder, MultimodeBuilder,
        ClusterBuilder, IOBlockBuilder, LogicBlockBuilder,
        SwitchBoxBuilder, TileBuilder, ArrayBuilder)
from ..integration import Integration
from ..netlist import TimingArcType, PortDirection, Module, ModuleUtils, NetUtils
from ..renderer import FileRenderer
from ..util import Object, ReadonlyMappingProxy, uno
from ..exception import PRGAAPIError, PRGAInternalError

import os, sys
sys.setrecursionlimit(2**16)

try:
    import cPickle as pickle
except ImportError:
    import pickle

import logging
_logger = logging.getLogger(__name__)

__all__ = ['ContextSummary', 'Context']

_VERSION = open(os.path.join(os.path.dirname(__file__), "..", "VERSION"), "r").read().strip()

# ----------------------------------------------------------------------------
# -- FPGA Summary ------------------------------------------------------------
# ----------------------------------------------------------------------------
class ContextSummary(Object):
    """Summary of the FPGA."""

    __slots__ = [
            'cwd',                  # root directory of the project
            # generic summaries: updated by 'SummaryUpdate'
            'ios',                  # list of `IO` s
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

    Args:
        cfg_type (:obj:`str`): Configuration type

    Keyword Args:
        database (:obj:`MutableMapping` [:obj:`Hashable`, `Module` ]): The module database. If not set, a new
            database is created
        **kwargs: Custom attributes assigned to the created context 

    Architecture context manages all resources created/added to the FPGA, including all modules, the
    routing graph, configration circuitry and more.
    """

    __slots__ = [
            "_cfg_type",            # configuration type
            '_globals',             # global wires
            '_tunnels',             # direct inter-block tunnels
            '_segments',            # wire segments
            '_database',            # module database
            '_top',                 # fpga top in user view
            '_system_top',          # system top in logical view
            '_switch_database',     # switch database
            '_fasm_delegate',       # FASM delegate
            '_verilog_headers',     # Verilog header rendering tasks
            'summary',              # FPGA summary
            "version",              # version of the context
            # non-persistent variables
            'cwd',                  # root path of the context. Set when unpickled/created
            '__dict__']

    def __init__(self, cfg_type, *, database = None, **kwargs):
        self._cfg_type = cfg_type
        self._globals = OrderedDict()
        self._tunnels = OrderedDict()
        self._segments = OrderedDict()
        self._top = None
        self._system_top = None
        self._verilog_headers = OrderedDict()
        if database is None:
            self._new_database()
        else:
            self._database = database
        self.summary = ContextSummary()
        self.version = _VERSION
        self.summary.cwd = self.cwd = os.getcwd()
        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def _add_verilog_header(self, f, template, **parameters):
        """Add a Verilog header. This rendering task will be collected via the `VerilogCollection` pass.
        
        Args:
            f (:obj:`str`): Name of the output file
            template (:obj:`str`): Name of the template or source file

        Keyword Args:
            **parameters: Extra parameters for the template
        """
        self._verilog_headers[f] = template, parameters

    def _new_database(self):
        database = self._database = OrderedDict()

        # 1. register built-in modules: LUTs
        for i in range(2, 9):
            lut = Module('lut' + str(i),
                    is_cell = True,
                    view = ModuleView.user,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.lut)
            in_ = ModuleUtils.create_port(lut, 'in', i, PortDirection.input_,
                    port_class = PrimitivePortClass.lut_in)
            out = ModuleUtils.create_port(lut, 'out', 1, PortDirection.output,
                    port_class = PrimitivePortClass.lut_out)
            NetUtils.create_timing_arc(TimingArcType.comb_matrix, in_, out)
            database[ModuleView.user, lut.key] = lut

        # 2. register built-in modules: D-flipflop
        if True:
            flipflop = Module('flipflop',
                    is_cell = True,
                    view = ModuleView.user,
                    module_class = ModuleClass.primitive,
                    primitive_class = PrimitiveClass.flipflop)
            clk = ModuleUtils.create_port(flipflop, 'clk', 1, PortDirection.input_,
                    is_clock = True, port_class = PrimitivePortClass.clock)
            D = ModuleUtils.create_port(flipflop, 'D', 1, PortDirection.input_,
                    port_class = PrimitivePortClass.D)
            Q = ModuleUtils.create_port(flipflop, 'Q', 1, PortDirection.output,
                    port_class = PrimitivePortClass.Q)
            NetUtils.create_timing_arc(TimingArcType.seq_end, clk, D)
            NetUtils.create_timing_arc(TimingArcType.seq_start, clk, Q)
            database[ModuleView.user, flipflop.key] = flipflop

        # 3. register built-in modules: I/O
        for class_ in (PrimitiveClass.inpad, PrimitiveClass.outpad):
            pad = Module(class_.name,
                    is_cell = True,
                    view = ModuleView.user,
                    module_class = ModuleClass.primitive,
                    primitive_class = class_)
            if class_.is_inpad:
                ModuleUtils.create_port(pad, 'inpad', 1, PortDirection.output)
            else:
                ModuleUtils.create_port(pad, 'outpad', 1, PortDirection.input_)
            database[ModuleView.user, pad.key] = pad

        # 4. register dual-mode I/O
        if True:
            pad = self.build_multimode("iopad")
            pad.create_input("outpad", 1)
            pad.create_output("inpad", 1)

            mode = pad.build_mode("inpad")
            inst = mode.instantiate(self.primitives["inpad"], "pad")
            mode.connect(inst.pins["inpad"], mode.ports["inpad"])
            mode.commit()

            mode = pad.build_mode("outpad")
            inst = mode.instantiate(self.primitives["outpad"], "pad")
            mode.connect(mode.ports["outpad"], inst.pins["outpad"])
            mode.commit()
            database[ModuleView.user, "iopad"] = pad.commit()

        # 5. register built-in designs
        FileRenderer._register_lib(self)
        Integration._register_lib(self)

    # == low-level API =======================================================
    @property
    def system_top(self):
        """`Module`: System top module in logical view."""
        return self._system_top

    @system_top.setter
    def system_top(self, v):
        self._system_top = v

    @property
    def database(self):
        """:obj:`Mapping` [:obj:`tuple` [`ModuleView`, :obj:`Hashable` ], `Module` ]: Module database."""
        return ReadonlyMappingProxy(self._database)

    @property
    def switch_database(self):
        """`AbstractSwitchDatabase`: Switch database.
        
        This is usually set by the configuration circuitry entry point, e.g., `Scanchain`.
        """
        try:
            return self._switch_database
        except AttributeError:
            raise PRGAInternalError("Switch database not set.\n"
                    "Possible cause: the context is not created by a configuration circuitry entry point.")

    @property
    def fasm_delegate(self):
        """`FASMDelegate`: FASM delegate for bitstream generation.
        
        This is usually set by the configuration circuitry entry point, e.g., `Scanchain`.
        """
        try:
            return self._fasm_delegate
        except AttributeError:
            raise PRGAInternalError("FASM delegate not set.\n"
                    "Possible cause: the context is not created by a configuration circuitry entry point.")

    def build_multimode(self, name, **kwargs):
        """Create a multi-mode primitive in user view.

        Args:
            name (:obj:`str`): Name of the multi-mode primitive

        Keyword Args:
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `MultimodeBuilder`:
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        primitive = self._database[ModuleView.user, name] = MultimodeBuilder.new(name, **kwargs)
        return MultimodeBuilder(self, primitive)

    def build_logical_primitive(self, name, *, not_cell = False, **kwargs):
        """Create a primitive in logical view.

        Args:
            name (:obj:`str`): Name of the logical primitive

        Keyword Args:
            not_cell (:obj:`bool`): If set, the logical primitive is not a cell module
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `LogicalPrimitiveBuilder`:
        """
        if (ModuleView.logical, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        user_view = self._database.get( (ModuleView.user, name) )
        if user_view:
            primitive = self._database[ModuleView.logical, name] = LogicalPrimitiveBuilder.new_from_user_view(
                    user_view, not_cell = not_cell, **kwargs)
            return LogicalPrimitiveBuilder(self, primitive, user_view)
        else:
            primitive = self._database[ModuleView.logical, name] = LogicalPrimitiveBuilder.new(
                    name, not_cell = not_cell, **kwargs)
            return LogicalPrimitiveBuilder(self, primitive)

    # == high-level API ======================================================
    # -- Global Wires --------------------------------------------------------
    @property
    def globals_(self):
        """:obj:`Mapping` [:obj:`str`, `Global` ]: A mapping from names to global wires."""
        return ReadonlyMappingProxy(self._globals)

    def create_global(self, name, width = 1, *,
            is_clock = False, bind_to_position = None, bind_to_subtile = None):
        """Create a global wire.

        Args:
            name (:obj:`str`): Name of the global wire
            width (:obj:`int`): Number of bits in the global wire

        Keyword Args:
            is_clock (:obj:`bool`): Set to ``True`` if this global wire is a clock. A global clock must be 1-bit wide
            bind_to_position (:obj:`Position`): Assign the IOB at the position as the driver of this global wire. If
                not specified, use `Global.bind` to bind later
            bind_to_subtile (:obj:`int`): Assign the IOB with the subtile ID as the driver of this global wire. If
                ``bind_to_position`` is specified, ``bind_to_subtile`` is ``0`` by default

        Returns:
            `Global`: The created global wire
        """
        if name in self._globals:
            raise PRGAAPIError("Global wire named '{}' is already created".format(name))
        elif width != 1:
            raise PRGAAPIError("Only 1-bit wide global wires are supported now")
        global_ = self._globals.setdefault(name, Global(name, width, is_clock))
        if bind_to_position is not None:
            global_.bind(bind_to_position, uno(bind_to_subtile, 0))
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

        Returns:
            `prga.core.common.Segment`:
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

        Returns:
            `DirectTunnel`:
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
        """:obj:`Mapping` [:obj:`str`, `Module` ]: A mapping from names to primitives."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_primitive,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    def build_primitive(self, name, **kwargs):
        """Create a primitive in user view.

        Args:
            name (:obj:`str`): Name of the primitive

        Keyword Args:
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `PrimitiveBuilder`:
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        primitive = self._database[ModuleView.user, name] = PrimitiveBuilder.new(name, **kwargs)
        return PrimitiveBuilder(self, primitive)

    def build_memory(self, name, addr_width, data_width, *, single_port = False, **kwargs):
        """Create a memory in user view.

        Args:
            name (:obj:`str`): Name of the memory
            addr_width (:obj:`int`): Number of bits of the address ports
            data_width (:obj:`int`): Number of bits of the data ports

        Keyword Args:
            single_port (:obj:`bool`): Create one read/write port instead of two
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `PrimitiveBuilder`:
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        primitive = self._database[ModuleView.user, name] = PrimitiveBuilder.new_memory(name,
                addr_width, data_width, single_port = single_port, **kwargs)
        return PrimitiveBuilder(self, primitive)

    # -- Clusters ------------------------------------------------------------
    @property
    def clusters(self):
        """:obj:`Mapping` [:obj:`str`, `Module` ]: A mapping from names to clusters."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_cluster,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    def build_cluster(self, name, **kwargs):
        """Create a cluster in user view.

        Args:
            name (:obj:`str`): Name of the cluster

        Keyword Args:
            **kwargs: Additional attributes to be associated with the cluster. Beware that these attributes are
                **NOT** carried over to the logical view automatically generated by `TranslationPass`
        
        Returns:
            `ClusterBuilder`:
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        cluster = self._database[ModuleView.user, name] = ClusterBuilder.new(name, **kwargs)
        return ClusterBuilder(self, cluster)

    # -- IO/Logic Blocks -----------------------------------------------------
    @property
    def blocks(self):
        """:obj:`Mapping` [:obj:`str`, `Module` ]: A mapping from names to blocks."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_block,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    def build_io_block(self, name, *, input_only = False, output_only = False, **kwargs):
        """Create an IO block in user view.

        Args:
            name (:obj:`str`): Name of the IO block

        Keyword Args:
            input_only (:obj:`bool`): If set to ``True``, the IO block is output-only
            output_only (:obj:`bool`): If set to ``True``, the IO block is input-only
            **kwargs: Additional attributes to be associated with the block. Beware that these attributes are
                **NOT** carried over to the logical view automatically generated by `TranslationPass`
        
        Returns:
            `IOBlockBuilder`:
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        io_primitive = None
        if input_only and output_only:
            raise PRGAAPIError("'input_only' and 'output_only' are mutual-exclusive.")
        elif output_only:
            io_primitive = self.primitives['outpad']
        elif input_only:
            io_primitive = self.primitives['inpad']
        else:
            io_primitive = self.primitives['iopad']
        iob = self._database[ModuleView.user, name] = IOBlockBuilder.new(name, **kwargs)
        builder = IOBlockBuilder(self, iob)
        builder.instantiate(io_primitive, 'io')
        return builder

    def build_logic_block(self, name, width = 1, height = 1, **kwargs):
        """Create a logic block in user view.

        Args:
            name (:obj:`str`): Name of the logic block
            width (:obj:`int`): Width of the logic block
            height (:obj:`int`): Height of the logic block

        Keyword Args:
            **kwargs: Additional attributes to be associated with the block. Beware that these attributes are
                **NOT** carried over to the logical view automatically generated by `TranslationPass`
        
        Returns:
            `LogicBlockBuilder`:
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        clb = self._database[ModuleView.user, name] = LogicBlockBuilder.new(name, width, height, **kwargs)
        return LogicBlockBuilder(self, clb)

    # -- Tiles ---------------------------------------------------------------
    @property
    def tiles(self):
        """:obj:`Mapping` [:obj:`str`, `Module` ]: A mapping from names to tiles."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_tile,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    def build_tile(self, block = None, capacity = None, *,
            width = 1, height = 1, name = None,
            edge = OrientationTuple(False), disallow_segments_passthru = False, **kwargs):
        """Create a tile in user view.

        Args:
            block (`Module`): A logic/IO block. If specified, the tile is created based on it.
            capacity (:obj:`int`): Number of block instances in the tile. This affectes the `capacity`_ attribute on
                output VPR specs.

        Keyword Args:
            width (:obj:`int`): Width of the tile. Overriden by the width of ``block`` if ``block`` is specified.
            height (:obj:`int`): Height of the tile. Overriden by the height of ``block`` if ``block`` is specified.
            name (:obj:`str`): Name of the tile. ``"tile_{block}"`` by default if ``block`` is specified.
            edge (`OrientationTuple` [:obj:`bool` ]): Specify on which edges of the top-level is the tile. This
                affects if IO blocks can be instantiated
            disallow_segments_passthru (:obj:`bool`): If set to ``True``, routing tracks are not allowed to run over
                the tile
            **kwargs: Additional attributes assigned to the tile

        Returns:
            `TileBuilder`:

        .. _capacity:
            https://docs.verilogtorouting.org/en/latest/arch/reference/#tag-%3Csub\_tilename
        """
        if block is not None:
            if not block.module_class.is_block:
                raise PRGAAPIError("{} is not a logic/IO block".format(block))
            name = uno(name, "tile_{}".format(block.name))
        elif name is None:
            raise PRGAAPIError("'name' is required if 'block' is not specified")
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        if block is None:
            tile = self._database[ModuleView.user, name] = TileBuilder.new(name, width, height,
                    disallow_segments_passthru = disallow_segments_passthru, edge = edge, **kwargs)
            return TileBuilder(self, tile)
        else:
            tile = self._database[ModuleView.user, name] = TileBuilder.new(name, block.width, block.height,
                    disallow_segments_passthru = disallow_segments_passthru, edge = edge, **kwargs)
            builder = TileBuilder(self, tile)
            builder.instantiate(block, capacity)
            return builder

    # -- Switch Boxes --------------------------------------------------------
    def build_switch_box(self, corner, *,
            identifier = None, dont_create = False, **kwargs):
        """Get or create a switch box in user view at a specific corner.

        Args:
            corner (`Corner`): On which corner of a tile is the switch box

        Keyword Args:
            identifier (:obj:`str`): If different switches boxes are needed for the same corner, use identifier to
                differentiate them
            dont_create (:obj:`bool`): If set to ``True``, return ``None`` when the requested switch box is not
                already created
            **kwargs: Additional attributes to be associated with the box if created. Beware that these
                attributes are **NOT** carried over to the logical view automatically generated by `TranslationPass`

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
                    SwitchBoxBuilder.new(corner, identifier = identifier, **kwargs)))

    # -- Arrays --------------------------------------------------------------
    @property
    def arrays(self):
        """:obj:`Mapping` [:obj:`str`, `Module` ]: A mapping from names to arrays."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_array,
                lambda k: (ModuleView.user, k), lambda k: k[1])

    @property
    def top(self):
        """`Module`: Top-level array in user view."""
        return self._top

    @top.setter
    def top(self, v):
        self._top = v

    def build_array(self, name, width = 1, height = 1, *,
            set_as_top = None, edge = None, **kwargs):
        """Create an array in user view.

        Args:
            name (:obj:`str`): Name of the array
            width (:obj:`int`): Width of the array
            height (:obj:`int`): Height of the array

        Keyword Args:
            set_as_top (:obj:`bool`): By default, the first array created is set as the top-level array. If this is
                not intended, set this boolean value explicitly
            edge (`OrientationTuple` [:obj:`bool` ]): Specify on which edges of the top-level is the array. This
                affects where IO blocks can be instantiated, and how some switch boxes are created
            **kwargs: Additional attributes to be associated with the array. Beware that these
                attributes are **NOT** carried over to the logical view automatically generated by `TranslationPass`

        Returns:
            `ArrayBuilder`:
        """
        if (ModuleView.user, name) in self._database:
            raise PRGAAPIError("Module with name '{}' already created".format(name))
        set_as_top = uno(set_as_top, self._top is None)
        edge = uno(edge, OrientationTuple(True) if set_as_top else OrientationTuple(False))
        if set_as_top and not all(edge):
            raise PRGAAPIError("Top array must have an all-True 'edge' settings")
        array = self._database[ModuleView.user, name] = ArrayBuilder.new(name, width, height,
                edge = edge, **kwargs)
        if set_as_top:
            self._top = array
        return ArrayBuilder(self, array)

    # -- Serialization -------------------------------------------------------
    def pickle(self, file_):
        """Pickle the architecture context into a file.

        Args:
            file_ (:obj:`str` or file-like object): output file or its name
        """
        cwd = self.cwd
        del self.cwd
        del self.summary.cwd
        if isinstance(file_, basestring):
            pickle.dump(self, open(file_, OpenMode.wb))
            _logger.info("Context pickled to {}".format(file_))
        else:
            pickle.dump(self, file_)
            _logger.info("Context pickled to {}".format(file_.name))
        self.summary.cwd = self.cwd = cwd

    def pickle_summary(self, file_):
        """Pickle the summary into a binary file.

        Args:
            file_ (:obj:`str` or file-like object): output file or its name
        """
        if isinstance(file_, basestring):
            pickle.dump(self.summary, open(file_, OpenMode.wb))
            _logger.info("Context summary pickled to {}".format(file_))
        else:
            pickle.dump(self.summary, file_)
            _logger.info("Context summary pickled to {}".format(file_.name))

    @classmethod
    def unpickle(cls, file_):
        """Unpickle a pickled architecture context.

        Args:
            file_ (:obj:`str` or file-like object): the pickled file
        """
        name = file_ if isinstance(file_, basestring) else file_.name
        obj = pickle.load(open(file_, OpenMode.rb) if isinstance(file_, basestring) else file_)
        if isinstance(obj, cls):
            if (version := getattr(obj, "version", None)) != _VERSION:
                if version is None:
                    raise PRGAAPIError(
                            "The context is pickled by an old PRGA release, not supported by current version {}"
                            .format(_VERSION))
                else:
                    raise PRGAAPIError(
                            "The context is pickled by PRGA version {}, not supported by current version {}"
                            .format(version, _VERSION))
            obj.summary.cwd = obj.cwd = os.path.dirname(os.path.abspath(name))
        _logger.info("Context {}unpickled from {}".format(
            "summary " if isinstance(obj, ContextSummary) else "", name))
        return obj
