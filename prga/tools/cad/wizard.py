# -*- encoding: ascii -*-

from ..util import create_argparser, docstring_from_argparser
from ...core.context import Context
from ...renderer.renderer import FileRenderer
from ...util import enable_stdout_logging, uno
from ...exception import PRGAAPIError

import os, sys, logging

__all__ = ['generate_cad_project']

import argparse
parser = create_argparser(__name__,
        description="CAD project generator for PRGA")

parser.add_argument("context", type=str,
        help="Pickled architecture context")
parser.add_argument("top", type=str,
        help="Name of the top-level module of the target design")

parser.add_argument("-v",
        type=str, action='append', dest="sources", default=[],
        help="Verilog source files of the target design")
parser.add_argument("-I", "--include",
        type=str, action='append', dest="includes", default=[],
        help="Verilog include directories of the target design")
parser.add_argument("-D", "--define", metavar="VAR[=VALUE]",
        type=str, action='append', dest="defines", default=[],
        help="Verilog defines")
parser.add_argument("-p", "--parameter", metavar="PARAMETER=VALUE",
        type=str, action='append', dest="parameters", default=[],
        help="Parameterization of the top-level module of the target design")

parser.add_argument("-f", "--fixed",
        type=str, dest="fixed",
        help="[Partial] IO constraints")

__doc__ = docstring_from_argparser(parser)

def generate_cad_project(context, renderer,
        top, sources, includes = None, defines = None, parameters = None, io_constraints = None):

    """Generate CAD project."""

    # pickle summary
    summary = context.summary
    summary_f = "summary.pkl"
    context.pickle_summary(summary_f)

    # prepare parameters for script generation
    param = {"summary": summary_f}

    # target design
    design = param["design"] = {}
    design["name"] = top
    design["sources"] = sources
    design["includes"] = uno(includes, tuple())
    design["defines"] = uno(defines, {})
    design["parameters"] = uno(parameters, {})

    # Synthesis settings
    syn = param["syn"] = {}
    syn["generic"] = os.path.join(summary.cwd, summary.yosys["script"])
    syn["design"] = "syn.tcl"
    
    # VPR settings
    vpr = param["vpr"] = {}
    vpr["channel_width"] = summary.vpr["channel_width"]
    vpr["archdef"] = os.path.join(summary.cwd, summary.vpr["arch"])
    vpr["rrgraph"] = os.path.join(summary.cwd, summary.vpr["rrg"])
    if io_constraints is not None:
        vpr["io_constraints"] = io_constraints

    # add script generation tasks
    renderer.add_generic(syn["design"], "synth.design.tmpl.tcl", **param)
    renderer.add_generic("Makefile", "impl.tmpl.mk", **param)

if __name__ == '__main__':
    args = parser.parse_args()
    _logger = logging.getLogger(__name__)
    enable_stdout_logging(__name__, logging.INFO)

    # preprocess
    if not args.sources:
        raise PRGAAPIError("No Verilog sources specified for the target design")
    
    defines = {}
    for s in args.defines:
        tokens = s.split("=")
        defines[tokens[0]] = None if len(tokens) == 1 else tokens[1]

    params = {}
    for s in args.parameters:
        tokens = s.split("=")
        params[tokens[0]] = tokens[1]

    # unpickle context
    _logger.info("Unpickling architecture context: {}".format(args.context))
    context = Context.unpickle(args.context)

    # generate project
    _logger.info("Generating CAD project ...")
    r = FileRenderer(os.path.join(os.path.dirname(__file__), "templates"))
    generate_cad_project(context, r, args.top, args.sources, args.includes, defines, params, args.fixed)

    r.render()
    _logger.info("CAD project generated. Bye")
