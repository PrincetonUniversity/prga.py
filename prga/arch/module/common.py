# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Enum

__all__ = ['ModuleClass']

# ----------------------------------------------------------------------------
# -- Module Class ------------------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleClass(Enum):
    """Class for modules."""
    # logical (and maybe physical as well) w/o user ports
    array = 0               #: top-level or intermediate-level array above tiles
    tile = 1                #: a single tile in an array (wrapper for block + connection box)
    config = 2              #: configuration circuitry
    switch = 3              #: configurable switch
    # logical (and maybe physical as well) w/ user ports
    # logic blocks
    io_block = 4            #: IO block
    logic_block = 5         #: logic block
    # routing boxes
    connection_box = 6      #: connection box
    switch_box = 7          #: switch box
    # logical-only w/ user ports
    # a mode in multi-mode primitive
    mode = 8                #: one mode in a multi-mode primitive
    # logical & user (and maybe physical as well)
    cluster = 9             #: intermediate-level module inside blocks but above primitives
    primitive = 10          #: primitive cell
