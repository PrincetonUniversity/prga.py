# -*- encoding: ascii -*-

from . import def_argparser
from .ioplan import IOPlanner
from .util import DesignIntf
from ...core.context import Context
from ...util import enable_stdout_logging

import logging, sys
_logger = logging.getLogger(__name__)

args = def_argparser(__name__).parse_args()
enable_stdout_logging(__name__, logging.INFO)

_logger.info("Parsing architecture context (or summary): {}".format(args.summary))
summary = Context.unpickle(args.summary)

_logger.info("Extracting target design interface: {}".format(args.design))
d = DesignIntf.parse_eblif(args.design)

if args.fixed is not None:
    _logger.info("Parsing partial IO constraints: {}".format(args.fixed))
    IOPlanner.parse_io_constraints(d, args.fixed)

_logger.info("Autoplanning IO constraints ...")
IOPlanner.autoplan(summary, d)

_logger.info("Writing constraints ...")
IOPlanner.print_io_constraints(d, sys.stdout if args.output is None else open(args.output, "w"))

_logger.info("Constraints generated. Bye")
