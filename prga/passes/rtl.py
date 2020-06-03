# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import ModuleView
from ..util import Object, uno
from ..exception import PRGAInternalError

import os

__all__ = ['VerilogCollection']

# ----------------------------------------------------------------------------
# -- Verilog Collection ------------------------------------------------------
# ----------------------------------------------------------------------------
class VerilogCollection(Object, AbstractPass):
    """Collecting Verilog rendering tasks."""

    __slots__ = ['renderer', 'src_output_dir', 'header_output_dir', 'view', 'visited']
    def __init__(self, renderer, src_output_dir = ".", header_output_dir = None, view = ModuleView.logical):
        self.renderer = renderer
        self.src_output_dir = src_output_dir
        self.header_output_dir = os.path.abspath(uno(header_output_dir, os.path.join(src_output_dir, "include")))
        self.view = view
        self.visited = {}

    def _process_module(self, module):
        if module.key in self.visited:
            return
        f = os.path.join(os.path.abspath(self.src_output_dir), module.name + ".v")
        self.visited[module.key] = f
        self.renderer.add_verilog(module, f, getattr(module, "verilog_template", "module.tmpl.v"))
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

    def run(self, context):
        top = context.system_top
        if top is None:
            raise PRGAInternalError("System top module is not set")
        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        self.visited = context.summary.rtl["sources"] = {}
        context.summary.rtl["includes"] = [self.header_output_dir]
        self._collect_headers(context)
        self._process_module(top)
