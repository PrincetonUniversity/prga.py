# -*- encoding: ascii -*-

from . import def_argparser
from ...ioplan import IOPlanner
from ...util import AppIntf
from ....core.context import Context
from ....renderer import FileRenderer
from ....util import enable_stdout_logging

import logging, os

def generate_implwrap_common(summary, app, renderer, f, template):
    if ((templates_dir := os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates"))
            not in renderer.template_search_paths):
        renderer.template_search_paths.insert(0, templates_dir)

    renderer.add_generic(f, template,
            app = app,
            summary = summary)

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
elif args.fixed is None:
    _logger.error("Missing required argument: -f IO_constraints")
    exit()
elif args.output is None:
    _logger.error("Missing required argument: -o output")
    exit()

# unpickle summary
_logger.info("Unpickling architecture context summary: {}".format(args.summary))
summary = Context.unpickle(args.summary)

# read application
_logger.info("Reading synthesized application: {}".format(args.application))
app = AppIntf.parse_eblif(args.application)

# read IO constraints
_logger.info("Reading IO constraints: {}".format(args.fixed))
IOPlanner.parse_io_constraints(app, args.fixed)

# select the correct implementation wrapper generator
prog_type = summary.prog_type.split('.')[-1]
if args.prog_type is not None:
    _logger.info("Using programming circuitry type: {} ({} used in architecture)"
            .format(args.prog_type, prog_type))
    prog_type = args.prog_type
else:
    _logger.info("Using programming circuitry type: {}".format(prog_type))

# generate implementation wrapper
_logger.info("Generating implementation wrapper")
r = FileRenderer()
generate_implwrap_common(summary, app, r, args.output, prog_type + ".tmpl.v")
r.render()

_logger.info("Implementation wrapper generated. Bye")
