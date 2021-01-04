# -*- encoding: ascii -*-

from . import def_argparser
from .v2b import generate_v2b_project
from .verif import generate_verif_makefile
from ...core.context import Context
from ...renderer import FileRenderer
from ...util import enable_stdout_logging

import logging, os
from ruamel.yaml import YAML

_logger = logging.getLogger(__name__)
enable_stdout_logging(__name__, logging.INFO)
args = def_argparser(__name__).parse_args()

# parse configuration
_logger.info("Parsing configuration: {}".format(args.configuration))
config_f = os.path.abspath(args.configuration)
config = YAML().load(open(args.configuration))

# create output directory
output = os.getcwd()
if args.output is not None:
    os.makedirs(args.output, exist_ok = True)

# cd to the directory which the specified configuration is in
if (dir_ := os.path.dirname(args.configuration)):
    os.chdir(dir_)

# unpickle context
_logger.info("Unpickling architecture context: {}".format(config["context"]))
context = Context.unpickle(os.path.expandvars(config["context"]))

r = FileRenderer(os.path.join(os.path.dirname(__file__), "templates"))

# generate Verilog-to-Bitstream project
_logger.info("Generating Verilog-to-Bitstream project")
generate_v2b_project(context, r, config,
        (v2b_dir := os.path.join(output, "design")))

# if there are tests, generate test projects
for test_name, test in config.get("tests", {}).items():
    _logger.info("Generating verification Makefile for test: {}".format(test_name))
    generate_verif_makefile(context.summary, r, v2b_dir, config_f, config, test_name,
            os.path.join(output, "tests", test_name))

r.render()
_logger.info("CAD project generated. Bye")
