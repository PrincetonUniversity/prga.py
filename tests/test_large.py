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
from prga.config.bitchain.flow import BitchainConfigCircuitryDelegate, InjectBitchainConfigCircuitry

from itertools import product

def test_large(): # tmpdir):
    width, height = 52, 42
    context = ArchitectureContext('top', width, height, BitchainConfigCircuitryDelegate)

    # 1. routing stuff
    clk = context.create_global('clk', is_clock = True, bind_to_position = (0, 1))
    context.create_segment('L1', 48, 1)
    context.create_segment('L2', 16, 2)
    context.create_segment('L4', 8, 4)

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
                'iotile_{}'.format(orientation.name), iob, 8, orientation)

    # 5. create CLB
    clb = context.create_logic_block('clb')
    while True:
        clkport = clb.create_global(clk, Orientation.south)
        for i, ori_in in enumerate(Orientation):
            if ori_in.is_auto:
                continue
            ori_out = ori_in.case(Orientation.east, Orientation.south, Orientation.west, Orientation.north)
            inport = clb.create_input('in_' + ori_in.name[0], 6, ori_in)
            outport = clb.create_output('out_' + ori_out.name[0], 2, ori_out)
            inst = clb.instantiate(context.primitives['fraclut6ff'], 'cluster_' + ori_in.name[0])
            clb.connect(clkport, inst.pins['clk'])
            clb.connect(inport, inst.pins['in'])
            clb.connect(inst.pins['o6'], outport[0])
            clb.connect(inst.pins['o5'], outport[1])
        break

    # 6. create tile
    clbtile = context.create_tile('clb_tile', clb)

    # 7. create BRAM
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

    # 8. create tile
    bramtile = context.create_tile('bram_tile', bram)

    # 9. create sub-array
    subarray = context.create_array('subarray', 5, 4)
    for x, y in product(range(5), range(4)):
        if x == 2:
            if y % 2 == 0:
                subarray.instantiate_element(bramtile, (x, y))
        else:
            subarray.instantiate_element(clbtile, (x, y))

    # 9. fill top-level array
    for x in range(width):
        for y in range(height):
            if x == 0:
                if y > 0 and y < height - 1:
                    context.top.instantiate_element(iotiles[Orientation.west], (x, y))
            elif x == width - 1:
                if y > 0 and y < height - 1:
                    context.top.instantiate_element(iotiles[Orientation.east], (x, y))
            elif y == 0:
                context.top.instantiate_element(iotiles[Orientation.south], (x, y))
            elif y == height - 1:
                context.top.instantiate_element(iotiles[Orientation.north], (x, y))
            elif x % 5 == 1 and y % 4 == 1:
                context.top.instantiate_element(subarray, (x, y))

    # 10. flow
    flow = Flow((
        CompleteRoutingBox(BlockFCValue(BlockPortFCValue(0.25), BlockPortFCValue(0.1))),
        CompleteSwitch(),
        CompleteConnection(),
        GenerateVerilog('rtl'),
        InjectBitchainConfigCircuitry(),
        GenerateVPRXML('vpr'),
        CompletePhysical(),
        ZeroingBRAMWriteEnable(),
            ))

    # 11. run flow
    flow.run(context)

    # 12. create a pickled version
    context.pickle('ctx.pickled')
