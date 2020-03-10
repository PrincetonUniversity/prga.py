# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.core.context import Context
from prga.renderer.renderer import FileRenderer
from prga.util import enable_stdout_logging, uno

from .tbgen import generate_scanchain_testbench_wrapper
from .mkgen import generate_scanchain_makefile
from ...util import find_verilog_top, parse_parameters, parse_io_bindings
from ...iobind import iobind
from ...ysgen import generate_yosys_script

import os
import argparse

import logging
_logger = logging.getLogger(__name__)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description="Simulation project wizard for scanchain configuration circuitry")
    
    parser.add_argument('context', type=str, help="Pickled architecture context object")
    
    parser.add_argument('-c', '--compiler', type=str, choices=['vcs', 'iverilog'], dest='compiler', default="vcs",
            help="Verilog compiler used to build the simulator")
    parser.add_argument('--fix_io', type=str, dest="io",
            help="Partial or full assignments of IO pads")
    
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
    
    parser.add_argument('--summary', type=str, default="summary.pickled",
            help="Name of the pickled summary file. 'summary.pickled' by default")
    parser.add_argument('--makefile', type=str, default="Makefile",
            help="Name of the generated Makefile. 'Makefile' by default")
    parser.add_argument('--wrapper', type=str,
            help="Name of the generated testbench wrapper. 'TESTBENCH_wrapper.v' by default")
    parser.add_argument('--yosys_script', type=str, default="synth.ys",
            help="Name of the generated design-specific synthesis script. 'synth.ys' by default")
    
    args = parser.parse_args()
    enable_stdout_logging(__name__, logging.INFO)
    
    # create renderer
    r = FileRenderer(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates'),
            os.path.join(os.path.abspath(os.path.dirname(__file__)), "..", "..", "templates"))
    
    _logger.info("Unpickling architecture context: {}".format(args.context))
    context = Context.unpickle(args.context)
    if not isinstance(context, Context):
        raise PRGAAPIError("'{}' is not a pickled architecture context object".format(args.context))
    
    _logger.info("Reading target design ...")
    if args.model is None:
        raise PRGAAPIError("Source file(s) for target design not given")
    model_top = find_verilog_top(args.model, args.model_top)
    model_top.parameters = parse_parameters(args.model_parameters) 
    
    _logger.info("Reading testbench ...")
    if args.testbench is None:
        raise PRGAAPIError("Source file(s) for testbench not given")
    testbench_top = find_verilog_top(args.testbench, args.testbench_top)
    testbench_top.parameters = parse_parameters(args.testbench_parameters) 
    
    _logger.info("Assigning IO ...")
    io_assignments = iobind(context.summary, model_top, 
            parse_io_bindings(args.io) if args.io is not None else {})
    ostream = open('io.pads', 'w')
    for name, (x, y, subblock) in iteritems(io_assignments):
        ostream.write("{} {} {} {}\n".format(name, x, y, subblock))

    _logger.info("Pickling architecture context summary ...")
    context.pickle_summary(args.summary)
    
    _logger.info("Generating testbench wrapper ...")
    wrapper = uno(args.wrapper, '{}_wrapper.v'.format(testbench_top.name))
    generate_scanchain_testbench_wrapper(context, r, wrapper, testbench_top, model_top, io_assignments)
    
    _logger.info("Generating design-specific synthesis script ...")
    generate_yosys_script(context.summary, r, args.yosys_script, model_top, args.model)
    
    _logger.info("Generating Makefile ...")
    generate_scanchain_makefile(args.summary, context.summary, r, args.makefile, args.yosys_script,
            testbench_top, args.testbench, model_top, args.model, 'io.pads', wrapper,
            args.compiler,
            args.testbench_plus_args, args.testbench_includes, args.testbench_defines,
            args.model_includes, args.model_defines)
    
    r.render()

    _logger.info("Simulation project generated. Bye")
