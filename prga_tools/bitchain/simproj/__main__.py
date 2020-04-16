# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import enable_stdout_logging, uno
from prga.flow.context import ArchitectureContext
from prga.exception import PRGAAPIError

from prga_tools.util import find_verilog_top, parse_io_bindings, parse_parameters
from prga_tools.iobind import iobind
from prga_tools.ysgen import generate_yosys_script
from prga_tools.bitchain.simproj.tbgen import generate_testbench_wrapper
from prga_tools.bitchain.simproj.mkgen import generate_makefile

import argparse
import logging
import jinja2 as jj
import os

_logger = logging.getLogger(__name__)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
            description="Simulation project wizard for bitchain-style configuration circuitry")
    
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
    
    parser.add_argument('--makefile', type=str,
            help="Name of the generated Makefile. 'Makefile' by default")
    parser.add_argument('--wrapper', type=str,
            help="Name of the generated testbench wrapper. 'TESTBENCH_wrapper.v' by default")
    parser.add_argument('--yosys_script', type=str,
            help="Name of the generated design-specific synthesis script. 'synth.ys' by default")
    
    args = parser.parse_args()
    enable_stdout_logging(__name__, logging.INFO)
    
    # get verilog template
    env = jj.Environment(loader=jj.FileSystemLoader(
        os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates'), ))
    
    _logger.info("Unpickling architecture context: {}".format(args.context))
    context = ArchitectureContext.unpickle(args.context)
    channel_width = 2 * sum(sgmt.width * sgmt.length for sgmt in itervalues(context.segments))
    
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
    io_assignments = iobind(context, model_top, 
            parse_io_bindings(args.io) if args.io is not None else {})
    ostream = open('io.pads', 'w')
    for name, (x, y, subblock) in iteritems(io_assignments):
        ostream.write("{} {} {} {}\n".format(name, x, y, subblock))
    
    _logger.info("Generating testbench wrapper ...")
    wrapper = uno(args.wrapper, '{}_wrapper.v'.format(testbench_top.name))
    generate_testbench_wrapper(context, env.get_template('tb.tmpl.v'), wrapper, testbench_top, model_top, io_assignments)
    
    _logger.info("Generating design-specific synthesis script ...")
    script = uno(args.yosys_script, 'synth.ys')
    generate_yosys_script(open(script, 'w'), args.model, model_top, context._yosys_script)
    
    _logger.info("Generating Makefile ...")
    makefile = uno(args.makefile, 'Makefile')
    ostream = open(makefile, 'w')
    generate_makefile(args.context, env.get_template('tmpl.Makefile'), ostream,
            testbench_top, args.testbench, model_top, args.model, script,
            channel_width, context._vpr_archdef, context._vpr_rrgraph,
            'io.pads', context._verilog_sources, wrapper, args.compiler, args.testbench_plus_args,
            args.testbench_includes, args.testbench_defines, args.model_includes, args.model_defines)
    
    _logger.info("Simulation project generated. Bye")
