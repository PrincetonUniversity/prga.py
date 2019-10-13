# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Global, Orientation
from prga.arch.block.cluster import Cluster
from prga.arch.block.block import IOBlock, LogicBlock
from prga.arch.routing.common import Segment
from prga.arch.array.common import ChannelCoverage
from prga.arch.array.tile import Tile, IOTile
from prga.arch.array.array import Array
from prga.util import Object, uno, ReadonlyMappingProxy
from prga.exception import PRGAAPIError, PRGAInternalError

from collections import OrderedDict

try:
    import cPickle as pickle
except ImportError:
    import pickle

__all__ = ['BaseArchitectureContext']

# ----------------------------------------------------------------------------
# -- Primitives Proxy --------------------------------------------------------
# ----------------------------------------------------------------------------
class _PrimitivesProxy(Object, Mapping):
    """Helper class for `BaseArchitectureContext.primitives` property."""

    __slots__ = ['context']
    def __init__(self, context):
        self.context = context

    def __getitem__(self, key):
        module = self.context._modules.get(key, None)
        if module is None:
            try:
                return self.context.primitive_library.get_or_create_primitive(key)
            except PRGAInternalError as e:
                raise KeyError(key)
        elif not module.module_class.is_primitive:
            raise KeyError(key)
        else:
            return module

    def __iter__(self):
        return iter(key for key, module in iteritems(self.context._modules)
                if module.module_class.is_primitive)

    def __len__(self):
        return sum(1 for _ in self.__iter__())

