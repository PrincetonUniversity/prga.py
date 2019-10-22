# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Orientation
from prga.arch.array.common import ChannelCoverage
from prga.algorithm.design.cbox import BlockPortFCValue, BlockFCValue
from prga.flow.context import ArchitectureContext
from prga.flow.flow import Flow
from prga.flow.design import CompleteRoutingBox, CompleteSwitch, CompleteConnection
from prga.flow.rtlgen import GenerateVerilog
from prga.flow.vprgen import GenerateVPRXML
from prga.config.bitchain.flow import BitchainConfigCircuitryDelegate, InjectBitchainConfigCircuitry

from itertools import product

def test_large(tmpdir):
    context = ArchitectureContext('top', 18, 18, BitchainConfigCircuitryDelegate)

    # 1. routing stuff
    clk = context.create_global('clk', is_clock = True, bind_to_position = (0, 1))
    context.create_segment('L1', 32, 1)
    context.create_segment('L2', 16, 2)

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

    # 4. create cluster
    cluster = context.create_cluster('cluster')
    while True:
        clkport = cluster.create_clock('clk')
        inport = cluster.create_input('in', 6)
        outport = cluster.create_output('out', 2)
        ff0 = cluster.instantiate(context.primitives['flipflop'], 'ff0')
        ff1 = cluster.instantiate(context.primitives['flipflop'], 'ff1')
        lut = cluster.instantiate(context.primitives['fraclut6'], 'lut')
        cluster.connect(clkport, ff0.pins['clk'])
        cluster.connect(clkport, ff1.pins['clk'])
        cluster.connect(inport, lut.pins['in'])
        cluster.connect(lut.pins['o6'], ff0.pins['D'])
        cluster.connect(lut.pins['o5'], ff1.pins['D'])
        cluster.connect(lut.pins['o6'], outport[0])
        cluster.connect(lut.pins['o5'], outport[1])
        cluster.connect(ff0.pins['Q'], outport[0])
        cluster.connect(ff1.pins['Q'], outport[1])
        break

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
            inst = clb.instantiate(cluster, 'cluster_' + ori_in.name[0])
            clb.connect(clkport, inst.pins['clk'])
            clb.connect(inport[i*6: (i+1)*6], inst.pins['in'])
            clb.connect(inst.pins['out'], outport)
        break

    # 6. create tile
    clbtile = context.create_tile('clb_tile', clb)

    # 7. create BRAM
    bram = context.create_logic_block('bram', 1, 2)
    while True:
        clkport = bram.create_global(clk, Orientation.south, position = (0, 0))
        addrport = bram.create_input('addr', 10, Orientation.west, position = (0, 0))
        dinport = bram.create_input('data', 8, Orientation.west, position = (0, 1))
        weport = bram.create_input('we', 1, Orientation.north, position = (0, 1))
        doutport = bram.create_output('out', 8, Orientation.east, position = (0, 0))
        inst = bram.instantiate(context.primitive_library.get_or_create_memory(10, 8), 'ram')
        bram.connect(clkport, inst.pins['clk'])
        bram.connect(addrport, inst.pins['addr'])
        bram.connect(dinport, inst.pins['data'])
        bram.connect(weport, inst.pins['we'])
        bram.connect(inst.pins['out'], doutport)
        break

    # 8. create tile
    bramtile = context.create_tile('bram_tile', bram)

    # 9. create sub-array
    subarray = context.create_array('subarray', 4, 4)
    for x, y in product(range(4), range(4)):
        if x == 2:
            if y % 2 == 0:
                subarray.instantiate_element(bramtile, (x, y))
        else:
            subarray.instantiate_element(clbtile, (x, y))

    # 9. fill top-level array
    for x in range(18):
        for y in range(18):
            if x == 0:
                if y > 0 and y < 17:
                    context.top.instantiate_element(iotiles[Orientation.west], (x, y))
            elif x == 17:
                if y > 0 and y < 17:
                    context.top.instantiate_element(iotiles[Orientation.east], (x, y))
            elif y == 0:
                context.top.instantiate_element(iotiles[Orientation.south], (x, y))
            elif y == 17:
                context.top.instantiate_element(iotiles[Orientation.north], (x, y))
            elif x % 4 == 1 and y % 4 == 1:
                context.top.instantiate_element(subarray, (x, y))

    # 10. flow
    flow = Flow((
        CompleteRoutingBox(BlockFCValue(BlockPortFCValue(0.25), BlockPortFCValue(0.1))),
        CompleteSwitch(),
        CompleteConnection(),
        GenerateVerilog('rtl'),
        InjectBitchainConfigCircuitry(),
        GenerateVPRXML('vpr'),
            ))

    # 11. run flow
    oldcwd = tmpdir.chdir()
    flow.run(context)

    # 12. create a pickled version
    context.pickle(tmpdir.join('ctx.pickled').open(OpenMode.w))

