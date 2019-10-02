# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Global, Orientation, Dimension
from prga.arch.primitive.builtin import Flipflop, LUT
from prga.arch.module.common import ModuleClass
from prga.arch.block.cluster import Cluster
from prga.arch.block.block import LogicBlock
from prga.arch.routing.common import SegmentPrototype
from prga.arch.switch.switch import ConfigurableMUX
from prga.arch.routing.box import ConnectionBox, SwitchBox
from prga.arch.array.common import ChannelCoverage
from prga.arch.array.tile import Tile
from prga.arch.array.array import Array
from prga.algorithm.design.cbox import BlockPortFCValue, BlockFCValue, populate_connection_box, generate_fc
from prga.algorithm.design.sbox import SwitchBoxEnvironment, populate_switch_box, generate_wilton
from prga.algorithm.design.tile import ConnectionBoxLibraryDelegate, cboxify, netify_tile
from prga.algorithm.design.array import SwitchBoxLibraryDelegate, sboxify, netify_array
from prga.algorithm.design.switch import SwitchLibraryDelegate, switchify
from prga.rtlgen.rtlgen import VerilogGenerator
from prga.config.bitchain.design.primitive import (CONFIG_BITCHAIN_SEARCH_PATH, ConfigBitchain, FracturableLUT6,
        SynchronousSRFlipflop, carrychain)
from prga.config.bitchain.algorithm.injection import ConfigBitchainLibraryDelegate, inject_config_chain

class Library(SwitchLibraryDelegate, ConnectionBoxLibraryDelegate, ConfigBitchainLibraryDelegate):
    def __init__(self):
        self.modules = {}

    def get_switch(self, width, module):
        return self.modules.setdefault((ModuleClass.switch, width), ConfigurableMUX(width))

    def get_cbox(self, block, orientation, position = None, channel = (0, 0)):
        orientation, position = block._validate_orientation_and_position(orientation, position)
        name = 'cbox_{}_x{}y{}{}'.format(block.name, position.x, position.y, orientation.name[0])
        return self.modules.setdefault(name, ConnectionBox(name, orientation.dimension.perpendicular))

    def get_sbox(self, env = SwitchBoxEnvironment(), drive_truncated = True):
        return self.modules.setdefault('sbox', SwitchBox('sbox'))

    def get_cbox_double_sided(self, dimension,
            block_ne = None, position_ne = None, block_sw = None, position_sw = None):
        raise NotImplementedError

    def get_bitchain(self, width):
        return self.modules.setdefault((ModuleClass.config, width), ConfigBitchain(width))

    def add_module(self, module):
        self.modules[module.name] = module
        return module

