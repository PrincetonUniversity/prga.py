# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from . import def_argparser
from .ioplan import IOPlanner
from ..util import find_verilog_top
from ...core.context import Context
from ...util import enable_stdout_logging

import logging, sys
_logger = logging.getLogger(__name__)

args = def_argparser(__name__).parse_args()
enable_stdout_logging(__name__, logging.INFO)

summary = Context.unpickle(args.summary)
_logger.info("Architecture context (or summary) parsed")
io_constraints = IOPlanner.autoplan(summary, find_verilog_top(args.model, args.model_top),
        IOPlanner.parse_io_constraints(args.fixed) if args.fixed is not None else {})
IOPlanner.print_io_constraints(io_constraints, sys.stdout if args.output is None else open(args.output, 'w'))
_logger.info("Constraints generated. Bye")
