# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from . import def_argparser
from .tbgen import generate_scanchain_testbench_wrapper
from .mkgen import generate_scanchain_makefile
from ...util import find_verilog_top, parse_parameters
from ...ioplan.ioplan import IOPlanner
from ...ysgen import generate_yosys_script
from ....core.context import Context
from ....renderer.renderer import FileRenderer
from ....util import enable_stdout_logging, uno

import os
import argparse

import logging
_logger = logging.getLogger(__name__)

args = def_argparser(__name__).parse_args()
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

_logger.info("Generating IO constraints ...")
io_constraints = IOPlanner.autoplan(context.summary, model_top, 
        IOPlanner.parse_io_constraints(args.io) if args.io is not None else {})
IOPlanner.print_io_constraints(io_constraints, "io.pads")

_logger.info("Pickling architecture context summary ...")
context.pickle_summary(args.summary)

_logger.info("Generating testbench wrapper ...")
wrapper = uno(args.wrapper, '{}_wrapper.v'.format(testbench_top.name))
generate_scanchain_testbench_wrapper(context, r, wrapper, testbench_top, model_top, io_constraints)

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