def test_bitchain(tmpdir):
    clk = Global('clk', is_clock = True)
    rst = Global('rst')
    sgmts = [SegmentPrototype('L1', 64, 1)]
    lib = Library()
    gen = VerilogGenerator( (CONFIG_BITCHAIN_SEARCH_PATH, ) )

    # 1. cluster
    cluster = lib.add_module(Cluster('cluster'))
    cluster.create_clock('clk')
    cluster.create_input('rst', 1)
    cluster.create_input('ce', 1)
    cluster.create_input('AI', 6)
    cluster.create_input('DI', 1)
    cluster.create_input('CI', 1)
    cluster.create_output('DO', 1)
    cluster.create_output('DQ', 1)
    cluster.create_output('DMUX', 1)
    cluster.create_output('CO', 1)
    lut = cluster.instantiate(lib.add_module(FracturableLUT6()), 'lut')
    ffa = cluster.instantiate(lib.add_module(SynchronousSRFlipflop()), 'ffa')
    ffb = cluster.instantiate(ffa.model, 'ffb')
    cy = cluster.instantiate(lib.add_module(carrychain), 'cy')
    cluster.connect(cluster.ports['AI'], lut.pins['in'])
    cluster.connect(cluster.ports['DI'], cy.pins['g'])
    cluster.connect(lut.pins['o6'], cy.pins['p'])
    cluster.connect(lut.pins['o5'], cy.pins['g'])
    cluster.connect(cluster.ports['CI'], cy.pins['ci'])
    cluster.connect(cluster.ports['clk'], ffa.pins['clk'])
    cluster.connect(cluster.ports['rst'], ffa.pins['rst'])
    cluster.connect(cluster.ports['ce'], ffa.pins['ce'])
    cluster.connect(cluster.ports['DI'], ffa.pins['d'])
    cluster.connect(lut.pins['o5'], ffa.pins['d'])
    cluster.connect(cluster.ports['clk'], ffb.pins['clk'])
    cluster.connect(cluster.ports['rst'], ffb.pins['rst'])
    cluster.connect(cluster.ports['ce'], ffb.pins['ce'])
    cluster.connect(cy.pins['co'], ffb.pins['d'])
    cluster.connect(cy.pins['s'], ffb.pins['d'])
    cluster.connect(lut.pins['o6'], ffb.pins['d'])
    cluster.connect(lut.pins['o5'], ffb.pins['d'])
    cluster.connect(cluster.ports['DI'], ffb.pins['d'])
    cluster.connect(ffa.pins['q'], cluster.ports['DMUX'])
    cluster.connect(cy.pins['co'], cluster.ports['DMUX'])
    cluster.connect(cy.pins['s'], cluster.ports['DMUX'])
    cluster.connect(lut.pins['o6'], cluster.ports['DMUX'])
    cluster.connect(lut.pins['o5'], cluster.ports['DMUX'])
    cluster.connect(lut.pins['o6'], cluster.ports['DO'])
    cluster.connect(ffb.pins['q'], cluster.ports['DQ'])
    cluster.connect(cy.pins['co'], cluster.ports['CO'])
    switchify(lib, cluster)

    # 2. logic block
    block = lib.add_module(LogicBlock('clb'))
    clkport = block.create_global(clk, Orientation.south)
    rstport = block.create_global(rst, Orientation.south)
    ceport = block.create_input('ce', 1, Orientation.south)
    ci = block.create_input('CI', 1, Orientation.south)
    co = block.create_output('CO', 1, Orientation.north)
    for i in range(4):
        ai = block.create_input('AI' + str(i), 6, Orientation.west)
        di = block.create_input('DI' + str(i), 1, Orientation.south)
        do = block.create_output('DO' + str(i), 1, Orientation.east)
        dq = block.create_output('DQ' + str(i), 1, Orientation.east)
        dmux = block.create_output('DMUX' + str(i), 1, Orientation.north)
        inst = block.instantiate(cluster, 'cluster' + str(i))
        block.connect(clkport, inst.pins['clk'])
        block.connect(rstport, inst.pins['rst'])
        block.connect(ceport, inst.pins['ce'])
        block.connect(ai, inst.pins['AI'])
        block.connect(di, inst.pins['DI'])
        block.connect(ci, inst.pins['CI'])
        ci = inst.pins['CO']
        block.connect(inst.pins['DO'], do)
        block.connect(inst.pins['DQ'], dq)
        block.connect(inst.pins['DMUX'], dmux)
    block.connect(ci, co)
    switchify(lib, block)

    # 3. tile
    tile = lib.add_module(Tile('tile', block))
    cboxify(lib, tile)
    for (position, orientation), cbox_inst in iteritems(tile.cbox_instances):
        # populate_connection_box(cbox_inst.model, sgmts, tile.block, orientation, position,
        #         orientation.case((0, 0), (0, 0), (0, -1), (-1, 0)))
        generate_fc(cbox_inst.model, sgmts, tile.block, orientation,
                BlockFCValue(BlockPortFCValue(0.25), BlockPortFCValue(0.5)), position,
                orientation.case((0, 0), (0, 0), (0, -1), (-1, 0)))
        switchify(lib, cbox_inst.model)
    netify_tile(tile)

    # 4. array
    array = lib.add_module(Array('macrotile', 1, 1, ChannelCoverage(north = True, east = True)))
    array.instantiate_element(tile, (0, 0))
    sboxify(lib, array)
    for sbox_inst in itervalues(array.sbox_instances):
        populate_switch_box(sbox_inst.model, sgmts)
        generate_wilton(sbox_inst.model, sgmts, cycle_free = True)
    netify_array(array)
    for sbox_inst in itervalues(array.sbox_instances):
        switchify(lib, sbox_inst.model)

    # 5. inject config circuitry
    inject_config_chain(lib, array)

    # 6. generate files
    for module in itervalues(lib.modules):
        gen.generate_module(tmpdir.join(module.name + '.v').open(OpenMode.w), module)
