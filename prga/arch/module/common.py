# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Enum

__all__ = ['ModuleClass']

# ----------------------------------------------------------------------------
# -- Logical Module Class ----------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleClass(Enum):
    """Logical class for modules."""
    # primitives
    primitive = 0           #: primitive module
    mode = 1                #: one mode of a multi-mode primitive
    # switches
    switch = 2              #: configurable switches
    # config circuitry
    config = 3              #: configuration circuitry-related modules
    # sub-block hierarchy
    cluster = 4             #: user-defined intermediate modules inside logic/io blocks
    # logic blocks
    logic_block = 5         #: logic block
    io_block = 6            #: io block
    # routing boxes
    connection_box = 7      #: connection box
    switch_box = 8          #: switch box
    # array elements
    tile = 9                #: a single tile in an array
    array = 10              #: top-level or intermediate level of arrays
    # extensions
    extension = 11          #: reserved for extensions
