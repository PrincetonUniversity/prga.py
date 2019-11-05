# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.flow.context import ArchitectureContext

from prga_tools.util import find_verilog_top, parse_io_bindings, parse_parameters

import jinja2 as jj
import os
import sys

__all__ = ['generate_yosys_script']

def generate_yosys_script(ostream, sources, model, generic_script, template = None):
    """Generate ``model``-specific synthesis script.

    Args:
        ostream (file-like object): output stream
        sources (:obj:`Sequence` [:obj:`str` ]):
        model (`VerilogModule`): Top-level module of the target design
        generic_script (:obj:`str`): The generic script generated for the architecture
    """
    if template is None:
        env = jj.Environment(loader=jj.FileSystemLoader(
            os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates')))
        template = env.get_template('synth.tmpl.ys')
    template.stream({
        "model": model,
        "model_sources": sources,
        "yosys_script": generic_script,
        "iteritems": iteritems,
        "itervalues": itervalues,
        }).dump(ostream)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
            description="Design-specific synthesis script generator")
    
    parser.add_argument('context', type=argparse.FileType(OpenMode.rb),
            help="Pickled architecture context object")
    parser.add_argument('-o', '--output', type=argparse.FileType("w"), dest='output',
            help="Generated script")
    parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
            help="Source file(s) for behavioral model")
    parser.add_argument('--model_top', type=str,
            help="Top-level module name of the behavioral model. Required if the model comprises multiple files/modules")
    parser.add_argument('--model_parameters', type=str, nargs="+", default=[],
            help="Parameters for the behavioral model: PARAMETER0=VALUE0 PARAMETER1=VALUE1 ...")

    args = parser.parse_args()

    context = ArchitectureContext.unpickle(args.context)
    model_top = find_verilog_top(args.model, args.model_top)
    model_top.parameters = parse_parameters(args.model_parameters) 
    ostream = sys.stdout if args.output is None else args.output

    generate_yosys_script(ostream, args.model, model_top, context._yosys_script)
