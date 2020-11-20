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
        renderer.add_yosys_synth_script(f, context.summary.lut_sizes)
        for primitive_key in context.summary.active_primitives:
            primitive = context.database[ModuleView.user, primitive_key]
            renderer.add_yosys_library(
                    os.path.join(self.output_dir, primitive.name + ".lib.v"),
                    primitive, template = getattr(primitive, "verilog_template", None))
            if (techmap_template := getattr(primitive, "techmap_template", None)) is not None:
                if primitive.primitive_class.is_custom:
                    premap_commands = getattr(primitive, "premap_commands", tuple())
                    renderer.add_yosys_techmap(
                        os.path.join(self.output_dir, primitive.name + ".techmap.v"),
                        techmap_template, premap_commands = premap_commands,
                        **getattr(primitive, "techmap_parameters", {}))
                elif primitive.primitive_class.is_memory:
                    try:
                        mem_infer_rule_template = primitive.mem_infer_rule_template
                        mem_infer_rule = os.path.join(self.output_dir, "bram.rule")
                        renderer.add_yosys_mem_infer_rule(mem_infer_rule, primitive, mem_infer_rule_template)
                    except AttributeError:
                        mem_infer_rule = None
                    premap_commands = getattr(primitive, "premap_commands", tuple())
                    renderer.add_yosys_memory_techmap(
                        os.path.join(self.output_dir, primitive.name + ".techmap.v"),
                        primitive, techmap_template,
                        premap_commands = premap_commands, rule_script = mem_infer_rule)
