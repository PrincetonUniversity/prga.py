# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.core.context import Context
from prga.renderer.renderer import FileRenderer
from prga.util import enable_stdout_logging, uno

from ...util import find_verilog_top, parse_parameters

import os
import sys

__all__ = ['PktchainMkgen']

class PktchainMkgen(object):

    @classmethod
    def generate_makefile(cls,
            summary_f, summary, renderer, ostream, yosys_script,
            tb_top, tb_sources, behav_top, behav_sources, io_binding, testbench_wrapper, compiler = "vcs",
            tb_plus_args = None, tb_includes = None, tb_defines = None,
            behav_includes = None, behav_defines = None):
        """Generate Makefile for verification flow."""

        param = {}
        param["compiler"] = compiler

        # testbench wrapper
        param["testbench_wrapper"] = testbench_wrapper

        # target (behavioral model)
        target = param["target"] = {}
        target["name"] = behav_top.name
        target["sources"] = uno(behav_sources, tuple())
        target["defines"] = uno(behav_defines, tuple())

        # host (testbench)
        host = param["host"] = {}
        host["name"] = tb_top.name
        host["sources"] = uno(tb_sources, tuple())
        host["defines"] = uno(tb_defines, tuple())
        host["args"] = uno(tb_plus_args, tuple())

        # summary
        param["summary"] = summary_f

        # yosys script
        param["yosys_script"] = yosys_script

        # vpr settings
        vpr = param["vpr"] = {}
        vpr["channel_width"] = summary.vpr["channel_width"]
        vpr["archdef"] = os.path.join(summary.vpr["arch"])
        vpr["rrgraph"] = os.path.join(summary.vpr["rrg"])
        vpr["io_binding"] = io_binding

        # fpga sources
        param["rtl"] = tuple(iter(itervalues(summary.rtl["sources"])))
        param["includes"] = tuple(summary.rtl["includes"])

        # generate
        renderer.add_generic( ostream, "tmpl.Makefile", **param )

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
            description="Makefile generator for pktchain configuration circuitry")
    
    parser.add_argument('summary', type=str, help="Pickled architecture context summary object")
    parser.add_argument('io_binding', type=str, help="IO assignment")
    parser.add_argument('testbench_wrapper', type=str, help="Testbench wrapper")
    parser.add_argument('yosys_script', type=str, help="Design-specific synthesis script")
    parser.add_argument('-o', '--output', type=argparse.FileType("w"), dest='output',
            help="Generated Makefile")

    parser.add_argument('-t', '--testbench', type=str, nargs='+', dest="testbench",
            help="Testbench file(s) for behavioral model")
    parser.add_argument('--testbench_top', type=str,
            help="Top-level module name of the testbench. Required if the testbench comprises multiple files/modules")
    parser.add_argument('--testbench_includes', type=str, nargs="+", default=[],
            help="Include directories for the testbench")
    parser.add_argument('--testbench_defines', type=str, nargs="+", default=[],
            help="Macros for the testbench. Use MACRO for valueless macro, and MACRO=VALUE for macros with value")
    parser.add_argument('--testbench_plus_args', type=str, nargs="+", default=[],
            help="Plus arguments to run the testbench. Use ARG for valueless args, and ARG=VALUE for args with value")

    parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
            help="Source file(s) for the target design")
    parser.add_argument('--model_top', type=str,
            help="Top-level module name of the target design. Required if the design comprises multiple files/modules")
    parser.add_argument('--model_includes', type=str, nargs="+", default=[],
            help="Include directories for the target design")
    parser.add_argument('--model_defines', type=str, nargs="+", default=[],
            help="Macros for the target design. Use MACRO for valueless macro, and MACRO=VALUE for macros with value")

    parser.add_argument('-c', '--compiler', type=str, choices=['vcs', 'iverilog'], dest='compiler', default="vcs",
            help="Verilog compiler used to build the simulator")

    args = parser.parse_args()

    tb_top = find_verilog_top(args.testbench, args.testbench_top)
    behav_top = find_verilog_top(args.model, args.model_top)
    ostream = sys.stdout if args.output is None else args.output

    summary = Context.unpickle(args.summary)
    if isinstance(summary, Context):
        summary = summary.summary

    # create renderer
    r = FileRenderer(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates'))

    PktchainMkgen.generate_makefile(args.summary, summary, r, ostream, args.yosys_script,
            tb_top, args.testbench, behav_top, args.model, args.io_binding, args.testbench_wrapper,
            args.compiler,
            args.testbench_plus_args, args.testbench_includes, args.testbench_defines,
            args.model_includes, args.model_defines)
