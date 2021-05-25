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
        view (`ModuleView` or :obj:`str`): Generate Verilog source files with the specified view
        incremental (:obj:`bool`): If set to ``True``, the RTL sources already listed in
            ``context.summary.rtl["sources"]`` will not be overwritten
    """

    __slots__ = ['src_output_dir', 'header_output_dir', 'view',
            'visited_modules', 'added_headers', 'incremental']
    def __init__(self, src_output_dir = ".", header_output_dir = None, view = ModuleView.design,
            incremental = False):
        self.src_output_dir = src_output_dir
        self.header_output_dir = uno(header_output_dir, os.path.join(src_output_dir, "include"))
        self.view = ModuleView.construct(view)
        self.visited_modules = {}
        self.added_headers = set()
        self.incremental = incremental

    def _process_header(self, context, h, requirer):
        if h not in self.added_headers:
            try:
                f, template, deps, parameters = context._verilog_headers[h]
            except KeyError:
                raise PRGAInternalError("Verilog header '{}' required by '{}' not found"
                        .format(h, requirer))
            for hh in deps:
                self._process_header(context, hh, h)
            context.renderer.add_generic(os.path.join(self.header_output_dir, f), template,
                    context = context, **parameters)
            self.added_headers.add(h)

    def _process_module(self, context, module):
        if module.key in self.visited_modules:
            return
        f = os.path.join(self.src_output_dir, getattr(module, "verilog_src", module.name + ".v"))
        self.visited_modules[module.key] = f

        if getattr(module, "do_generate_verilog", not os.path.isabs(f)):
            context.renderer.add_verilog(f, module, getattr(module, "verilog_template", "generic/module.tmpl.v"))
        for instance in module.instances.values():
            self._process_module(context, instance.model)

        for h in getattr(module, "verilog_dep_headers", tuple()):
            self._process_header(context, h, module)

    @property
    def key(self):
        return "rtl.verilog"

    @property
    def dependences(self):
        return ("translation", )

    @property
    def is_readonly_pass(self):
        return True

    def run(self, context):
        if (top := context.system_top) is None:
            raise PRGAAPIError("System top module is not set")

        self._process_module(context, top)

        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        context.summary.rtl["includes"] = set([self.header_output_dir]) | context.summary.rtl.get("includes", set())

        for k, v in self.visited_modules.items():
            if self.incremental:
                context.summary.rtl.setdefault("sources", {}).setdefault(k, v)
            else:
                context.summary.rtl.setdefault("sources", {})[k] = v
