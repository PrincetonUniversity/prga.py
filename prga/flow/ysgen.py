# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.primitive.common import PrimitiveClass
from prga.ysgen.ysgen import YosysGenerator
from prga.flow.flow import AbstractPass
from prga.flow.util import iter_all_primitives
from prga.util import Object

import os

__all__ = ['GenerateYosysResources']

# ----------------------------------------------------------------------------
# -- Generate Yosys Resources ------------------------------------------------
# ----------------------------------------------------------------------------
class GenerateYosysResources(Object, AbstractPass):
    """Generate blackbox modules, BRAM mapping rules, and techmap files for Yosys.

    Args:
        prefix (:obj:`str`): Prefix to the files
    """

    __slots__ = ['prefix']
    def __init__(self, prefix = ''):
        self.prefix = prefix

    @property
    def key(self):
        """Key of this pass."""
        return 'syn.resource'

    def run(self, context):
        makedirs(self.prefix)
        ysgen = YosysGenerator(context.yosys_template_registry, context._additional_template_search_paths)
        blackbox = open(os.path.abspath(os.path.join(self.prefix, 'lib.v')), OpenMode.w)
        bram_rule = open(os.path.abspath(os.path.join(self.prefix, 'bram.rule')), OpenMode.w)
        techmap = open(os.path.abspath(os.path.join(self.prefix, 'techmap.v')), OpenMode.w)
        for primitive in iter_all_primitives(context):
            # blackbox?
            if primitive.primitive_class in (PrimitiveClass.memory, PrimitiveClass.custom):
                ysgen.generate_blackbox(blackbox, primitive)
            # bram rules?
            if primitive.primitive_class.is_memory:
                ysgen.generate_bram_rule(bram_rule, primitive)
            # techmap?
            if primitive.primitive_class in (PrimitiveClass.memory, PrimitiveClass.custom, PrimitiveClass.multimode):
                ysgen.generate_techmap(techmap, primitive)
