# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import ModuleView
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
        for primitive_key in context.summary.active_primitives:
            primitive = context.database[ModuleView.user, primitive_key]
            self.renderer.add_yosys_library(
                    os.path.join(os.path.abspath(self.output_dir), "lib.v"),
                    primitive, template = getattr(primitive, "lib_template", None))
            techmap_template = getattr(primitive, "techmap_template", None)
            if techmap_template is not None:
                if primitive.primitive_class.is_custom:
                    premap_commands = getattr(primitive, "premap_commands", tuple())
                    self.renderer.add_yosys_techmap(
                        os.path.join(os.path.abspath(self.output_dir), primitive.name + ".techmap.v"),
                        techmap_template, premap_commands = premap_commands)
                elif primitive.primitive_class.is_memory:
                    try:
                        mem_infer_rule_template = primitive.mem_infer_rule_template
                        mem_infer_rule = os.path.join(os.path.abspath(self.output_dir), "bram.rule")
                        self.renderer.add_yosys_mem_infer_rule(mem_infer_rule, primitive, mem_infer_rule_template)
                    except AttributeError:
                        mem_infer_rule = None
                    premap_commands = getattr(primitive, "premap_commands", tuple())
                    self.renderer.add_yosys_memory_techmap(
                        os.path.join(os.path.abspath(self.output_dir), primitive.name + ".techmap.v"),
                        primitive, techmap_template,
                        premap_commands = premap_commands, rule_script = mem_infer_rule)
