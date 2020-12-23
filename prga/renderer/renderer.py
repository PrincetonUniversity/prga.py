# -*- encoding: ascii -*-

from ..netlist import NetUtils
from ..util import uno
from ..exception import PRGAInternalError

import os
import jinja2 as jj

__all__ = ['FileRenderer']

# ----------------------------------------------------------------------------
# -- File Renderer -----------------------------------------------------------
# ----------------------------------------------------------------------------
class FileRenderer(object):
    """File renderer based on Jinja2."""

    __slots__ = ['template_search_paths', 'tasks', '_yosys_synth_script_task']
    def __init__(self, *paths):
        self.template_search_paths = [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates'),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "integration", "templates")]
        self.template_search_paths = list(iter(paths)) + self.template_search_paths
        self.tasks = {}
        self._yosys_synth_script_task = None

    @classmethod
    def _net2verilog(cls, net):
        """:obj:`str`: Render ``net`` in verilog syntax."""
        if net.net_type.is_const:
            if net.value is None:
                return "{}'bx".format(len(net))
            else:
                return "{}'h{:x}".format(len(net), net.value)
        elif net.net_type.is_concat:
            return '{' + ',\n'.join(cls._net2verilog(i) for i in reversed(net.items)) + '}'
        elif net.net_type.is_slice:
            return '{}[{}:{}]'.format(cls._net2verilog(net.bus), net.index.stop - 1, net.index.start)
        elif net.net_type.is_bit:
            return '{}[{}]'.format(cls._net2verilog(net.bus), net.index)
        elif net.net_type.is_port:
            return net.name
        elif net.net_type.is_pin:
            return "_{}__{}".format(net.instance.name, net.model.name)
        else:
            raise PRGAInternalError("Unsupported net: {}".format(net))

    @classmethod
    def _source2verilog(cls, net):
        """:obj:`str`: Render in verilog syntax the concatenation for the nets driving ``net``."""
        return cls._net2verilog(NetUtils.get_source(net, return_const_if_unconnected = True))

    def _get_yosys_script_task(self, script_file = None):
        """Get the specified or most recently added yosys script rending task."""
        if (script_file := uno(script_file, self._yosys_synth_script_task)) is None:
            raise PRGAInternalError("Main synthesis script not specified")
        script_task = self.tasks[script_file]
        if len(script_task) > 1:
            raise PRGAInternalError("Main synthesis script is produced by multiple templates")
        return script_file, script_task

    def add_verilog(self, file_, module, template = None, order = 1., **kwargs):
        """Add a Verilog rendering task.

        Args:
            file_ (:obj:`str`): The output file
            module (`Module`): The module to be rendered
            template (:obj:`str`): The template to be used
            order (:obj:`float`): Rendering ordering when multiple ``template`` s are used to render ``file_``. The
                higher this value is, the earlier it is rendered.
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        self.tasks.setdefault(file_, []).append( (order, uno(template, "generic/module.tmpl.v"),
            dict(module = module,
                source2verilog = self._source2verilog,
                **kwargs)) )

    def add_generic(self, file_, template, order = 1., **kwargs):
        """Add a generic file rendering task.

        Args:
            file_ (:obj:`str`): The output file
            template (:obj:`str`): The template to be used
            order (:obj:`float`): Rendering ordering when multiple ``template`` s are used to render ``file_``. The
                higher this value is, the earlier it is rendered.
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        self.tasks.setdefault(file_, []).append( (order, template, kwargs) )

    def add_yosys_synth_script(self, file_, lut_sizes, template = None, **kwargs):
        """Add a yosys synthesis script rendering task.

        Args:
            file_ (:obj:`str`): The output file
            lut_sizes (:obj:`Sequence` [:obj:`int` ]): LUT sizes active in the FPGA
            template (:obj:`str`): The template to be used
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        self.tasks.setdefault(file_, []).append( (1., uno(template, "generic/synth.tmpl.tcl"),
            dict(libraries = [],
                memory_techmap = {},    # {"premap_commands": list[{"order": float, "commands": str}],
                                        #  "techmap": str,
                                        #  "techmap_task": str,
                                        #  "rule": str,
                                        #  "rule_task": str,}
                techmaps = [],          # {"premap_commands": str, "techmap": str, "order": float}
                lut_sizes = lut_sizes,
                **kwargs)) )
        self._yosys_synth_script_task = file_

    def add_yosys_library(self, file_, module, template = None, order = 1., **kwargs):
        """Add a yosys library rendering task and link it in the currently active synthesis script.

        Args:
            file_ (:obj:`str`): The output file
            module (`Module`): The blackbox module

        Keyword Args:
            template (:obj:`str`): The template to be used
            order (:obj:`float`): Rendering ordering when multiple ``template`` s are used to render ``file_``. The
                higher this value is, the earlier it is rendered.
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        self.tasks.setdefault(file_, []).append( (order, uno(template, "generic/blackbox.lib.tmpl.v"),
            dict(module = module,
                **kwargs)) )

        script_file, script_task = self._get_yosys_script_task()
        if not os.path.isabs(file_) and not os.path.isabs(script_file):
            file_ = os.path.relpath(file_, os.path.dirname(script_file))
        if file_ not in script_task[0][2]["libraries"]:
            script_task[0][2]["libraries"].append( file_ )

    def add_yosys_techmap(self, file_, template, premap_commands = None, order = 1., **kwargs):
        """Add a yosys techmap rendering task to the currently active synthesis script.

        Args:
            file_ (:obj:`str`): The output file
            template (:obj:`str`): The template to be used

        Keyword Args:
            premap_commands (:obj:`str`): Commands to be run before running the techmap step
            order (:obj:`float`): Rendering ordering when multiple ``template`` s are used to render ``file_``. The
                higher this value is, the earlier it is rendered. In addition, ``order`` is used to sort techmap
                commands in the synthesis script. Techmaps are executed before lutmap if ``order`` is non-negative,
                and after lutmap if ``order`` is negative.
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        self.tasks.setdefault(file_, []).append( (order, template, dict(**kwargs)) )

        script_file, script_task = self._get_yosys_script_task()
        if not os.path.isabs(file_) and not os.path.isabs(script_file):
            file_ = os.path.relpath(file_, os.path.dirname(script_file))
        script_task[0][2]["techmaps"].append( {
            "premap_commands": premap_commands,
            "techmap": file_,
            "order": order,
            } )

    def add_yosys_bram_rule(self, module, template, file_ = None, order = 1., **kwargs):
        """Add a yosys BRAM inferring rule rendering task to the currently active synthesis script.

        Args:
            module (`Module`): The memory module
            template (:obj:`str`): The template to be used

        Keyword Args:
            file_ (:obj:`str`): The output file. If ``add_yosys_bram_rule`` is called the first
                time after a new synthesis script is activated, this argument is required. Otherwise, this argument
                must either match the previously set value, or remain ``None``.
            order (:obj:`float`): Rendering ordering when multiple ``template`` s are used to render ``file_``. The
                higher this value is, the earlier it is rendered.
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        script_file, script_task = self._get_yosys_script_task()
        if (rule := script_task[0][2].setdefault("memory_techmap", {}).setdefault("rule_task", file_)) is None:
            raise PRGAInternalError("`file_` is required because `add_yosys_bram_rule` is called the first time")
        elif file_ is not None and rule != file_:
            raise PRGAInternalError("Active synthesis script uses '{}' for BRAM inferrence, but got '{}' this time"
                    .format(rule, file_))

        self.tasks.setdefault(rule, []).append( (order, template, dict(module = module, **kwargs)) )

        if not os.path.isabs(rule) and not os.path.isabs(script_file):
            rule = os.path.relpath(rule, os.path.dirname(script_file))
        script_task[0][2]["memory_techmap"]["rule"] = rule

    def add_yosys_memory_techmap(self, module, template,
            file_ = None, premap_commands = None, order = 1., **kwargs):
        """Add a yosys memory techmap rendering task to the currently active synthesis script.

        Args:
            file_ (:obj:`str`): The output file
            module (`Module`): The memory module
            template (:obj:`str`): The template to be used

        Keyword Args:
            file_ (:obj:`str`): The output file. If ``add_yosys_memory_techmap`` is called the
                first time after a new synthesis script is activated, this argument is required. Otherwise, this
                argument must either match the previously set value, or remain ``None``.
            premap_commands (:obj:`str`): Commands to be run before running the techmap step
            order (:obj:`float`): Rendering ordering when multiple ``template`` s are used to render ``file_``. The
                higher this value is, the earlier it is rendered.
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        script_file, script_task = self._get_yosys_script_task()
        if (techmap := script_task[0][2].setdefault("memory_techmap", {}).setdefault("techmap_task", file_)) is None:
            raise PRGAInternalError("`file_` is required because `add_yosys_memory_techmap` is called the first time")
        elif file_ is not None and techmap != file_:
            raise PRGAInternalError("Active synthesis script uses '{}' for memory map, but got '{}' this time"
                    .format(techmap, file_))

        self.tasks.setdefault(techmap, []).append( (order, template, dict(module = module, **kwargs)) )

        if not os.path.isabs(techmap) and not os.path.isabs(script_file):
            techmap = os.path.relpath(techmap, os.path.dirname(script_file))
        script_task[0][2]["memory_techmap"]["techmap"] = techmap

        if premap_commands:
            script_task[0][2]["memory_techmap"].setdefault("premap_commands", []).append( (order, premap_commands) )

    def render(self):
        """Render all added files and clear the task queue."""
        env = jj.Environment(loader = jj.FileSystemLoader(self.template_search_paths))
        while self.tasks:
            file_, l = self.tasks.popitem()
            if isinstance(file_, str):
                d = os.path.dirname(file_)
                if d:
                    os.makedirs(d, exist_ok = True)
                file_ = open(file_, "wb")
            for i, (_, template, parameters) in enumerate(sorted(l, key=lambda i: i[0], reverse=True)):
                env.get_template(template
                        ).stream(dict(_task_id = i, _num_tasks = len(l), **parameters)
                        ).dump(file_, encoding="ascii")
