# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..core.common import ModuleView, ModuleClass
from ..netlist.net.util import NetUtils
from ..netlist.module.module import Module
from ..netlist.module.util import ModuleUtils
from ..util import Object, uno
from ..exception import PRGAInternalError

import os
import jinja2 as jj

# In Python 3.7 and above, ``dict`` preserves insertion order and is more performant than ``OrderedDict``
OrderedDict = dict

__all__ = ['FileRenderer']

DEFAULT_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- File Renderer -----------------------------------------------------------
# ----------------------------------------------------------------------------
class FileRenderer(Object):
    """File renderer based on Jinja2."""

    __slots__ = ['template_search_paths', 'tasks', 'test_tasks','_yosys_synth_script_task']
    def __init__(self, *paths):
        self.template_search_paths = [DEFAULT_TEMPLATE_SEARCH_PATH]
        self.template_search_paths.extend(paths)
        self.tasks = OrderedDict()
        self.test_tasks = OrderedDict()
        self._yosys_synth_script_task = None

    @classmethod
    def _net2verilog(cls, net):
        """:obj:`str`: Render in verilog syntax a slice or a bus ``net``."""
        if net.net_type.is_const:
            if net.value is None:
                return "{}'bx".format(len(net))
            else:
                return "{}'h{:x}".format(len(net), net.value)
        else:
            bus, suffix = net, ""
            if net.bus_type.is_slice:
                bus = net.bus
                if len(net) == 1:
                    suffix = '[{}]'.format(net.index.start)
                else:
                    suffix = '[{}:{}]'.format(net.index.stop - 1, net.index.start)
            if bus.net_type.is_port:
                return bus.name + suffix
            else:
                return "_{}__{}".format(bus.instance.name, bus.model.name) + suffix

    @classmethod
    def _source2verilog(cls, net):
        """:obj:`str`: Render in verilog syntax the concatenation for the nets driving ``net``."""
        source = NetUtils.get_source(net)
        if source.bus_type.is_concat:
            return '{' + ', '.join(cls._net2verilog(i) for i in reversed(source.items)) + '}'
        else:
            return cls._net2verilog(source)

    def _get_yosys_script_task(self, script_file = None):
        """Get the specified or most recently added yosys script rending task."""
        script_task = uno(script_file, self._yosys_synth_script_task)
        if script_task is None:
            raise PRGAInternalError("Main synthesis script not specified")
        script_task = self.tasks[script_task]
        if len(script_task) > 1:
            raise PRGAInternalError("Main synthesis script is produced by multiple templates")
        return script_task

    @classmethod
    def _register_lib(cls, context):
        """Register designs shipped with PRGA into ``context`` database.

        Args:
            context (`Context`):
        """
        # register designs
        for d in ("prga_ram_1r1w", "prga_fifo", "prga_fifo_resizer", "prga_fifo_lookahead_buffer",
                "prga_fifo_adapter", "prga_byteaddressable_reg", "prga_tokenfifo"):
            context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "stdlib/{}.v".format(d))
        for d in ("prga_ram_1r1w_dc", "prga_async_fifo", "prga_async_tokenfifo", "prga_clkdiv"):
            context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "cdclib/{}.v".format(d))
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_fifo"],
                context._database[ModuleView.logical, "prga_ram_1r1w"], "ram")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_fifo"],
                context._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_fifo_resizer"],
                context._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_fifo_adapter"],
                context._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_async_fifo"],
                context._database[ModuleView.logical, "prga_ram_1r1w_dc"], "ram")
        ModuleUtils.instantiate(context._database[ModuleView.logical, "prga_async_fifo"],
                context._database[ModuleView.logical, "prga_fifo_lookahead_buffer"], "buffer")

        # add headers
        context._add_verilog_header("prga_utils.vh", "stdlib/include/prga_utils.tmpl.vh")

    def add_verilog(self, module, file_, template = 'module.tmpl.v', **kwargs):
        """Add a Verilog rendering task.

        Args:
            module (`Module`): The module to be rendered
            file_ (:obj:`str` of file-like object): The output file
            template (:obj:`str`): The template to be used
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                "module": module,
                "source2verilog": self._source2verilog,
                'itervalues': itervalues,
                'iteritems': iteritems,
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (template, parameters) )


    def add_makefile(self, instance, file_, template = 'test_base.tmpl', **kwargs):
        """Add a Verilog rendering task.

        Args:
            instance (`Abstractg`): The instance to be rendered
            file_ (:obj:`str` of file-like object): The output file
            template (:obj:`str`): The template to be used
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                "instance": instance,
                "source2verilog": self._source2verilog,
                'itervalues': itervalues,
                'iteritems': iteritems
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (template, parameters) )

    def add_python_test(self, instance, file_, template = 'test_base.tmpl.py', **kwargs):
        """Add a Verilog rendering task.

        Args:
            instance (`Abstractg`): The instance to be rendered
            file_ (:obj:`str` of file-like object): The output file
            template (:obj:`str`): The template to be used
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                "instance": instance,
                "source2verilog": self._source2verilog,
                'itervalues': itervalues,
                'iteritems': iteritems,
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (template, parameters) )

    def add_generic(self, file_, template, **kwargs):
        """Add a generic file rendering task.

        Args:
            file_ (:obj:`str` of file-like object): The output file
            template (:obj:`str`): The template to be used
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                'itervalues': itervalues,
                'iteritems': iteritems,
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (template, parameters) )

    def add_yosys_synth_script(self, file_, lut_sizes, template = 'synth.generic.tmpl.ys', **kwargs):
        """Add a yosys synthesis script rendering task.

        Args:
            file_ (:obj:`str` of file-like object): The output file
            lut_sizes (:obj:`Sequence` [:obj:`int` ]): LUT sizes active in the FPGA
            template (:obj:`str`): The template to be used
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                "libraries": [],
                "memory_techmaps": [],
                "techmaps": [],
                "lut_sizes": lut_sizes,
                "iteritems": iteritems,
                "itervalues": itervalues,
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (template, parameters) )
        self._yosys_synth_script_task = file_

    def add_yosys_library(self, file_, module, template = "blackbox.lib.tmpl.v", script_file = None, **kwargs):
        """Add a yosys library rendering task.

        Args:
            file_ (:obj:`str` of file-like object): The output file
            module (`Module`): The blackbox module

        Keyword Args:
            template (:obj:`str`): The template to be used
            script_file (:obj:`str` of file-like object): The main script file. If not specified, the most recently
                added yosys script file will be used
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                "iteritems": iteritems,
                "itervalues": itervalues,
                "module": module,
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (uno(template, "blackbox.lib.tmpl.v"), parameters) )
        script_task = self._get_yosys_script_task(script_file)
        if not isinstance(file_, basestring):
            file_ = os.path.abspath(file_.name)
        else:
            file_ = os.path.abspath(file_)
        if file_ not in script_task[0][1]["libraries"]:
            script_task[0][1]["libraries"].append( file_ )

    def add_yosys_techmap(self, file_, template, script_file = None, premap_commands = tuple(), **kwargs):
        """Add a yosys techmap rendering task.

        Args:
            file_ (:obj:`str` of file-like object): The output file
            template (:obj:`str`): The template to be used

        Keyword Args:
            script_file (:obj:`str` of file-like object): The main script file. If not specified, the most recently
                added yosys script file will be used
            premap_commands (:obj:`Sequence` [:obj:`str` ]): Commands to be run before running the techmap step
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                "iteritems": iteritems,
                "itervalues": itervalues,
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (template, parameters) )
        script_task = self._get_yosys_script_task(script_file)
        if len(script_task) > 1:
            raise PRGAInternalError("Main synthesis script is produced by multiple templates")
        if not isinstance(file_, basestring):
            file_ = os.path.abspath(file_.name)
        else:
            file_ = os.path.abspath(file_)
        script_task[0][1]["techmaps"].append( {
            "premap_commands": premap_commands,
            "techmap": file_,
            } )

    def add_yosys_mem_infer_rule(self, file_, module, template, **kwargs):
        """Add a yosys BRAM inferring rule rendering task.

        Args:
            file_ (:obj:`str` of file-like object): The output file
            module (`Module`): The memory module
            template (:obj:`str`): The template to be used

        Keyword Args:
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                "iteritems": iteritems,
                "itervalues": itervalues,
                "module": module,
                }
        parameters.update(kwargs)
        l = self.tasks.setdefault(file_, [])
        if l:
            l[-1][1].setdefault("not_last", True)
        l.append( (template, parameters) )

    def add_yosys_memory_techmap(self, file_, module, template = None, script_file = None,
            premap_commands = tuple(), rule_script = None, **kwargs):
        """Add a yosys memory techmap rendering task.

        Args:
            file_ (:obj:`str` or file-like object): The output file
            module (`Module`): The memory module

        Keyword Args:
            template (:obj:`str`): The template to be used
            script_file (:obj:`str` of file-like object): The main script file. If not specified, the most recently
                added yosys script file will be used
            premap_commands (:obj:`Sequence` [:obj:`str` ]): Commands to be run before running the techmap step
            rule_script (:obj:`str` or file-like object): The BRAM inferring rule
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
        parameters = {
                "iteritems": iteritems,
                "itervalues": itervalues,
                "module": module,
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (template, parameters) )
        script_task = self._get_yosys_script_task(script_file)
        if len(script_task) > 1:
            raise PRGAInternalError("Main synthesis script is produced by multiple templates")
        if not isinstance(file_, basestring):
            file_ = os.path.abspath(file_.name)
        else:
            file_ = os.path.abspath(file_)
        d = {
                "premap_commands": premap_commands,
                "techmap": file_,
                }
        if isinstance(rule_script, basestring):
            d["rule"] = os.path.abspath(rule_script)
        elif rule_script is not None:
            d["rule"] = os.path.abspath(rule_script.name)
        script_task[0][1]["memory_techmaps"].append( d )

    def render(self):
        """Render all added files and clear the task queue."""
        env = jj.Environment(loader = jj.FileSystemLoader(self.template_search_paths))
        env.globals.update(NetUtils=NetUtils)
        while self.tasks:
            file_, l = self.tasks.popitem()
            if isinstance(file_, basestring):
                d = os.path.dirname(file_)
                if d:
                    makedirs(d)
                file_ = open(file_, OpenMode.wb)
            for template, parameters in l:
                env.get_template(template).stream(parameters).dump(file_, encoding="ascii")
