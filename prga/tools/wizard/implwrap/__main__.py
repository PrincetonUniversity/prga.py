# -*- encoding: ascii -*-

from . import def_argparser
from .magic import generate_implwrap_magic
from ...ioplan import IOPlanner
from ...util import DesignIntf
from ....core.context import Context
from ....renderer import FileRenderer
from ....util import enable_stdout_logging

import logging, os

generators = {
        "magic": generate_implwrap_magic,
        }

_logger = logging.getLogger(__name__)
enable_stdout_logging(__name__, logging.INFO)
args = def_argparser(__name__).parse_args()

# validate arguments
if args.summary is None:
    _logger.error("Missing required argument: -c summary")
    exit()
elif args.design is None:
    _logger.error("Missing required argument: -d design")
    exit()
elif args.fixed is None:
    _logger.error("Missing required argument: -f IO_constraints")
    exit()
elif args.output is None:
    _logger.error("Missing required argument: -o output")
    exit()

# unpickle summary
_logger.info("Unpickling architecture context summary: {}".format(args.summary))
summary = Context.unpickle(args.summary)

# read design
_logger.info("Reading synthesized design: {}".format(args.design))
design = DesignIntf.parse_eblif(args.design)

# read IO constraints
_logger.info("Reading IO constraints: {}".format(args.fixed))
IOPlanner.parse_io_constraints(design, args.fixed)

# select the correct implementation wrapper generator
if (f := generators.get(summary.prog_type)) is None:
    _logger.error("No implementation wrapper found for programming circuitry type: {}"
            .format(summary.prog_type))
    exit()
_logger.info("Programming circuitry type: {}".format(summary.prog_type))

# generate implementation wrapper
_logger.info("Generating implementation wrapper")
r = FileRenderer()
f(summary, design, r, args.output)

r.render()

_logger.info("Implementation wrapper generated. Bye")
