# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..util import create_argparser, docstring_from_argparser
import argparse

def def_argparser(name):
    parser = create_argparser(name, description="IO assignment generator")

    parser.add_argument('summary', type=argparse.FileType(OpenMode.rb),
            help="Pickled context or summary object")
    parser.add_argument('-o', '--output', type=str, dest="output",
            help="Generated IO assignments")
    parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
            help="Source file(s) for behavioral model")
    parser.add_argument('--model_top', type=str,
            help="Top-level module name of the behavioral model. Required if the model comprises multiple files/modules")
    parser.add_argument('-f', '--fix', type=str, dest="fixed",
            help="Partial assignments")

    return parser

__doc__ = docstring_from_argparser(def_argparser(__name__))
