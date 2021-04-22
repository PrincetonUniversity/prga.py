# -*- encoding: ascii -*-

from ...util import create_argparser, docstring_from_argparser
import argparse

def def_argparser(name):
    parser = create_argparser(name,
            description="Generate FPGA-implemented application wrapper")

    parser.add_argument("-c", "--summary", type=str, metavar="summary.pkl",
            help="Pickled PRGA architecture context summary")
    parser.add_argument("-i", "--application", type=str, metavar="syn.eblif",
            help="Synthesized application")
    parser.add_argument('-o', '--output', type=str, dest="output",
            help="Output file for the IO constraints")
    parser.add_argument('-f', '--fix', type=str, dest="fixed",
            help="IO constraints")
    parser.add_argument("-p", "--prog_type", metavar="prog_type",
            help=("[Export Option] Overwrite the programming circuitry type in the pickled context. "
                "For example, use `Magic` to generate a fake bitstream with Verilog `force` statements. "))

    return parser

__doc__ = docstring_from_argparser(def_argparser(__name__))
__all__ = []
