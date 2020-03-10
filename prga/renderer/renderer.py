# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..netlist.net.util import NetUtils
from ..util import Object

import os
import jinja2 as jj

__all__ = ['FileRenderer']

DEFAULT_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

# ----------------------------------------------------------------------------
# -- File Renderer -----------------------------------------------------------
# ----------------------------------------------------------------------------
class FileRenderer(Object):
    """File renderer based on Jinja2."""

    __slots__ = ['template_search_paths', 'tasks', '_yosys_synth_script_task']
    def __init__(self, *paths):
        self.template_search_paths = [DEFAULT_TEMPLATE_SEARCH_PATH]
        self.template_search_paths.extend(paths)
        self.tasks = {}
        self._yosys_synth_script_task = None

    @classmethod
    def _net2verilog(cls, net):
        """:obj:`str`: Render in verilog syntax a slice or a bus ``net``."""
        if net.net_type.is_unconnected or net.net_type.is_const:
            return net.name
        elif net.net_type.is_port:
            if net.bus_type.is_nonref:
                return net.name
            elif isinstance(net.index, int):
                return '{}[{}]'.format(net.bus.name, net.index)
            else:
                return '{}[{}:{}]'.format(net.bus.name, net.index.stop - 1, net.index.start)
        elif net.bus_type.is_nonref:
            return '_{}__{}'.format(net.hierarchy[-1].name, net.model.name)
        elif isinstance(net.index, int):
            return '_{}__{}[{}]'.format(net.bus.hierarchy[-1].name, net.bus.model.name, net.index)
        else:
            return '_{}__{}[{}:{}]'.format(net.bus.hierarchy[-1].name, net.bus.model.name, net.index.stop - 1, net.index.start)

    @classmethod
    def _source2verilog(cls, net):
        """:obj:`str`: Render in verilog syntax the concatenation for the nets driving ``net``."""
        source = NetUtils.get_source(net)
        if source.bus_type.is_concat:
            return '{' + ', '.join(cls._net2verilog(i) for i in reversed(source.items)) + '}'
        else:
            return cls._net2verilog(source)

    def add_verilog(self, module, file_, template = 'module.tmpl.v', **kwargs):
        """Add a Verilog rendering task.

        Args:
            module (`AbstractModule`): The module to be rendered
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

    def add_generic(self, file_, template, **parameters):
        """Add a generic file rendering task.

        Args:
            file_ (:obj:`str` of file-like object): The output file
            template (:obj:`str`): The template to be used
            **kwargs: Additional key-value parameters to be passed into the template when rendering
        """
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
                }
        parameters.update(kwargs)
        self.tasks.setdefault(file_, []).append( (template, parameters) )
        self._yosys_synth_script_task = file_

    def render(self):
        """Render all added files and clear the task queue."""
        env = jj.Environment(loader = jj.FileSystemLoader(self.template_search_paths))
        while self.tasks:
            file_, l = self.tasks.popitem()
            if isinstance(file_, basestring):
                d = os.path.dirname(file_)
                if d:
                    makedirs(d)
                file_ = open(file_, OpenMode.wb)
            for template, parameters in l:
                env.get_template(template).stream(parameters).dump(file_, encoding="ascii")
