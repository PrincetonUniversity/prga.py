# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.vprgen.arch import vpr_arch_xml
from prga.vprgen.rrg import vpr_rrg_xml
from prga.flow.flow import AbstractPass
from prga.util import Object
from prga.xml import XMLGenerator

import os

__all__ = ['GenerateVPRXML']

# ----------------------------------------------------------------------------
# -- Generate VPR Input Files ------------------------------------------------
# ----------------------------------------------------------------------------
class GenerateVPRXML(Object, AbstractPass):
    """Generate XML input files for VPR."""

    __slots__ = ['prefix']
    def __init__(self, prefix = ''):
        self.prefix = prefix

    @property
    def key(self):
        return "vpr.xml"

    def run(self, context):
        makedirs(self.prefix)
        arch = os.path.join(self.prefix, 'arch.xml')
        with XMLGenerator(open(arch, OpenMode.wb), True) as xml:
            vpr_arch_xml(xml, context.config_circuitry_delegate, context)
        rrg = os.path.join(self.prefix, 'rrg.xml')
        with XMLGenerator(open(rrg, OpenMode.wb), True) as xml:
            vpr_rrg_xml(xml, context.config_circuitry_delegate, context)
