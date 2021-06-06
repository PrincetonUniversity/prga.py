# -*- encoding: ascii -*-

from ..util import uno
from ..exception import PRGAInternalError

import os

__all__ = []

# ----------------------------------------------------------------------------
# -- Verilog Generation Mixins -----------------------------------------------
# ----------------------------------------------------------------------------
class AppRTLMixin(object):
    """Mixin class for RTL generation for app wrapping logic."""

    def __process_header(self, include_dir, h, requirer, _added_headers):
        if h not in _added_headers:
            try:
                f, template, deps, parameters = self._verilog_headers[h]
            except KeyError:
                raise PRGAInternalError("Verilog header '{}' required by '{}' not found"
                        .format(h, requirer))
            for hh in deps:
                self.__process_header(h, requirer, _added_headers)
            self.renderer.add_generic( os.path.join(include_dir, f), template, **parameters )
            _added_headers.add(h)

    def __process_module(self, rtl_dir, include_dir,
            module = None, _added_modules = None, _added_headers = None):
        module = uno(module, self.top)
        _added_modules = uno(_added_modules, {})
        _added_headers = uno(_added_headers, set())

        if module.key in _added_modules:
            return

        f = os.path.join(rtl_dir, getattr(module, "verilog_src", module.name + ".v"))
        _added_modules[module.key] = f

        if getattr(module, "do_generate_verilog", not os.path.isabs(f)):
            self.renderer.add_verilog(f, module, getattr(module, "verilog_template", "generic/module.tmpl.v"))

        for instance in module.instances.values():
            self.__process_module(rtl_dir, include_dir,
                    instance.model, _added_modules, _added_headers)

        for h in getattr(module, "verilog_dep_headers", tuple()):
            self.__process_header(include_dir, h, module, _added_headers)

    def generate_verilog(self, rtl_dir, include_dir):
        self.renderer = None
        self.__process_module(rtl_dir, include_dir)
        self.renderer.render()
