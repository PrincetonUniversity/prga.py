# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.array.array import Array
from prga.algorithm.design.switch import SwitchLibraryDelegate
from prga.algorithm.design.tile import ConnectionBoxLibraryDelegate
from prga.algorithm.design.array import SwitchBoxLibraryDelegate
from prga.flow.library import (PrimitiveLibraryDelegate,
        BuiltinPrimitiveLibrary, BuiltinSwitchLibrary, BuiltinConnectionBoxLibrary, BuiltinSwitchBoxLibrary)
from prga.rtlgen.rtlgen import VerilogGenerator
from prga.util import Object, uno, ReadonlyMappingProxy

from collections import OrderedDict

try:
    import cPickle as pickle
except ImportError:
    import pickle

__all__ = ['BaseArchitectureContext']

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
            '_vgen',                # verilog generator
            '_primitive_lib',       # primitive library
            '_switch_lib',          # switch library
            '_cbox_lib',            # connection box library
            '_sbox_lib',            # switch box library
            ]

    def __init__(self, name, width, height,
            additional_template_search_paths = tuple(),
            primitive_library = None,
            switch_library = None,
            connection_box_library = None,
            switch_box_library = None
            ):
        super(BaseArchitectureContext, self).__init__()
        self._top = Array(name, width, height)
        self._globals = OrderedDict()
        self._segments = OrderedDict()
        self._modules = OrderedDict()
        self._vgen = VerilogGenerator(additional_template_search_paths)
        self._primitive_lib = uno(primitive_library, BuiltinPrimitiveLibrary(self))
        self._switch_lib = uno(switch_library, BuiltinSwitchLibrary(self))
        self._cbox_lib = uno(connection_box_library, BuiltinConnectionBoxLibrary(self))
        self._sbox_lib = uno(switch_box_library, BuiltinSwitchBoxLibrary(self))

    # == low-level API =======================================================
    @property
    def top(self):
        """`Array`: Top-level array."""
        return self._top

    @property
    def globals(self):
        """:obj:`Mapping` [:obj:`str`, `Global` ]: A mapping from names to global wire prototypes."""
        return ReadonlyMappingProxy(self._globals)

    @property
    def segments(self):
        """:obj:`Mapping` [:obj:`str`, `SegmentPrototype` ]: A mapping from names to wire segment prototypes."""
        return ReadonlyMappingProxy(self._segments)

    @property
    def modules(self):
        """:obj:`Mapping` [:obj:`str`, `AbstractModule` ]: A mapping from names to modules."""
        return ReadonlyMappingProxy(self._modules)

    @property
    def verilog_generator(self):
        """`VerilogGenerator`: Verilog generator."""
        return self._vgen

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
