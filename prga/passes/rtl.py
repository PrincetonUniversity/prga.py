# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import ModuleView
from ..util import uno
from ..exception import PRGAInternalError, PRGAAPIError

import os

__all__ = ['VerilogCollection']

# ----------------------------------------------------------------------------
# -- Verilog Collection ------------------------------------------------------
# ----------------------------------------------------------------------------
class VerilogCollection(AbstractPass):
    """Collecting Verilog rendering tasks.
    
    Args:
        src_output_dir (:obj:`str`): Verilog source files are generated in the specified directory. Default value is
            the current working directory.

    Keyword Args:
        header_output_dir (:obj:`str`): Verilog header files are generated in the specified directory. Default value
            is "{src_output_dir}/include"
        view (`ModuleView`): Generate Verilog source files with the specified view
    """

    __slots__ = ['renderer', 'src_output_dir', 'header_output_dir', 'view', 'visited']
    def __init__(self, src_output_dir = ".", header_output_dir = None, view = ModuleView.logical):
        self.src_output_dir = src_output_dir
        self.header_output_dir = uno(header_output_dir, os.path.join(src_output_dir, "include"))
        self.view = view
        self.visited = {}

    def _process_module(self, module):
        if module.key in self.visited:
            return
        f = os.path.join(self.src_output_dir, getattr(module, "verilog_src", module.name + ".v"))
        self.visited[module.key] = f
        if not getattr(module, "dont_generate_verilog", False):
            self.renderer.add_verilog(f, module, getattr(module, "verilog_template", "module.tmpl.v"))
        for instance in itervalues(module.instances):
            self._process_module(instance.model)

    def _collect_headers(self, context):
        for f, (template, parameters) in iteritems(context._verilog_headers):
            self.renderer.add_generic(os.path.join(self.header_output_dir, f), template, context = context,
                    **parameters)

    @property
    def key(self):
        return "rtl.verilog"

    @property
    def dependences(self):
        if self.view.is_logical:
            return ("translation", )
        else:
            return ("translation", "materialization")

    @property
    def is_readonly_pass(self):
        return True

    def run(self, context, renderer = None):
        if renderer is None:
            raise PRGAAPIError("File renderer is required for the Verilog Collection pass")
        self.renderer = renderer
        if (top := context.system_top) is None:
            raise PRGAAPIError("System top module is not set")
        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        self.visited = context.summary.rtl["sources"] = {}
        context.summary.rtl["includes"] = [self.header_output_dir]
        self._collect_headers(context)
        self._process_module(top)