# ----------------------------------------------------------------------------
# -- Base Architecture Context -----------------------------------------------
# ----------------------------------------------------------------------------
class BaseArchitectureContext(Object):
    """Base class for main interface to PRGA architecture description.

    Architecture context manages all resources created/added to the FPGA, including all modules, the
    routing graph, configration circuitry and more. Each configuration circuitry type should inherit this class to
    create its own type of architecture context.
    """

    __slots__ = [
            '_top',                 # top-level array
            '_globals',             # global wire prototypes
            '_segments',            # wire segment prototypes
            '_modules',             # all created modules
            '_config_lib',          # configuration circuitry library
            '_primitive_lib',       # primitive library
            '_switch_lib',          # switch library
            '_cbox_lib',            # connection box library
            '_sbox_lib',            # switch box library
            '_cache',               # non-pickled stuff
            '_additional_template_search_paths',
            ]

    def __init__(self, name, width, height, config_circuitry_delegate_class,
            additional_template_search_paths = tuple()):
        super(BaseArchitectureContext, self).__init__()
        self._top = Array(name, width, height, True)
        self._globals = OrderedDict()
        self._segments = OrderedDict()
        self._modules = OrderedDict()
        cfg = self._config_lib = config_circuitry_delegate_class(self)
        self._primitive_lib = cfg.get_primitive_library(self)
        self._switch_lib = cfg.get_switch_library(self)
        self._cbox_lib = cfg.get_connection_box_library(self)
        self._sbox_lib = cfg.get_switch_box_library(self)
        self._additional_template_search_paths = additional_template_search_paths
        self._cache = {}

    # == low-level API =======================================================
    @property
    def modules(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractModule` ]: A mapping from names to modules."""
        return ReadonlyMappingProxy(self._modules)

    @property
    def config_circuitry_delegate(self):
        """`ConfigCircuitryDelegate`: Configuration circuitry delegate."""
        return self._config_lib

    @property
    def primitive_library(self):
        """`PrimitiveLibraryDelegate`: Primitive library."""
        return self._primitive_lib

    @property
    def switch_library(self):
        """`SwitchLibraryDelegate`: Switch library."""
        return self._switch_lib

    @property
    def connection_box_library(self):
        """`ConnectionBoxLibraryDelegate`: Connection box library."""
        return self._cbox_lib

    @property
    def switch_box_library(self):
        """`SwitchBoxLibraryDelegate`: Switch box library."""
        return self._sbox_lib

    # == high-level API ======================================================
    # -- Global Wires --------------------------------------------------------
    @property
    def globals_(self):
        """:obj:`Mapping` [:obj:`str`, `Global` ]: A mapping from names to global wire prototypes."""
        return ReadonlyMappingProxy(self._globals)

    def create_global(self, name, width = 1, is_clock = False,
            bind_to_position = None, bind_to_subblock = None):
        """Create a global wire.

        Args:
            name (:obj:`str`): Name of the global wire
            width (:obj:`int`): Number of bits in the global wire
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

    # -- Wire Segments -------------------------------------------------------
    @property
    def segments(self):
        """:obj:`Mapping` [:obj:`str`, `Segment` ]: A mapping from names to wire segment prototypes."""
        return ReadonlyMappingProxy(self._segments)

    def create_segment(self, name, width, length):
        """Create a wire segment prototype.

        Args:
            name (:obj:`str`): Name of the segment
            width (:obj:`int`): Number of wire segments per routing channel, per direction. If the wire segments are
                longer than 1 tile, this is the number of wire segments originated from the channel
            length (:obj:`int`): Length of the wire segments, in terms of tiles

        Returns:
            `Segment`: The created segment prototype
        """
        if name in self._segments:
            raise PRGAAPIError("Wire segment named '{}' is already created".format(name))
        return self._segments.setdefault(name, Segment(name, width, length))

    # -- Primitives ----------------------------------------------------------
    @property
    def primitives(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractPrimitive` ]: A mapping from names to primitives."""
        return _PrimitivesProxy(self)

    # -- Clusters ------------------------------------------------------------
    @property
    def clusters(self):
        """:obj:`Mapping` [:obj:`str`, `Cluster` ]: A mapping from names to clusters."""
        return ReadonlyMappingProxy(self._modules, lambda kv: kv[1].module_class.is_cluster)

    def create_cluster(self, name):
        """Create a cluster.

        Args:
            name (:obj:`str`): Name of the cluster

        Returns:
            `Cluster`: The created cluster
        """
        if name in self._modules:
            raise PRGAAPIError("Module '{}' is already created".format(name))
        return self._modules.setdefault(name, Cluster(name))

    # -- IO Blocks -----------------------------------------------------------
    @property
    def io_blocks(self):
        """:obj:`Mapping` [:obj:`str`, `IOBlock` ]: A mapping from names to IOBs."""
        return ReadonlyMappingProxy(self._modules, lambda kv: kv[1].module_class.is_io_block)

    def create_io_block(self, name, input_ = True, output = True):
        """Create an IO block.

        Args:
            name (:obj:`str`): Name of the IO block
            input_ (:obj:`bool`): If set, the IOB can be used as an external input
            output (:obj:`bool`): If set, the IOB can be used as an external output

        Returns:
            `IOBlock`: The created IO block
        """
        if name in self._modules:
            raise PRGAAPIError("Module '{}' is already created".format(name))
        io_primitive = ((self.primitives['iopad'] if output else self.primitives['inpad'])
                if input_ else (self.primitives['outpad'] if output else None))
        if io_primitive is None:
            raise PRGAAPIError("At least one of 'input' and 'output' must be True")
        return self._modules.setdefault(name, IOBlock(name, io_primitive))

    # -- Logic Blocks --------------------------------------------------------
    @property
    def logic_blocks(self):
        """:obj:`Mapping` [:obj:`str`, `LogicBlock` ]: A mapping from names to CLBs."""
        return ReadonlyMappingProxy(self._modules, lambda kv: kv[1].module_class.is_logic_block)

    def create_logic_block(self, name, width = 1, height = 1):
        """Create a logic block.

        Args:
            name (:obj:`str`): Name of the logic block
            width (:obj:`int`): Width of the logic block in terms of tiles
            height (:obj:`int`): Height of the logic block in terms of tiles

        Returns:
            `LogicBlock`: The created logic block
        """
        if name in self._modules:
            raise PRGAAPIError("Module '{}' is already created".format(name))
        return self._modules.setdefault(name, LogicBlock(name, width, height))

    # -- Connection Boxes ----------------------------------------------------
    @property
    def connection_boxes(self):
        """:obj:`Mapping` [:obj:`str`, `ConnectionBox` ]: A mapping from names to connection boxes."""
        return ReadonlyMappingProxy(self._modules, lambda kv: kv[1].module_class.is_connection_box)

    # -- Switch Boxes --------------------------------------------------------
    @property
    def switch_boxes(self):
        """:obj:`Mapping` [:obj:`str`, `SwitchBox` ]: A mapping from names to switch boxes."""
        return ReadonlyMappingProxy(self._modules, lambda kv: kv[1].module_class.is_switch_box)

    # -- Tiles ---------------------------------------------------------------
    @property
    def tiles(self):
        """:obj:`Mapping` [:obj:`str`, `Tile` ]: A mapping from names to tiles."""
        return ReadonlyMappingProxy(self._modules, lambda kv: kv[1].module_class.is_tile)

    def create_tile(self, name, block, capacity = None, orientation = None):
        """Create a tile.

        Args:
            name (:obj:`str`): Name of the tile
            block (`IOBlock` or `LogicBlock`): Block in this tile
            capacity (:obj:`int`): Number of block instances in this tile. Required and only used if ``block`` is
                an `IOBlock`
            orientation (`Orientation`): On which side of the top-level array should the tile be placed on. Required
                and only used if ``block`` is an `IOBlock`

        Returns:
            `Tile`: The created tile

        Note:
            Sadly, unlike VPR, each tile must have a unique name DIFFERENT from the name of the block
        """
        if name in self._modules:
            raise PRGAAPIError("Module '{}' is already created".format(name))
        if block.module_class.is_io_block:
            if capacity is None or orientation in (None, Orientation.auto):
                raise PRGAAPIError("'capacity' and 'orientation' are required since '{}' is an IO block"
                        .format(block))
            return self._modules.setdefault(name, IOTile(name, block, capacity, orientation))
        else:
            return self._modules.setdefault(name, Tile(name, block))

    # -- Arrays --------------------------------------------------------------
    @property
    def top(self):
        """`Array`: Top-level array."""
        return self._top

    @property
    def arrays(self):
        """:obj:`Mapping` [:obj:`str`, `Array` ]: A mapping from names to arrays."""
        return ReadonlyMappingProxy(self._modules, lambda kv: kv[1].module_class.is_array)

    def create_array(self, name, width, height, coverage = ChannelCoverage()):
        """Create a (sub-)array.

        Args:
            name (:obj:`str): Name of the array
            width (:obj:`int`): Number of tiles in the X axis
            height (:obj:`int`): Number of tiles in the Y axis
            coverage (`ChannelCoverage`): Coverage of routing channels surrounding the array. No routing channels are
                covered by default

        Returns:
            `Array`: The created array
        """
        if name in self._modules:
            raise PRGAAPIError("Module '{}' is already created".format(name))
        return self._modules.setdefault(name, Array(name, width, height, False, coverage))

    # -- Serialization -------------------------------------------------------
    def pickle(self, file_):
        """Pickle the architecture context into a file.

        Args:
            file_ (file-like object): output file
        """
        # drop cache before pickling
        cache = self._cache
        self._cache = {}
        pickle.dump(self, file_, 2)
        # put cache back
        self._cache = cache

    @staticmethod
    def unpickle(file_):
        """Unpickle a pickled architecture context.

        Args:
            file_ (file-like object): the pickled file
        """
        return pickle.load(file_)
