# -*- encoding: ascii -*-

from . import def_argparser
from .magic import MagicBitstreamGenerator
from .scanchain import ScanchainBitstreamGenerator
from .pktchain import PktchainBitstreamGenerator
from .frame import FrameBitstreamGenerator
from ...core.context import Context
from ...util import enable_stdout_logging, uno

import logging, os

_generators = {
        'Magic':        MagicBitstreamGenerator,
        'Scanchain':    ScanchainBitstreamGenerator,
        'Pktchain':     PktchainBitstreamGenerator,
        'Frame':        FrameBitstreamGenerator,
        }

_logger = logging.getLogger(__name__)
enable_stdout_logging(__name__, logging.INFO)
args = def_argparser(__name__).parse_args()

# validate arguments
if args.context is None:
    _logger.error("Missing required argument: -c context")
    exit()
elif args.fasm is None:
    _logger.error("Missing required argument: -f fasm")
    exit()
elif args.output is None:
    _logger.error("Missing required argument: -o output")
    exit()

# unpickle context
_logger.info("Unpickling architecture context: {}".format(args.context))
context = Context.unpickle(args.context)

# select the correct bitstream generator
prog_type = uno(args.prog_type, context.prog_entry.__name__)
if prog_type != context.prog_entry.__name__:
    _logger.info("Using programming circuitry type: {} ({} used in architecture)"
            .format(prog_type, context.prog_entry.__name__))
else:
    _logger.info("Using programming circuitry type: {}".format(prog_type))
generator = _generators[prog_type](context)

# generate bitstream
_logger.info("Generating bitstream: {} from FASM: {} ...".format(args.output, args.fasm))
generator.generate_bitstream(args.fasm, args.output)

_logger.info("Bitstream generated. Bye")
