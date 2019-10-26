# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.const import ZERO
from prga.arch.module.common import ModuleClass
from prga.arch.primitive.common import PrimitivePortClass
from prga.flow.flow import AbstractPass
from prga.flow.util import analyze_hierarchy
from prga.util import Object

__all__ = ['ZeroingUnusedLUTInputs', 'ZeroingBRAMWriteEnable']

# ----------------------------------------------------------------------------
# -- Pass: ZeroingUnusedLUTInputs --------------------------------------------
# ----------------------------------------------------------------------------
class ZeroingUnusedLUTInputs(Object, AbstractPass):
    """Add connections to the LUT inputs, so they are grounded when not used."""

    @property
    def key(self):
        return "opt.zeroing_unused_lut_inputs"

    @property
    def passes_after_self(self):
        return ("completion.switch", "physical", "config", "rtl", "vpr", "asicflow")

    def run(self, context):
        hierarchy = analyze_hierarchy(context)
        stack = {context.top.name: context.top}
        visited = set()
        while stack:
            name, module = stack.popitem()
            visited.add(name)
            if module.module_class in (ModuleClass.cluster, ModuleClass.io_block, ModuleClass.logic_block):
                for instance in itervalues(module.instances):
                    if instance.module_class.is_primitive and instance.model.primitive_class.is_lut:
                        for bit in instance.pins['in']:
                            sources = tuple(iter(bit.user_sources))
                            bit.remove_user_sources()
                            bit.add_user_sources((ZERO, ) + sources)
            for subname, submod in iteritems(hierarchy[name]):
                if subname in stack or subname in visited:
                    continue
                elif submod.module_class not in (ModuleClass.array, ModuleClass.tile, ModuleClass.io_block,
                        ModuleClass.logic_block, ModuleClass.cluster):
                    continue
                stack[subname] = submod

# ----------------------------------------------------------------------------
# -- Pass: ZeroingBRAMWriteEnable --------------------------------------------
# ----------------------------------------------------------------------------
class ZeroingBRAMWriteEnable(Object, AbstractPass):
    """Set the default connection of a BRAM write-enable to zero."""

    @property
    def key(self):
        return "opt.zeroing_bram_write_enable"

    @property
    def passes_after_self(self):
        return ("completion.switch", "physical", "config", "rtl", "vpr", "asicflow")

    def run(self, context):
        hierarchy = analyze_hierarchy(context)
        stack = {context.top.name: context.top}
        visited = set()
        while stack:
            name, module = stack.popitem()
            visited.add(name)
            if module.module_class in (ModuleClass.cluster, ModuleClass.io_block, ModuleClass.logic_block):
                for instance in itervalues(module.instances):
                    if instance.module_class.is_primitive and instance.model.primitive_class.is_memory:
                        for pin in itervalues(instance.pins):
                            if pin.in_user_domain and pin.model.port_class in (PrimitivePortClass.write_en,
                                    PrimitivePortClass.write_en1, PrimitivePortClass.write_en2):
                                for bit in pin:
                                    sources = tuple(iter(bit.user_sources))
                                    bit.remove_user_sources()
                                    bit.add_user_sources((ZERO, ) + sources)
            for subname, submod in iteritems(hierarchy[name]):
                if subname in stack or subname in visited:
                    continue
                elif submod.module_class not in (ModuleClass.array, ModuleClass.tile, ModuleClass.io_block,
                        ModuleClass.logic_block, ModuleClass.cluster):
                    continue
                stack[subname] = submod
