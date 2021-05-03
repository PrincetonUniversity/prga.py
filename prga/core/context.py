# -*- encoding: ascii -*-

from .common import (Global, Segment, ModuleClass, PrimitiveClass, PrimitivePortClass, ModuleView, OrientationTuple,
        DirectTunnel)
from .builder.primitive import DesignViewPrimitiveBuilder, PrimitiveBuilder, MultimodeBuilder
from .builder.block import SliceBuilder, LogicBlockBuilder, IOBlockBuilder
from .builder.box import ConnectionBoxBuilder, SwitchBoxBuilder
from .builder.array.tile import TileBuilder
from .builder.array.array import ArrayBuilder
from ..netlist import TimingArcType, PortDirection, Module, ModuleUtils, NetUtils
from ..renderer.renderer import FileRenderer
from ..renderer.lib import BuiltinCellLibrary
from ..passes.vpr.delegate import FASMDelegate
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

VERSION = open(os.path.join(os.path.dirname(__file__), "..", "VERSION"), "r").read().strip()

# ----------------------------------------------------------------------------
# -- FPGA Summary ------------------------------------------------------------
# ----------------------------------------------------------------------------
class ContextSummary(Object):
    """Summary of the FPGA."""

    __slots__ = [
            'cwd',                  # root directory of the project
            # generic summaries: updated by 'SummaryUpdate'
            'prog_type',            # programming circuitry type
            'prog_support_magic_checker',   # set if the programming circuitry type supports Magic bitstream checked
                                            # in simulation
            'top',                  # top-level FPGA module name
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
        template_search_paths (:obj:`str` or :obj:`Container` [:obj:`str` ]): Additional search paths other than the
            default ones

    Keyword Args:
        **kwargs: Custom attributes assigned to the context 

    Architecture context manages all resources created/added to the FPGA, including all modules, the
    routing graph, programming circuitry and more.
    """

    __slots__ = [
            '_prog_entry',          # programming circuitry entry point
            '_globals',             # global wires
            '_tunnels',             # direct inter-block tunnels
            '_segments',            # wire segments
            '_database',            # module database
            '_top',                 # fpga top in abstract view
            '_switch_delegate',     # switch delegate
            '_fasm_delegate',       # FASM delegate
            '_verilog_headers',     # Verilog header rendering tasks
            'summary',              # FPGA summary
            "version",              # version of the context
            'template_search_paths',    # File renderer template search paths
            '__dict__',

            # non-persistent variables
            'cwd',                  # root path of the context. Set when unpickled/created
            '_renderer',            # File renderer. Created on demand
            ]

    def __init__(self, template_search_paths = None, **kwargs):
        self._globals = {}
        self._tunnels = {}
        self._segments = {}
        self._top = None
        self._fasm_delegate = FASMDelegate()
        self._verilog_headers = {}

        if template_search_paths is None:
            self.template_search_paths = []
        elif isinstance(template_search_paths, str):
            self.template_search_paths = [template_search_paths]
        else:
            self.template_search_paths = list(iter(template_search_paths))

        self.version = VERSION
        self.summary = ContextSummary()
        self.summary.cwd = self.cwd = os.getcwd()
        self.summary.prog_type = "abstract"
        self.summary.prog_support_magic_checker = False

        for k, v in kwargs.items():
            setattr(self, k, v)

        self._database = {}
        BuiltinCellLibrary.install_abstract(self)

    # == low-level API =======================================================
    @property
    def database(self):
        """:obj:`Mapping` [:obj:`tuple` [`ModuleView`, :obj:`Hashable` ], `Module` ]: Module database."""
        return ReadonlyMappingProxy(self._database)

    @property
    def renderer(self):
        """`FileRenderer`: File renderer of the current context."""
        try:
            return self._renderer
        except AttributeError:
            r = self._renderer = FileRenderer(*self.template_search_paths)
            return r

    @renderer.setter
    def renderer(self, r):
        if r is None:
            try:
                del self._renderer
            except AttributeError:
                pass
        else:
            self._renderer = r

    @property
    def prog_entry(self):
        """`AbstractProgCircuitryEntry`: Programming circuitry type entry point."""
        try:
            return self._prog_entry
        except AttributeError:
            raise PRGAInternalError("Programming circuitry not set.\n"
                    "Possible cause: the context is not materialized by a programming circuitry entry point yet.")

    @property
    def switch_delegate(self):
        """`SwitchDelegate`: Switch delegate.
        
        This is usually set by the programming circuitry entry point, e.g., `Scanchain`.
        """
        try:
            return self._switch_delegate
        except AttributeError:
            raise PRGAInternalError("Switch delegate not set.\n"
                    "Possible cause: the context is not materialized by a programming circuitry entry point yet.")

    @property
    def fasm_delegate(self):
        """`FASMDelegate`: FASM delegate for bitstream generation."""
        return self._fasm_delegate

    def _add_module(self, module):
        """Add ``module`` into the database of this context.

        Args:
            module (`Module`):

        Returns:
            `Module`:
        """
        if d := self._database.get( (module.view, module.key), None ):
            raise PRGAAPIError("Module ({} view) with key '{}' already created: {}"
                    .format(module.view.name, module.key, d))
        self._database[module.view, module.key] = module
        return module

    def build_multimode(self, name, **kwargs):
        """Create a multi-mode primitive in abstract view.

        Args:
            name (:obj:`str`): Name of the multi-mode primitive

        Keyword Args:
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `MultimodeBuilder`:
        """
        return MultimodeBuilder(self, self._add_module(MultimodeBuilder.new(name, **kwargs)))

    def build_design_view_primitive(self, name, *, key = None, not_cell = False, **kwargs):
        """Create a primitive in design view.

        Args:
            name (:obj:`str`): Name of the design-view primitive

        Keyword Args:
            key (:obj:`Hashable`): Key of the created module in the database. Same as ``name`` if not set, or same as
                the abstract view if the abstract view already exists
            not_cell (:obj:`bool`): If set, the design-view primitive is not a cell module
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `DesignViewPrimitiveBuilder`:
        """
        key = uno(key, name)
        if abstract_view := self._database.get( (ModuleView.abstract, key) ):
            return DesignViewPrimitiveBuilder(self,
                    self._add_module(DesignViewPrimitiveBuilder.new_from_abstract_view(
                        abstract_view, not_cell = not_cell, **kwargs)),
                    abstract_view)
        else:
            return DesignViewPrimitiveBuilder(self,
                    self._add_module(DesignViewPrimitiveBuilder.new(name,
                        key = key, not_cell = not_cell, **kwargs)))

    # == high-level API ======================================================
    # -- Verilog headers -----------------------------------------------------
    def add_verilog_header(self, f, template, *deps,
            key = None, **parameters):
        """Add a Verilog header. This rendering task will be collected via the `VerilogCollection` pass.
        
        Args:
            f (:obj:`str`): Name of the output file
            template (:obj:`str`): Name of the template or source file
            *deps (:obj:`str`): Other header files that this one depends on

        Keyword Args:
            key (:obj:`str`): A key to index this verilog header. Default to ``f``
            **parameters: Extra parameters for the template
        """
        self._verilog_headers[uno(key, f)] = f, template, set(deps), parameters

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
        """:obj:`Mapping` [:obj:`str` or :obj:`Hashable`, `Module` ]: A mapping from keys (names) to primitives."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_primitive,
                lambda k: (ModuleView.abstract, k), lambda k: k[1])

    def build_primitive(self, name, *, vpr_model = None, **kwargs):
        """Create a primitive in abstract view.

        Args:
            name (:obj:`str`): Name of the primitive

        Keyword Args:
            vpr_model (:obj:`str`): Name of the VPR model. Default: "m_{name}"
            **kwargs: Additional attributes to be associated with the primitive

        Returns:
            `PrimitiveBuilder`:
        """
        return PrimitiveBuilder(self, self._add_module(PrimitiveBuilder.new(name, vpr_model = vpr_model, **kwargs)))

    def create_memory(self, addr_width, data_width, *,
            name = None, vpr_model = None, memory_type = "1r1w", **kwargs):
        """Create a memory in abstract view.

        Args:
            addr_width (:obj:`int`): Number of bits of the address ports
            data_width (:obj:`int`): Number of bits of the data ports

        Keyword Args:
            name (:obj:`str`): Name of the memory module. Default: "ram_{memory_type}_a{addr_width}d{data_width}"
            vpr_model (:obj:`str`): Name of the VPR model. Default: "m_ram_{memory_type}"
            memory_type (:obj:`str`): ``"1r1w"``, ``"1rw"`` or ``"2rw"``. Default is ``"1r1w"``
            **kwargs: Additional attributes assigned to the primitive

        Returns:
            `Module`:
        """
        return BuiltinCellLibrary.create_memory(self, addr_width, data_width,
                name = name, vpr_model = vpr_model, memory_type = memory_type, **kwargs)

    def create_multimode_memory(self, core_addr_width, data_width, *,
            addr_width = None, name = None):
        """Create a multi-mode RAM.

        Args:
            core_addr_width (:obj:`int`): The address width of the single-mode, 1R1W RAM core behind the multi-mode
                logic
            data_width (:obj:`int`): The data width of the single-mode, 1R1W RAM core behind the multi-mode logic

        Keyword Args:
            name (:obj:`str`): Name of the multi-mode primitive. ``"fracram_a{addr_width}d{data_width}"`` by default.
            addr_width (:obj:`int`): The maximum address width. See notes for more information

        Returns:
            `Module`: User view of the multi-modal primitive
        
        Notes:
            This method builds a multi-mode, fracturable 1R1W RAM. For example,
            ``build_multimode_memory(ctx, 9, 64)`` creates a multimode primitive with the following modes:
            ``512x64b``, ``1K32b``, ``2K16b``, ``4K8b``, ``8K4b``, ``16K2b``, and ``32K1b``.

            If 1b is not the desired smallest data width, change ``addr_width`` to a number between
            ``core_addr_width`` and ``core_addr_width + floor(log2(data_width))``.

            When ``data_width`` is not a power of 2, the actual data width of each mode is determined by the actual
            address width. For example, ``build_multimode_memory(ctx, 9, 72)`` creates the following modes:
            ``512x72b``, ``1K36b``, ``2K18b``, ``4K9b``, ``8K4b``, ``16K2b``, ``32K1b``. Note that instead of a
            ``9K4b``, we got a ``8K4b``.
        """
        return BuiltinCellLibrary.create_multimode_memory(self, core_addr_width, data_width,
                addr_width = addr_width, name = name)

    def create_multiplier(self, width_a, width_b = None, *, name = None):
        """Create a basic combinational multiplier.

        Args:
            width_a (:obj:`int`): Width of the multiplier/multiplicand
            width_b (:obj:`int`): Width of the other multiplier/multiplicand. Equal to ``width_a`` if not set.

        Keyword Args:
            name (:obj:`str`): Name of the primitive. ``"mul_a{width_a}b{width_b}"`` by default.

        Returns:
            `Module`: User view of the multiplier
        """
        return BuiltinCellLibrary.create_multiplier(self, width_a, width_b, name = name)

    # -- Slices --------------------------------------------------------------
    @property
    def slices(self):
        """:obj:`Mapping` [:obj:`str` or :obj:`Hashable`, `Module` ]: A mapping from keys (names) to slices."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_slice,
                lambda k: (ModuleView.abstract, k), lambda k: k[1])

    def build_slice(self, name, **kwargs):
        """Create a slice in abstract view.

        Args:
            name (:obj:`str`): Name of the slice

        Keyword Args:
            **kwargs: Additional attributes to be associated with the slice. Beware that these attributes are
                **NOT** carried over to the design view automatically generated by `Translation`
        
        Returns:
            `SliceBuilder`:
        """
        return SliceBuilder(self, self._add_module(SliceBuilder.new(name, **kwargs)))

    # -- IO/Logic Blocks -----------------------------------------------------
    @property
    def blocks(self):
        """:obj:`Mapping` [:obj:`str` or :obj:`Hashable`, `Module` ]: A mapping from keys (names) to blocks."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_block,
                lambda k: (ModuleView.abstract, k), lambda k: k[1])

    def build_io_block(self, name, *, input_only = False, output_only = False, **kwargs):
        """Create an IO block in abstract view.

        Args:
            name (:obj:`str`): Name of the IO block

        Keyword Args:
            input_only (:obj:`bool`): If set to ``True``, the IO block is output-only
            output_only (:obj:`bool`): If set to ``True``, the IO block is input-only
            **kwargs: Additional attributes to be associated with the block. Beware that these attributes are
                **NOT** carried over to the design view automatically generated by `Translation`
        
        Returns:
            `IOBlockBuilder`:
        """
        io_primitive = None
        if input_only and output_only:
            raise PRGAAPIError("'input_only' and 'output_only' are mutual-exclusive.")
        elif output_only:
            io_primitive = self.primitives['outpad']
        elif input_only:
            io_primitive = self.primitives['inpad']
        else:
            io_primitive = self.primitives['iopad']

        builder = IOBlockBuilder(self, self._add_module(IOBlockBuilder.new(name, **kwargs)))
        builder.instantiate(io_primitive, 'io')
        return builder

    def build_logic_block(self, name, width = 1, height = 1, **kwargs):
        """Create a logic block in abstract view.

        Args:
            name (:obj:`str`): Name of the logic block
            width (:obj:`int`): Width of the logic block
            height (:obj:`int`): Height of the logic block

        Keyword Args:
            **kwargs: Additional attributes to be associated with the block. Beware that these attributes are
                **NOT** carried over to the design view automatically generated by `Translation`
        
        Returns:
            `LogicBlockBuilder`:
        """
        return LogicBlockBuilder(self, self._add_module(LogicBlockBuilder.new(name, width, height, **kwargs)))

    # -- Tiles ---------------------------------------------------------------
    @property
    def tiles(self):
        """:obj:`Mapping` [:obj:`str` or :obj:`Hashable`, `Module` ]: A mapping from keys (names) to tiles."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_tile,
                lambda k: (ModuleView.abstract, k), lambda k: k[1])

    def build_tile(self, block = None, capacity = None, *,
            width = 1, height = 1, name = None,
            edge = OrientationTuple(False), disallow_segments_passthru = False, **kwargs):
        """Create a tile in abstract view.

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
        if block is None:
            return TileBuilder(self, self._add_module(TileBuilder.new(name, width, height,
                    disallow_segments_passthru = disallow_segments_passthru, edge = edge, **kwargs)))
        else:
            builder = TileBuilder(self, self._add_module(TileBuilder.new(name, block.width, block.height,
                    disallow_segments_passthru = disallow_segments_passthru, edge = edge, **kwargs)))
            builder.instantiate(block, capacity)
            return builder

    # -- Switch Boxes --------------------------------------------------------
    def build_switch_box(self, corner, *,
            identifier = None, dont_create = False, **kwargs):
        """Get or create a switch box in abstract view at a specific corner.

        Args:
            corner (`Corner`): On which corner of a tile is the switch box

        Keyword Args:
            identifier (:obj:`str`): If different switches boxes are needed for the same corner, use identifier to
                differentiate them
            dont_create (:obj:`bool`): If set to ``True``, return ``None`` when the requested switch box is not
                already created
            **kwargs: Additional attributes to be associated with the box if created. Beware that these
                attributes are **NOT** carried over to the design view automatically generated by `Translation`

        Return:
            `SwitchBoxBuilder`:
        """
        key = SwitchBoxBuilder._sbox_key(corner, identifier)
        try:
            return SwitchBoxBuilder(self, self._database[ModuleView.abstract, key])
        except KeyError:
            if dont_create:
                return None
            else:
                return SwitchBoxBuilder(self, self._database.setdefault((ModuleView.abstract, key),
                    SwitchBoxBuilder.new(corner, identifier = identifier, **kwargs)))

    # -- Arrays --------------------------------------------------------------
    @property
    def arrays(self):
        """:obj:`Mapping` [:obj:`str` or :obj:`Hashable`, `Module` ]: A mapping from keys (names) to arrays."""
        return ReadonlyMappingProxy(self._database, lambda kv: kv[1].module_class.is_array,
                lambda k: (ModuleView.abstract, k), lambda k: k[1])

    @property
    def top(self):
        """`Module`: Top-level array in abstract view."""
        return self._top

    @top.setter
    def top(self, v):
        self._top = v
        self.summary.top = v.name

    def build_array(self, name, width = 1, height = 1, *, set_as_top = None, edge = None, **kwargs):
        """Create an array in abstract view.

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
                attributes are **NOT** carried over to the design view automatically generated by `Translation`

        Returns:
            `ArrayBuilder`:
        """
        set_as_top = uno(set_as_top, self._top is None)
        edge = uno(edge, OrientationTuple(True) if set_as_top else OrientationTuple(False))
        if set_as_top and not all(edge):
            raise PRGAAPIError("Top array must have an all-True 'edge' settings")
        array = self._add_module(ArrayBuilder.new(name, width, height, edge = edge, **kwargs))
        if set_as_top:
            self.top = array
        return ArrayBuilder(self, array)

    # -- Serialization -------------------------------------------------------
    def pickle(self, file_):
        """Pickle the architecture context into a file.

        Args:
            file_ (:obj:`str` or file-like object): output file or its name
        """
        try:
            r = self._renderer
            del self._renderer
        except AttributeError:
            r = None

        cwd = self.cwd
        del self.cwd

        del self.summary.cwd

        if isinstance(file_, str):
            pickle.dump(self, open(file_, "wb"))
            _logger.info("Context pickled to {}".format(file_))
        else:
            pickle.dump(self, file_)
            _logger.info("Context pickled to {}".format(file_.name))

        self.summary.cwd = self.cwd = cwd

        if r is not None:
            self._renderer = r

    def pickle_summary(self, file_):
        """Pickle the summary into a binary file.

        Args:
            file_ (:obj:`str` or file-like object): output file or its name
        """
        if isinstance(file_, str):
            pickle.dump(self.summary, open(file_, "wb"))
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
        name = file_ if isinstance(file_, str) else file_.name
        obj = pickle.load(open(file_, "rb") if isinstance(file_, str) else file_)
        if isinstance(obj, cls):
            if (version := getattr(obj, "version", None)) != VERSION:
                if version is None:
                    raise PRGAAPIError(
                            "The context is pickled by an old PRGA release, not supported by current version {}"
                            .format(VERSION))
                else:
                    raise PRGAAPIError(
                            "The context is pickled by PRGA version {}, not supported by current version {}"
                            .format(version, VERSION))
            obj.summary.cwd = obj.cwd = os.path.dirname(os.path.abspath(name))
        _logger.info("Context {}unpickled from {}".format(
            "summary " if isinstance(obj, ContextSummary) else "", name))
        return obj
