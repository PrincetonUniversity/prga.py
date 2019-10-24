# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.routing.common import Segment
from prga.arch.routing.box import SwitchBox
from prga.arch.switch.switch import ConfigurableMUX
from prga.algorithm.design.sbox import (SwitchBoxEnvironment, populate_switch_box,
        WiltonSwitchBoxPattern, generate_wilton)
from prga.algorithm.design.switch import SwitchLibraryDelegate, switchify
from prga.rtlgen.rtlgen import VerilogGenerator

class SwitchLibrary(SwitchLibraryDelegate):
    def __init__(self):
        self.switches = {}

    def get_or_create_switch(self, width, module, in_physical_domain = True):
        return self.switches.setdefault(width, ConfigurableMUX(width))

    @property
    def is_empty(self):
        return False

def test_switch_box(tmpdir):
    sgmts = [Segment('L1', 4, 1), Segment('L2', 1, 2)]
    lib = SwitchLibrary()
    gen = VerilogGenerator()

    # 1. create a switch box
    sbox = SwitchBox('mock_sbox')

    # 2. populate and generate connections
    populate_switch_box(sbox, sgmts)
    generate_wilton(sbox, sgmts, cycle_free = True)

    # 2.3 switchify!
    switchify(lib, sbox)

    # 4. generate files
    gen.generate_module(tmpdir.join(sbox.name + '.v').open(OpenMode.w), sbox)
