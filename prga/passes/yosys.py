# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..util import Object

import os

__all__ = ['YosysScriptsCollection']

# ----------------------------------------------------------------------------
# -- Yosys Scripts Collection ------------------------------------------------
# ----------------------------------------------------------------------------
class YosysScriptsCollection(AbstractPass):
    """Collecting Yosys script rendering tasks."""

    __slots__ = ['renderer', 'output_dir']
    def __init__(self, renderer, output_dir = "."):
        self.renderer = renderer
        self.output_dir = output_dir

    @property
    def key(self):
        return "yosys"

    @property
    def dependences(self):
        return ("vpr", )

    @property
    def is_readonly_pass(self):
        return True

    def run(self, context):
        f = context.summary.yosys_script = os.path.join(os.path.abspath(self.output_dir), "synth.ys") 
        self.renderer.add_yosys_synth_script(f, context.summary.lut_sizes)
