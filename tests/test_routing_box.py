# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Global, Orientation, Dimension
from prga.arch.primitive.builtin import Iopad
from prga.arch.block.block import IOBlock
from prga.arch.routing.common import SegmentPrototype
from prga.arch.routing.box import ConnectionBox, SwitchBox
from prga.arch.switch.switch import ConfigurableMUX
from prga.algorithm.design.routing import (BlockPortFCValue, BlockFCValue, populate_connection_box, generate_fc,
        SwitchBoxEnvironment, populate_switch_box, WiltonSwitchBoxPattern, generate_wilton)
from prga.algorithm.design.switch import SwitchLibraryDelegate, switchify
from prga.rtlgen.rtlgen import VerilogGenerator

class SwitchLibrary(SwitchLibraryDelegate):
    def __init__(self):
        self.switches = {}

    def get_switch(self, width, module):
        return self.switches.setdefault(width, ConfigurableMUX(width))

def test_connection_box(tmpdir):
    io = Iopad()
    block = IOBlock('mock_block', 4, io)
    glb = Global('clk', is_clock = True)
    sgmts = [SegmentPrototype('L1', 4, 1), SegmentPrototype('L2', 1, 2)]
    lib = SwitchLibrary()
    gen = VerilogGenerator()

    # 1. add some ports
    block.create_global(glb)
    block.create_input('outpad', 1)
    block.create_output('inpad', 1)

    # 2. create a connection box
    cbox = ConnectionBox('mock_cbox', Dimension.x)

    # 3. populate and generate connections
    populate_connection_box(cbox, sgmts, block, Orientation.south)
    generate_fc(cbox, sgmts, block, Orientation.south, BlockFCValue(BlockPortFCValue(0.5), BlockPortFCValue(1.0)))

    # 2.3 switchify!
    switchify(lib, cbox)

    # 4. generate files
    gen.generate_module(tmpdir.join(cbox.name + '.v').open(OpenMode.w), cbox)

def test_switch_box(tmpdir):
    sgmts = [SegmentPrototype('L1', 4, 1), SegmentPrototype('L2', 1, 2)]
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
