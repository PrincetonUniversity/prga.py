# -*- encoding: ascii -*-

from ..util import create_argparser, docstring_from_argparser
import argparse

def def_argparser(name):
    parser = create_argparser(name, description="IO constraints generator")

    parser.add_argument('summary', type=argparse.FileType("rb"),
            help="Pickled context or summary object")
    parser.add_argument('design', type=str,
            help="Input file for the synthesized design")
    parser.add_argument('-o', '--output', type=str, dest="output",
            help="Output file for the IO constraints")
    parser.add_argument('-f', '--fix', type=str, dest="fixed",
            help="Partial IO constraints")

    return parser

__doc__ = docstring_from_argparser(def_argparser(__name__))
