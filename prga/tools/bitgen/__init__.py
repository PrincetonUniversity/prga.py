# -*- encoding: ascii -*-

from ..util import create_argparser, docstring_from_argparser
import argparse

def def_argparser(name):
    parser = create_argparser(name,
            description="PRGA bitstream generator")

    parser.add_argument("-c", "--context", metavar="context",
            help="Pickled PRGA architecture context")
    parser.add_argument("-f", "--fasm", metavar="fasm",
            help="Raw FASM input")
    parser.add_argument("-o", "--output", metavar="output",
            help="Output file")

    return parser

__doc__ = docstring_from_argparser(def_argparser(__name__))
__all__ = []
