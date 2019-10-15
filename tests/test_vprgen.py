# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Global, Orientation, Dimension
from prga.arch.primitive.builtin import LUT, Flipflop
from prga.arch.multimode.multimode import Multimode
from prga.arch.block.cluster import Cluster
from prga.arch.block.block import LogicBlock
from prga.arch.array.tile import Tile
from prga.flow.delegate import ConfigCircuitryDelegate
from prga.vprgen.arch import vpr_arch_block
from prga.xml import XMLGenerator

def test_vprgen(tmpdir):
    lut5 = LUT(5)
    lut6 = LUT(6)
    ff = Flipflop()
    clk = Global('clk', is_clock = True)
    delegate = ConfigCircuitryDelegate(None)

    mm = Multimode('fle', 'fake_template')
    mm.create_clock('clk')
    mm.create_input('in', 6)
    mm.create_output('o6', 1)
    mm.create_output('o5', 1)

    mode = mm.create_mode('lut6x1')
    lutinst = mode.instantiate(lut6, 'lut')
    ffinst = mode.instantiate(ff, 'ff')
    mode.connect(mode.ports['clk'], ffinst.pins['clk'])
    mode.connect(mode.ports['in'], lutinst.pins['in'])
    mode.connect(lutinst.pins['out'], ffinst.pins['D'])
    mode.connect(lutinst.pins['out'], mode.ports['o6'])
    mode.connect(ffinst.pins['Q'], mode.ports['o6'])

    mode = mm.create_mode('lut5x2')
    lutinst = [mode.instantiate(lut5, 'lut{}'.format(i)) for i in range(2)]
    ffinst = mode.instantiate(ff, 'ff')
    mode.connect(mode.ports['clk'], ffinst.pins['clk'])
    mode.connect(mode.ports['in'][0:5], lutinst[0].pins['in'])
    mode.connect(mode.ports['in'][0:5], lutinst[1].pins['in'])
    mode.connect(lutinst[0].pins['out'], ffinst.pins['D'])
    mode.connect(lutinst[0].pins['out'], mode.ports['o6'])
    mode.connect(ffinst.pins['Q'], mode.ports['o6'])
    mode.connect(lutinst[1].pins['out'], mode.ports['o5'])

    block = LogicBlock('clb')
    clkport = block.create_global(clk, Orientation.south)
    inport = block.create_input('I', 12, Orientation.west)
    outport = block.create_output('O', 4, Orientation.east)
    for i in range(2):
        inst = block.instantiate(mm, 'fle' + str(i))
        block.connect(clkport, inst.pins['clk'])
        block.connect(inport[6 * i: 6 * (i + 1)], inst.pins['in'])
        block.connect(inst.pins['o6'], outport[2 * i])
        block.connect(inst.pins['o5'], outport[2 * i + 1])

    tile = Tile('clb_tile', block)

    with XMLGenerator(tmpdir.join('block.xml').open(OpenMode.w), True) as xmlgen:
        vpr_arch_block(xmlgen, tile)
