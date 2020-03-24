# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import ModuleView
from ..util import Object

import os

__all__ = ['VerilogCollection']

# ----------------------------------------------------------------------------
# -- Verilog Collection ------------------------------------------------------
# ----------------------------------------------------------------------------
class VerilogCollection(Object, AbstractPass):
    """Collecting Verilog rendering tasks."""

    __slots__ = ['renderer', 'output_dir', 'view', 'visited']
    def __init__(self, renderer, output_dir = ".", view = ModuleView.logical):
        self.renderer = renderer
        self.output_dir = output_dir
        self.view = view

    def _process_module(self, module):
        if module.key in self.visited:
            return
        f = os.path.join(os.path.abspath(self.output_dir), module.name + ".v")
        self.visited[module.key] = f
        self.renderer.add_verilog(module, f, getattr(module, "verilog_template", "module.tmpl.v"))
        for instance in itervalues(module.instances):
            self._process_module(instance.model)

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
        top = context.database[self.view, context.top.key]
        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        self.visited = context.summary.rtl["sources"] = {}
        self._process_module(top)
