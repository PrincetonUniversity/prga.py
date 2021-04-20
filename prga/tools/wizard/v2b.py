# -*- encoding: ascii -*-

from ..util import create_argparser, docstring_from_argparser
from ...core.context import Context
from ...renderer.renderer import FileRenderer
from ...util import enable_stdout_logging, uno
from ...exception import PRGAAPIError

import os, logging
from ruamel.yaml import YAML
from copy import deepcopy

__all__ = ['generate_v2b_project']

import argparse
_help = """PRGA Verilog-to-Bitstream project generator.
    
Auto-generate Makefile, synthesis script, etc. This tool takes a configuration file in YAML or JSON format. The
configuration file requires the following keys::

    context (string): File name of the pickled PRGA context
    app (map): Data needed to describe the application to be mapped onto the FPGA
        name (string): Name of the top-level module
        sources (list of strings): Verilog source files
        includes (list of strings): [optional] Include directories
        defines (map of strings to strings, numbers or null): [optional] Define macros for Verilog preprocessing
        parameters (map of strings to strings or numbers): [optional] Parameterization of the top-level module

The configuration file takes these optional keys::

    constraints (map): Various constraints
        io (string): File name of the [partial] IO constraint
"""

_parser = create_argparser(__name__, description=_help, formatter_class=argparse.RawTextHelpFormatter)

_parser.add_argument("configuration", type=argparse.FileType('r'), metavar="CONFIG.YAML",
        help="Configuration file in YAML or JSON format")
_parser.add_argument("-o", "--output", type=str,
        help="Output directory. All files are generated into the current directory by default")

__doc__ = docstring_from_argparser(_parser)

def generate_v2b_project(context, renderer, config, output = None):

    """Generate Verilog-to-Bitstream project."""

    output = uno(output, os.getcwd())
    os.makedirs(output, exist_ok = True)

    # pickle summary
    summary = context.summary
    summary_f = os.path.join(output, "summary.pkl")
    context.pickle_summary(summary_f)

    # prepare parameters for script generation
    param = {
            "abspath": lambda p: os.path.abspath(os.path.expandvars(p)),
            "summary": "summary.pkl",
            }

    # Synthesis settings
    syn = param["syn"] = {}
    syn["generic"] = { k: os.path.join(summary.cwd, v)
            for k, v in summary.yosys["scripts"].items() }
    syn["app"] = os.path.join("syn.tcl")
    
    # VPR settings
    vpr = param["vpr"] = {}
    vpr["channel_width"] = summary.vpr["channel_width"]
    vpr["archdef"] = os.path.join(summary.cwd, summary.vpr["arch"])
    vpr["rrgraph"] = os.path.join(summary.cwd, summary.vpr["rrg"])

    # add script generation tasks
    renderer.add_generic(os.path.join(output, "syn.tcl"), "synth.app.tmpl.tcl", **param, **config)
    renderer.add_generic(os.path.join(output, "Makefile"), "impl.tmpl.mk", **param, **config)

if __name__ == '__main__':
    _logger = logging.getLogger(__name__)
    enable_stdout_logging(__name__, logging.INFO)
    args = _parser.parse_args()

    _logger.info("Parsing configuration: {}".format(args.configuration.name))
    config = YAML().load(args.configuration)

    # create output directory 
    output = os.getcwd()
    if args.output is not None:
        os.makedirs(args.output, exist_ok = True)
        output = os.path.abspath(args.output)

    # cd to the directory which the specified configuration is in
    if (dir_ := os.path.dirname(args.configuration.name)):
        os.chdir(dir_)

    # unpickle context
    context_f = os.path.abspath(os.path.expandvars(config["context"]))
    _logger.info("Unpickling architecture context: {}".format(config["context"]))
    context = Context.unpickle(context_f)

    # generate project
    _logger.info("Generating Verilog-to-Bitstream project ...")
    r = FileRenderer(os.path.join(os.path.dirname(__file__), "templates"))
    config = deepcopy(config)
    config["context"] = context_f
    generate_v2b_project(context, r, config, output)

    r.render()
    _logger.info("Verilog-to-Bitstream project generated. Bye")
