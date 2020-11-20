# -*- encoding: ascii -*-

from ...util import create_argparser, docstring_from_argparser
import argparse

def def_argparser(name):
    parser = create_argparser(name,
            description="Simulation project wizard for scanchain configuration circuitry")
    
    parser.add_argument('context', type=str, help="Pickled architecture context object")
    
    parser.add_argument('-c', '--compiler', type=str, choices=['vcs', 'iverilog'], dest='compiler', default="vcs",
            help="Verilog compiler used to build the simulator")
    parser.add_argument('--fix_io', type=str, dest="io",
            help="Partial or full constraints of IOs")
    
    parser.add_argument('-t', '--testbench', type=str, nargs='+', dest="testbench",
            help="Testbench file(s) for behavioral model")
    parser.add_argument('--testbench_top', type=str,
            help="Top-level module name of the testbench. Required if the testbench comprises multiple files/modules")
    parser.add_argument('--testbench_includes', type=str, nargs="+", default=[],
            help="Include directories for the testbench")
    parser.add_argument('--testbench_defines', type=str, nargs="+", default=[],
            help="Macros for the testbench. Use MACRO for valueless macro, and MACRO=VALUE for macros with value")
    parser.add_argument('--testbench_parameters', type=str, nargs="+", default=[],
            help="Parameters for the testbench: PARAMETER0=VALUE0 PARAMETER1=VALUE1 ...")
    parser.add_argument('--testbench_plus_args', type=str, nargs="+", default=[],
            help="Plus arguments to run the testbench. Use ARG for valueless args, and ARG=VALUE for args with value")
    
    parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
            help="Source file(s) for the target design")
    parser.add_argument('--model_top', type=str,
            help="Top-level module name of the target design. Required if the design comprises multiple files/modules")
    parser.add_argument('--model_includes', type=str, nargs="+", default=[],
            help="Include directories for the target design")
    parser.add_argument('--model_defines', type=str, nargs="+", default=[],
            help="Macros for the target design. Use MACRO for valueless macro, and MACRO=VALUE for macros with value")
    parser.add_argument('--model_parameters', type=str, nargs="+", default=[],
            help="Parameters for the behavioral model: PARAMETER0=VALUE0 PARAMETER1=VALUE1 ...")
    
    parser.add_argument('--summary', type=str, default="summary.pkl",
            help="Name of the pickled summary file. 'summary.pkl' by default")
    parser.add_argument('--makefile', type=str, default="Makefile",
            help="Name of the generated Makefile. 'Makefile' by default")
    parser.add_argument('--wrapper', type=str,
            help="Name of the generated testbench wrapper. 'TESTBENCH_wrapper.v' by default")
    parser.add_argument('--yosys_script', type=str, default="synth.ys",
            help="Name of the generated design-specific synthesis script. 'synth.ys' by default")
    
    return parser

__doc__ = docstring_from_argparser(def_argparser(__name__))
