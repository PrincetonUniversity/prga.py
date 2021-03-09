# -*- encoding: ascii -*-

from ..util import create_argparser, docstring_from_argparser
import argparse

__all__ = []

def def_argparser(name):
    help_ = """PRGA CAD flow wizard.

Auto-generate Makefile, synthesis script, testbench, etc. This tool takes a configuration file in YAML or JSON
format. The configuration file requires the following keys::

    context (string): File name of the pickled PRGA context
    design (map): Data needed to describe the target design to be mapped onto the FPGA
        name (string): Name of the top-level module
        sources (list of strings): Verilog source files of the design
        includes (list of strings): [optional] Include directories of the design
        defines (map of strings to strings, numbers or null): [optional] Define macros for Verilog preprocessing
        parameters (map of strings to strings or numbers): [optional] Parameterization of the top-level module

The configuration file takes these optional keys::

    compiler (string): Verilog compiler. Supported values are: "vcs", "verilog"
    constraints (map): Various constraints
        io (string): File name of the [partial] IO constraint
    tests (map of maps): Tests for the target design, indexed by the name of the test
        sources (list of strings): Verilog source files of the test
        includes (list of strings): [optional] Include directories of the test
        defines (map of strings to strings, numbers or null): [optional] Define macros for Verilog preprocessing
        parameters (map of strings to strings or numbers): [optional] Parameterization of the top-level test
        comp_flags (list of strings): Additional flags for compilation
        run_flags (list of strings): Additional flags for simulation
"""

    parser = create_argparser(name, description=help_, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("configuration", type=str, metavar="CONFIG.YAML",
            help="Configuration file in YAML or JSON format")
    parser.add_argument("-o", "--output", type=str,
            help="Output directory. All files are generated into the current directory by default")

    return parser

__doc__ = docstring_from_argparser(def_argparser(__name__))
