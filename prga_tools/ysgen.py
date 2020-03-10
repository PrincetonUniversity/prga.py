# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.core.context import Context
from prga.renderer.renderer import FileRenderer

from .util import find_verilog_top, parse_io_bindings, parse_parameters

import jinja2 as jj
import os
import sys

__all__ = ['generate_yosys_script']

def generate_yosys_script(summary, renderer, ostream, model, model_sources, template = "synth.specific.tmpl.ys"):
    """Generate ``model``-specific synthesis script.

    Args:
        summary (`ContextSummary`):
        renderer (`FileRenderer`):
        ostream (file-like object): output stream
        model (`VerilogModule`): Top-level module of the target design
        model_sources (:obj:`Sequence` [:obj:`str` ]): Verilog sources for ``model``
        template (:obj:`str`): Custom template
    """
    renderer.add_generic( ostream, template, 
            model = model, model_sources = model_sources, yosys_script = summary.yosys_script,
            iteritems = iteritems, itervalues = itervalues )

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
            description="Design-specific synthesis script generator")
    
    parser.add_argument('summary', type=argparse.FileType(OpenMode.rb),
            help="Pickled architecture context summary object")
    parser.add_argument('-o', '--output', type=argparse.FileType("w"), dest='output',
            help="Generated script")
    parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
            help="Source file(s) for behavioral model")
    parser.add_argument('--model_top', type=str,
            help="Top-level module name of the behavioral model. Required if the model comprises multiple files/modules")
    parser.add_argument('--model_parameters', type=str, nargs="+", default=[],
            help="Parameters for the behavioral model: PARAMETER0=VALUE0 PARAMETER1=VALUE1 ...")

    args = parser.parse_args()

    summary = Context.unpickle(args.summary)
    model_top = find_verilog_top(args.model, args.model_top)
    model_top.parameters = parse_parameters(args.model_parameters) 
    ostream = sys.stdout if args.output is None else args.output

    # create renderer
    r = FileRenderer(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates'))

    generate_yosys_script(summary, r, ostream.model, model_top, args.model)
