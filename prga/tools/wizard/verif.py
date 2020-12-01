# -*- encoding: ascii -*-

from ..util import DesignIntf, create_argparser, docstring_from_argparser
from ...core.context import Context
from ...renderer import FileRenderer
from ...util import enable_stdout_logging, uno

import sys, os, logging
from ruamel.yaml import YAML

__all__ = ['generate_verif_makefile', 'generate_verif_testbench']

import argparse
_help = """PRGA verification project generator.

    Auto-generate Makefile, testbench, etc. This tool depends on the Verilog-to-Bitstream project generator tool. This
    tool also takes a configuration file in YAML or JSON format. The configuration file requires the following keys:

        compiler \(string\): Verilog compiler. Supported values are: "vcs", "iverilog"
        tests \(map of maps\): Tests for the target design. The Verilog writing instruction can be found at <TODO>
            [key] \(string\): Name of the test
            sources \(list of strings\): Verilog source files of the test
            includes \(list of strings\): [optional] Include directories of the test
            defines \(map of strings to strings, numbers or null\): [optional] Define macros for Verilog
                preprocessing
            parameters \(map of strings to strings or numbers\): [optional] Parameterization of the top-level test
"""

_parser = create_argparser(__name__, description=_help, formatter_class=argparse.RawDescriptionHelpFormatter)

_subparsers = _parser.add_subparsers(dest="subcommand",
        description="Subcommands. Run with '{{subcommand}} -h' for more help")

# Verification Makefile generator
_parser_mk = _subparsers.add_parser("makefile", aliases=["mk", "make"],
        description="Generate Makefile")
_parser_mk.add_argument("configuration", type=str, metavar="CONFIG.YAML",
        help="Configuration file in YAML or JSON format")
_parser_mk.add_argument("v2b_dir", type=str,
        help="Verilog-to-Bitstream project directory")
_parser_mk.add_argument("-t", "--test", type=str, dest="test",
        help="Explicitly select one test from the tests defined in the configuration file")
_parser_mk.add_argument("-o", "--output", type=str, dest="output",
        help="Output directory. All files are generated into the current directory by default")

# Verification testbench generator
_parser_tb = _subparsers.add_parser("testbench", aliases=["tb"],
        description="Generate testbench")
_parser_tb.add_argument("configuration", type=str, metavar="CONFIG.YAML",
        help="Configuration file in YAML or JSON format")
_parser_tb.add_argument("v2b_dir", type=str,
        help="Verilog-to-Bitstream project directory")
_parser_tb.add_argument("-t", "--test", type=str, dest="test",
        help="Explicitly select one test from the tests defined in the configuration file")
_parser_tb.add_argument("-o", "--output", type=str, dest="output",
        help="Output directory. All files are generated into the current directory by default")

def generate_verif_makefile(summary, renderer, v2b_dir, config_f, config = None, test = None, output = None):
    """Generate verification makefile."""

    output = uno(output, os.getcwd())
    os.makedirs(output, exist_ok = True)

    # gather FPGA resources
    fpga = {
            "sources": tuple(os.path.join(summary.cwd, src) for src in summary.rtl["sources"].values()),
            "includes": tuple(os.path.join(summary.cwd, inc) for inc in summary.rtl["includes"]),
            }

    # read config if not already read
    if config is None:
        config = YAML().load(open(config_f))

    # add script generation tasks
    renderer.add_generic(os.path.join(output, "Makefile"), "verif.tmpl.mk",
            config = config_f,
            compiler = config["compiler"],
            v2b_dir = v2b_dir,
            design = config["design"],
            test_name = test,
            test = config["tests"][test],
            fpga = fpga,
            abspath = os.path.abspath)

def generate_verif_testbench(renderer, v2b_dir, config, test = None, output = None):
    """Generate verification testbench."""

    output = uno(output, os.getcwd())
    os.makedirs(output, exist_ok = True)

    # read synthesized netlist
    design = DesignIntf.parse_eblif(os.path.join(v2b_dir, "syn.eblif"))

    # add testbench generation tasks
    renderer.add_generic(os.path.join(output, "tb.v"), "tb.tmpl.v",
            test_name = test,
            test = config["tests"][test],
            design = design,
            postsyn = {"name": "postsyn"},
            impl = {"name": "postimpl"},
            )

__doc__ = docstring_from_argparser(_parser)

if __name__ == '__main__':
    _logger = logging.getLogger(__name__)
    enable_stdout_logging(__name__, logging.INFO)
    args = _parser.parse_args()

    # echo subcommand selected
    subcommand = None
    if args.subcommand is None:
        _logger.error("No subcommand selected. Run with '-h' for more help")
        _parser.print_usage()
        exit()
    elif args.subcommand in ("makefile", "mk", "make"):
        subcommand = "mk"
    elif args.subcommand in ("testbench", "tb"):
        subcommand = "tb"
    else:
        _logger.error("Unsupported subcommand: {}".format(args.subcommand))
        _parser.print_usage()
        exit()
    _logger.info("Executing subcommand: {}".format(subcommand))

    # parse configuration file
    _logger.info("Parsing configuration: {}".format(args.configuration))
    config_f = os.path.abspath(args.configuration)
    config = YAML().load(open(args.configuration))

    # select test
    if (tests := config.get("tests")) is None or len(tests) == 0:
        _logger.error("No test defined in configuration file: {}".format(args.configuration))
        exit()

    if (test := args.test) is None:
        test = next(iter(tests))
    elif test not in tests:
        _logger.error("Test '{}' not found in configuration file: {}".format(args.configuration))
        exit()

    # remember v2b project dir
    v2b_dir = os.path.abspath(args.v2b_dir)

    # create output directory 
    output = os.getcwd()
    if args.output is not None:
        os.makedirs(args.output, exist_ok = True)
        output = os.path.abspath(args.output)

    # cd to the directory which the specified configuration is in
    if (dir_ := os.path.dirname(args.configuration)):
        os.chdir(dir_)

    # run subcommand
    r = FileRenderer(os.path.join(os.path.dirname(__file__), "templates"))
    if subcommand == "mk":
        _logger.info("Generating verification Makefile ...")
        generate_verif_makefile(r, v2b_dir, config_f, config, test, output)

        r.render()
        _logger.info("Verification Makefile generated. Bye")
    elif subcommand == "tb":
        _logger.info("Generating verification testbench ...")
        generate_verif_testbench(r, v2b_dir, config, test, output)

        r.render()
        _logger.info("Verification testbench generated. Bye")
