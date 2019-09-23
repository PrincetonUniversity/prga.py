# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Global
from prga.arch.primitive.builtin import Flipflop, Iopad
from prga.arch.block.block import IOBlock

def test_cluster(tmpdir):
    io = Iopad()
    ff = Flipflop()
    block = IOBlock('mock_block', 4, io)
    glb = Global('clk', is_clock = True)

    # 1. add some ports
    block.create_global(glb)
    block.create_input('outpad', 1)
    block.create_output('inpad', 1)

    # 2. add some instances
    iff = block.instantiate(ff, 'iff')
    off = block.instantiate(ff, 'off')

    # 3. connect stuff
    block.connect(block.ports['clk'], iff.pins['clk'])
    block.connect(block.ports['clk'], off.pins['clk'])

    block.connect(block.ports['outpad'], off.pins['D'])
    block.connect(block.ports['outpad'], block.instances['io'].pins['outpad'])
    block.connect(off.pins['Q'], block.instances['io'].pins['outpad'])

    block.connect(block.instances['io'].pins['inpad'], iff.pins['D'])
    block.connect(block.instances['io'].pins['inpad'], block.ports['inpad'])
    block.connect(iff.pins['Q'], block.ports['inpad'])
