# -*- encoding: ascii -*-

from . import def_argparser
from .ioplan import IOPlanner
from ..util import AppIntf
from ...core.context import Context
from ...util import enable_stdout_logging

import logging, sys

_logger = logging.getLogger(__name__)
enable_stdout_logging(__name__, logging.INFO)
args = def_argparser(__name__).parse_args()

# validate arguments
if args.summary is None:
    _logger.error("Missing required argument: -c summary")
    exit()
elif args.application is None:
    _logger.error("Missing required argument: -i application")
    exit()
elif args.output is None:
    _logger.error("Missing required argument: -o output")
    exit()

# unpickle summary
_logger.info("Parsing architecture context (or summary): {}".format(args.summary))
summary = Context.unpickle(args.summary)

_logger.info("Extracting application interface: {}".format(args.application))
d = AppIntf.parse_eblif(args.application)

if args.fixed is not None:
    _logger.info("Parsing partial IO constraints: {}".format(args.fixed))
    IOPlanner.parse_io_constraints(d, args.fixed)

_logger.info("Autoplanning IO constraints ...")
IOPlanner.autoplan(summary, d)

_logger.info("Writing constraints ...")
IOPlanner.print_io_constraints(d, sys.stdout if args.output is None else open(args.output, "w"))

_logger.info("Constraints generated. Bye")
