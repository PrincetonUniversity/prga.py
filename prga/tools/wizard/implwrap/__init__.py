# -*- encoding: ascii -*-

from ..util import create_argparser, docstring_from_argparser
import argparse

def def_argparser(name):
    parser = create_argparser(name,
            description="Generate FPGA-implemented design wrapper")

    parser.add_argument("-c", "--summary", type=str, metavar="summary.pkl",
            help="Pickled PRGA architecture context summary")
    parser.add_argument("-d", "--design", type=str, metavar="syn.eblif",
            help="Synthesized target design")
    parser.add_argument('-o', '--output', type=str, dest="output",
            help="Output file for the IO constraints")
    parser.add_argument('-f', '--fix', type=str, dest="fixed",
            help="Partial IO constraints")

    return parser

__doc__ = docstring_from_argparser(def_argparser(__name__))
__all__ = []
