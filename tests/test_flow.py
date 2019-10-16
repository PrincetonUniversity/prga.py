# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Orientation
from prga.arch.array.common import ChannelCoverage
from prga.algorithm.design.cbox import BlockPortFCValue, BlockFCValue
from prga.flow.context import BaseArchitectureContext
from prga.flow.flow import Flow
from prga.flow.design import CompleteRoutingBox, CompleteSwitch, CompleteConnection
from prga.flow.rtlgen import GenerateVerilog
from prga.flow.vprgen import GenerateVPRXML
from prga.config.bitchain.flow import BitchainConfigCircuitryDelegate, InjectBitchainConfigCircuitry

def test_flow(tmpdir):
    context = BaseArchitectureContext('mock_array', 8, 8, BitchainConfigCircuitryDelegate)

    # 1. routing stuff
    clk = context.create_global('clk', is_clock = True, bind_to_position = (0, 1))
    context.create_segment('L1', 4, 1)
    context.create_segment('L2', 1, 2)

    # 2. create IOB
    iob = context.create_io_block('mock_iob')
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
                'mock_iotile_{}'.format(orientation.name), iob, 4, orientation)

    # 4. create cluster
    cluster = context.create_cluster('mock_cluster')
    while True:
        clkport = cluster.create_clock('clk')
        inport = cluster.create_input('in', 4)
        outport = cluster.create_output('out', 1)
        ff = cluster.instantiate(context.primitives['flipflop'], 'ff')
        lut = cluster.instantiate(context.primitives['lut4'], 'lut')
        cluster.connect(clkport, ff.pins['clk'])
        cluster.connect(inport, lut.pins['in'])
        cluster.connect(lut.pins['out'], ff.pins['D'])
        cluster.connect(lut.pins['out'], outport)
        cluster.connect(ff.pins['Q'], outport)
        break

    # 5. create CLB
    clb = context.create_logic_block('mock_clb')
    while True:
        clkport = clb.create_global(clk, Orientation.south)
        inport = clb.create_input('in', 8, Orientation.west)
        outport = clb.create_output('out', 2, Orientation.east)
        for i in range(2):
            inst = clb.instantiate(cluster, 'cluster{}'.format(i))
            clb.connect(clkport, inst.pins['clk'])
            clb.connect(inport[i*4: (i+1)*4], inst.pins['in'])
            clb.connect(inst.pins['out'], outport[i])
        break

    # 6. create tile
    clbtile = context.create_tile('mock_clb_tile', clb)

    # 7. fill top-level array
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
            else:
                context.top.instantiate_element(clbtile, (x, y))

    # 8. create a pickled version
    context.pickle(tmpdir.join('ctx.pickled').open(OpenMode.w))

    # 9. flow
    flow = Flow((
        CompleteRoutingBox(BlockFCValue(BlockPortFCValue(0.25), BlockPortFCValue(0.1))),
        CompleteSwitch(),
        CompleteConnection(),
        GenerateVerilog(),
        InjectBitchainConfigCircuitry(),
        GenerateVPRXML(),
            ))

    # 10. run flow
    oldcwd = tmpdir.chdir()
    flow.run(context)
