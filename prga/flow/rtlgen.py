# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.rtlgen.rtlgen import VerilogGenerator
from prga.flow.flow import AbstractPass
from prga.flow.util import analyze_hierarchy
from prga.util import Object

import os
import logging
_logger = logging.getLogger(__name__)

__all__ = ['GenerateVerilog']

# ----------------------------------------------------------------------------
# -- Generate Verilog --------------------------------------------------------
# ----------------------------------------------------------------------------
class GenerateVerilog(Object, AbstractPass):
    """Generate Verilog for all physical modules.
    
    Args:
        prefix (:obj:`str`): Prefix to the verilog files
    """

    __slots__ = ['prefix']
    def __init__(self, prefix = ''):
        self.prefix = prefix

    @property
    def key(self):
        """Key of this pass."""
        return "rtl.verilog"

    def run(self, context):
        vgen = VerilogGenerator(context._additional_template_search_paths)
        hierarchy = analyze_hierarchy(context)
        visited = set()
        queue = {context.top.name: context.top}
        context._verilog_sources = []
        while queue:
            name, module = queue.popitem()
            visited.add(name)
            f = module.verilog_source
            if f is None:
                f = module.verilog_source = os.path.abspath(os.path.join(self.prefix, name + '.v'))
            else:
                f = module.verilog_source = os.path.abspath(os.path.join(self.prefix, module.verilog_source))
            _logger.info("[RTLGEN] Generating Verilog for module '{}': {}".format(name, f))
            makedirs(os.path.dirname(f))
            vgen.generate_module(open(f, OpenMode.wb), module)
            context._verilog_sources.append(f)
            for subname, sub in iteritems(hierarchy[name]):
                if subname in visited or subname in queue or not sub.in_physical_domain:
                    continue
                queue[subname] = sub
