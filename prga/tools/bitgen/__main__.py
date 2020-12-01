# -*- encoding: ascii -*-

from . import def_argparser
from .magic import MagicBitstreamGenerator
from ...core.context import Context
from ...util import enable_stdout_logging

import logging, os

generators = {
        "magic": MagicBitstreamGenerator,
        }

_logger = logging.getLogger(__name__)
enable_stdout_logging(__name__, logging.INFO)
args = def_argparser(__name__).parse_args()

# validate arguments
if args.summary is None:
    _logger.error("Missing required argument: -c summary")
    exit()
elif args.fasm is None:
    _logger.error("Missing required argument: -f fasm")
    exit()
elif args.output is None:
    _logger.error("Missing required argument: -o output")
    exit()

# unpickle summary
_logger.info("Unpickling architecture context summary: {}".format(args.summary))
summary = Context.unpickle(args.summary)

# select the correct bitstream generator
if (cls := generators.get(summary.prog_type)) is None:
    _logger.error("No bitstream generator found for programming circuitry type: {}"
            .format(summary.prog_type))
    exit()
_logger.info("Programming circuitry type: {}".format(summary.prog_type))

# generate bitstream
if args.verif:
    _logger.info("Generating verification bitstream ...")
    cls().generate_verif(summary, args.fasm, args.output)
else:
    _logger.info("Generating raw bitstream ...")
    cls().generate_raw(summary, args.fasm, args.output)

_logger.info("Bitstream generated. Bye")
