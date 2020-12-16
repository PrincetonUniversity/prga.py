# -*- encoding: ascii -*-

from .base import AbstractPass
from ..core.common import ModuleView
from ..util import Object
from ..exception import PRGAAPIError

import os

__all__ = ['YosysScriptsCollection']

# ----------------------------------------------------------------------------
# -- Yosys Scripts Collection ------------------------------------------------
# ----------------------------------------------------------------------------
class YosysScriptsCollection(AbstractPass):
    """Collecting Yosys script rendering tasks.

    Args:
        output_dir (:obj:`str`): Directory for all output files. Current working directory is used by default
    """

    __slots__ = ['output_dir']
    def __init__(self, output_dir = "."):
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

    def run(self, context, renderer = None):
        if renderer is None:
            raise PRGAAPIError("File renderer is required for the Yosys Script Collection pass")
        if not hasattr(context.summary, "yosys"):
            context.summary.yosys = {}
        f = context.summary.yosys["script"] = os.path.join(self.output_dir, "synth.tcl") 
        libs = context.summary.yosys["libs"] = {}
        renderer.add_yosys_synth_script(f, context.summary.lut_sizes)
        for primitive_key in context.summary.active_primitives:
            primitive = context.database[ModuleView.user, primitive_key]
            if primitive.primitive_class.is_memory:
                rule = os.path.join(self.output_dir, "bram.rule")
                renderer.add_yosys_bram_rule(rule, primitive,
                        getattr(primitive, "bram_rule_template", None))
                mmap = os.path.join(self.output_dir, "memory.techmap.v")
                renderer.add_yosys_memory_techmap(mmap, primitive,
                        getattr(primitive, "techmap_template", None),
                        premap_commands = getattr(primitive, "premap_commands", tuple()),
                        rule_script = rule,
                        **getattr(primitive, "techmap_parameters", {}) )
            if primitive.vpr_model in libs:
                continue
            lib = libs[primitive.vpr_model] = os.path.join(self.output_dir, primitive.vpr_model + ".lib.v")
            renderer.add_yosys_library(lib, primitive,
                    template = getattr(primitive, "verilog_template", None))
            if primitive.primitive_class.is_custom:
                if (techmap_template := getattr(primitive, "techmap_template", None)) is not None:
                    renderer.add_yosys_techmap(
                            os.path.join(self.output_dir, primitive.vpr_model + ".techmap.v"),
                            techmap_template,
                            premap_commands = getattr(primitive, "premap_commands", tuple()),
                            model = primitive.vpr_model,
                            **getattr(primitive, "techmap_parameters", {}) )
                if (techmap_template := getattr(primitive, "postlutmap_template", None)) is not None:
                    renderer.add_yosys_postlutmap(
                            os.path.join(self.output_dir, primitive.vpr_model + ".postlutmap.v"),
                            techmap_template,
                            premap_commands = getattr(primitive, "postlut_commands", tuple()),
                            model = primitive.vpr_model,
                            **getattr(primitive, "postlutmap_parameters", {}) )
