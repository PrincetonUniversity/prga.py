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

        blackbox = None
        memory = {}
        techmap = {}

        lut_sizes = []
        for primitive in iter_all_primitives(context):
            if primitive.primitive_class in (PrimitiveClass.inpad, PrimitiveClass.outpad, PrimitiveClass.iopad,
                    PrimitiveClass.flipflop):
                continue
            elif primitive.primitive_class.is_lut:
                lut_sizes.append(len(primitive.ports['in']))
            elif primitive.primitive_class.is_memory:
                if blackbox is None:
                    blackbox = os.path.abspath(os.path.join(self.prefix, 'lib.v'))
                bram_rule = memory.setdefault('rule',
                        os.path.abspath(os.path.join(self.prefix, 'bram.rule')))
                memory_techmap = memory.setdefault('techmap',
                        os.path.abspath(os.path.join(self.prefix, 'bram_techmap.v')))
                ysgen.generate_memory(blackbox, memory_techmap, bram_rule, primitive)
                entry = context.yosys_template_registry.memory_entries.get(primitive.name)
                if entry is not None:
                    memory.setdefault('premap_commands', []).extend(entry.premap_commands)
            else:
                entry = context.yosys_template_registry.blackbox_entries.get(primitive.name)
                if entry is not None:
                    techmap.setdefault('premap_commands', []).extend(entry.premap_commands)
                if blackbox is None:
                    blackbox = os.path.abspath(os.path.join(self.prefix, 'lib.v'))
                ysgen.generate_blackbox(blackbox,
                        techmap.setdefault('techmap', os.path.abspath(os.path.join(self.prefix, 'techmap.v'))),
                        primitive)
        script = os.path.abspath(os.path.join(self.prefix, 'synth.ys'))
        ysgen.generate_script(open(script, OpenMode.wb),
                ','.join('{0}:{0}'.format(size) for size in sorted(lut_sizes)),
                [blackbox] if blackbox is not None else [], [memory], [techmap])
        context._yosys_script = script
