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
    parser.add_argument("-p", "--prog_type", metavar="prog_type",
            help=("[Export Option] Overwrite the programming circuitry type in the pickled context. "
                "For example, use `Magic` to generate a fake bitstream with Verilog `force` statements. "))

    return parser

__doc__ = docstring_from_argparser(def_argparser(__name__))
__all__ = []
