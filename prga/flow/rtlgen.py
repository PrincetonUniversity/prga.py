# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.rtlgen.rtlgen import VerilogGenerator
from prga.flow.flow import AbstractPass
from prga.flow.util import analyze_hierarchy
from prga.util import Object

__all__ = ['VerilogGeneration']

# ----------------------------------------------------------------------------
# -- Generate Verilog --------------------------------------------------------
# ----------------------------------------------------------------------------
class GenerateVerilog(Object, AbstractPass):
    """Generate Verilog for all physical modules."""

    @property
    def key(self):
        """Key of this pass."""
        return "rtl.verilog"

    def run(self, context):
        vgen = VerilogGenerator(context._additional_template_search_paths)
        hierarchy = analyze_hierarchy(context)
        queue = [context.top]
        generated = set()
        while queue:
            module = queue.pop(0)
            for name, sub in iteritems(hierarchy[module.name]):
                if name in generated or not sub.is_physical:
                    continue
                queue.append(sub)
            vgen.generate_module(open(module.name + '.v', OpenMode.w), module)
            generated.add(module.name)
