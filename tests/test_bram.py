# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Orientation
from prga.arch.array.common import ChannelCoverage
from prga.algorithm.design.cbox import BlockPortFCValue, BlockFCValue
from prga.flow.context import ArchitectureContext
from prga.flow.flow import Flow
from prga.flow.design import CompleteRoutingBox, CompleteSwitch, CompleteConnection, CompletePhysical
from prga.flow.rtlgen import GenerateVerilog
from prga.flow.vprgen import GenerateVPRXML
from prga.flow.opt import ZeroingBRAMWriteEnable
from prga.flow.ysgen import GenerateYosysResources
from prga.config.bitchain.flow import BitchainConfigCircuitryDelegate, InjectBitchainConfigCircuitry

def test_bram(tmpdir):
    context = ArchitectureContext('top', 8, 8, BitchainConfigCircuitryDelegate)

    # 1. routing stuff
    clk = context.create_global('clk', is_clock = True, bind_to_position = (0, 1))
    context.create_segment('L1', 12, 1)
    context.create_segment('L2', 4, 2)

    # 2. create IOB
    iob = context.create_io_block('iob')
    while True:
        clkport = iob.create_global(clk)
        outpad = iob.create_input('outpad', 1)
        inpad = iob.create_output('inpad', 1)
        ioinst = iob.instances['io']
        iff = iob.instantiate(context.primitives['flipflop'], 'iff')
        off = iob.instantiate(context.primitives['flipflop'], 'off')
        iob.connect(clkport, iff.pins['clk'])
        iob.connect(ioinst.pins['inpad'], iff.pins['D'])
        iob.connect(iff.pins['Q'], inpad)
        iob.connect(ioinst.pins['inpad'], inpad)
        iob.connect(clkport, off.pins['clk'])
        iob.connect(off.pins['Q'], ioinst.pins['outpad'])
        iob.connect(outpad, ioinst.pins['outpad'])
        iob.connect(outpad, off.pins['D'])
        break

    # 3. create tile
    iotiles = {}
    for orientation in iter(Orientation):
        if orientation.is_auto:
            continue
        iotiles[orientation] = context.create_tile(
                'io_tile_{}'.format(orientation.name), iob, 4, orientation)

    # 5. create CLB
    clb = context.create_logic_block('clb')
    while True:
        clkport = clb.create_global(clk, Orientation.south)
        ceport = clb.create_input('ce', 1, Orientation.south)
        srport = clb.create_input('sr', 1, Orientation.south)
        cin = clb.create_input('cin', 1, Orientation.north)
        for i in range(2):
            inst = clb.instantiate(context.primitives['fraclut6sffc'], 'cluster{}'.format(i))
            clb.connect(clkport, inst.pins['clk'])
            clb.connect(ceport, inst.pins['ce'])
            clb.connect(srport, inst.pins['sr'])
            clb.connect(clb.create_input('ia' + str(i), 6, Orientation.west), inst.pins['ia'])
            clb.connect(clb.create_input('ib' + str(i), 1, Orientation.west), inst.pins['ib'])
            clb.connect(cin, inst.pins['cin'], pack_pattern = 'carrychain')
            cin = inst.pins['cout']
            clb.connect(inst.pins['oa'], clb.create_output('oa' + str(i), 1, Orientation.east))
            clb.connect(inst.pins['ob'], clb.create_output('ob' + str(i), 1, Orientation.east))
            clb.connect(inst.pins['q'], clb.create_output('q' + str(i), 1, Orientation.east))
        clb.connect(cin, clb.create_output('cout', 1, Orientation.south), pack_pattern = 'carrychain')
        break

    # 6. create direct inter-block tunnels
    context.create_direct_tunnel('carrychain', clb.ports['cout'], clb.ports['cin'], (0, 1))

    # 7. create tile
    clbtile = context.create_tile('clb_tile', clb)

    # 8. create BRAM
    bram = context.create_logic_block('bram', 1, 2)
    while True:
        clkport = bram.create_global(clk, Orientation.south, position = (0, 0))
        addrport1 = bram.create_input('addr1', 10, Orientation.west, position = (0, 0))
        dinport1 = bram.create_input('data1', 8, Orientation.west, position = (0, 0))
        weport1 = bram.create_input('we1', 1, Orientation.west, position = (0, 0))
        doutport1 = bram.create_output('out1', 8, Orientation.east, position = (0, 0))
        addrport2 = bram.create_input('addr2', 10, Orientation.west, position = (0, 1))
        dinport2 = bram.create_input('data2', 8, Orientation.west, position = (0, 1))
        weport2 = bram.create_input('we2', 1, Orientation.west, position = (0, 1))
        doutport2 = bram.create_output('out2', 8, Orientation.east, position = (0, 1))
        inst = bram.instantiate(context.primitive_library.get_or_create_memory(10, 8, 
            dualport = True), 'ram')
        bram.connect(clkport, inst.pins['clk'])
        bram.connect(addrport1, inst.pins['addr1'])
        bram.connect(dinport1, inst.pins['data1'])
        bram.connect(weport1, inst.pins['we1'])
        bram.connect(inst.pins['out1'], doutport1)
        bram.connect(addrport2, inst.pins['addr2'])
        bram.connect(dinport2, inst.pins['data2'])
        bram.connect(weport2, inst.pins['we2'])
        bram.connect(inst.pins['out2'], doutport2)
        break

    # 9. create tile
    bramtile = context.create_tile('bram_tile', bram)

    # 10. fill top-level array
    for x in range(8):
        for y in range(8):
            if x == 0:
                if y > 0 and y < 7:
                    context.top.instantiate_element(iotiles[Orientation.west], (x, y))
            elif x == 7:
                if y > 0 and y < 7:
                    context.top.instantiate_element(iotiles[Orientation.east], (x, y))
            elif y == 0:
                context.top.instantiate_element(iotiles[Orientation.south], (x, y))
            elif y == 7:
                context.top.instantiate_element(iotiles[Orientation.north], (x, y))
            elif x in (2, 5):
                if y % 2 == 1:
                    context.top.instantiate_element(bramtile, (x, y))
            else:
                context.top.instantiate_element(clbtile, (x, y))

    # 11. flow
    flow = Flow((
        CompleteRoutingBox(BlockFCValue(BlockPortFCValue(0.25), BlockPortFCValue(0.5)),
            {'clb': BlockFCValue(BlockPortFCValue(0.25), BlockPortFCValue(0.25),
                {'cin': BlockPortFCValue(0), 'cout': BlockPortFCValue(0)})}),
        CompleteSwitch(),
        CompleteConnection(),
        GenerateVerilog('rtl'),
        InjectBitchainConfigCircuitry(),
        GenerateVPRXML('vpr'),
        CompletePhysical(),
        ZeroingBRAMWriteEnable(),
        GenerateYosysResources('syn'),
            ))

    # 11. run flow
    oldcwd = tmpdir.chdir()
    flow.run(context)

    # 12. create a pickled version
    context.pickle('ctx.pickled')
