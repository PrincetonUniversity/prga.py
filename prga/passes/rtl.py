# -*- encoding: ascii -*-

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
        incremental (:obj:`bool`): If set to ``True``, the RTL sources already listed in
            ``context.summary.rtl["sources"]`` will not be overwritten
    """

    __slots__ = ['renderer', 'src_output_dir', 'header_output_dir', 'view', 'visited', 'incremental']
    def __init__(self, src_output_dir = ".", header_output_dir = None, view = ModuleView.design,
            incremental = False):
        self.src_output_dir = src_output_dir
        self.header_output_dir = uno(header_output_dir, os.path.join(src_output_dir, "include"))
        self.view = view
        self.visited = {}
        self.incremental = incremental

    def _process_module(self, module):
        if module.key in self.visited:
            return
        f = os.path.join(self.src_output_dir, getattr(module, "verilog_src", module.name + ".v"))
        self.visited[module.key] = f

        if getattr(module, "do_generate_verilog", not os.path.isabs(f)):
            self.renderer.add_verilog(f, module, getattr(module, "verilog_template", "generic/module.tmpl.v"))
        for instance in module.instances.values():
            self._process_module(instance.model)

    def _collect_headers(self, context):
        for f, (template, parameters) in context._verilog_headers.items():
            self.renderer.add_generic(os.path.join(self.header_output_dir, f), template, context = context,
                    **parameters)

    @property
    def key(self):
        return "rtl.verilog"

    @property
    def dependences(self):
        if self.view.is_design:
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

        self._collect_headers(context)
        self._process_module(top)

        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        context.summary.rtl["includes"] = set([self.header_output_dir]) | context.summary.rtl.get("includes", set())

        for k, v in self.visited.items():
            if self.incremental:
                context.summary.rtl.setdefault("sources", {}).setdefault(k, v)
            else:
                context.summary.rtl.setdefault("sources", {})[k] = v
