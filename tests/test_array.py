# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Global, Orientation, Dimension
from prga.arch.primitive.builtin import Iopad, Memory
from prga.arch.block.block import IOBlock, LogicBlock
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

from itertools import chain

class Library(SwitchLibraryDelegate, ConnectionBoxLibraryDelegate):
    def __init__(self):
        self.switches = {}
        self.cboxes = {}
        self.sboxes = {}

    def get_switch(self, width, module):
        return self.switches.setdefault(width, ConfigurableMUX(width))

    def get_cbox(self, block, orientation, position = None, channel = (0, 0)):
        orientation, position = block._validate_orientation_and_position(orientation, position)
        name = 'mock_cbox_{}_x{}y{}{}'.format(block.name, position.x, position.y, orientation.name[0])
        return self.cboxes.setdefault(name, ConnectionBox(name, orientation.dimension.perpendicular))

    def get_sbox(self, env = SwitchBoxEnvironment(), drive_truncated = True):
        name = 'mock_sbox_{}'.format(''.join(map(lambda d: d.name[0],
            filter(lambda d: not d.is_auto and env[d], Orientation))))
        return self.sboxes.setdefault(env, SwitchBox(name))

    def get_cbox_double_sided(self, dimension,
            block_ne = None, position_ne = None, block_sw = None, position_sw = None):
        raise NotImplementedError

def test_io_leaf_array(tmpdir):
    io = Iopad()
    block = IOBlock('mock_block', 4, io)
    glb = Global('clk', is_clock = True)
    sgmts = [SegmentPrototype('L1', 4, 1)]
    lib = Library()
    gen = VerilogGenerator()

    # 1. add some ports
    block.create_global(glb)
    block.create_input('outpad', 1)
    block.create_output('inpad', 1)

    # 2. create tile
    tile = Tile('mock_tile', block)

    # 3. cboxify
    cboxify(lib, tile, Orientation.east)

    # 4. populate and generate connections
    for (position, orientation), cbox_inst in iteritems(tile.cbox_instances):
        populate_connection_box(cbox_inst.model, sgmts, tile.block, orientation, position)
        generate_fc(cbox_inst.model, sgmts, tile.block, orientation,
                BlockFCValue(BlockPortFCValue(0.5), BlockPortFCValue(1.0)), position)

    # 5. netify
    netify_tile(tile)

    # 6. create array
    array = Array('mock_array', tile.width, tile.height, ChannelCoverage(north = True, east = True))

    # 7. place tile
    array.instantiate_element(tile, (0, 0))

    # 8. sboxify
    sboxify(lib, array)

    # 9. populate and generate connections
    for env, sbox in iteritems(lib.sboxes):
        populate_switch_box(sbox, sgmts, env)
        generate_wilton(sbox, sgmts, cycle_free = True)

    # 10. netify
    netify_array(array)

    # 11. switchify!
    for box in chain(itervalues(lib.cboxes), itervalues(lib.sboxes)):
        switchify(lib, box)

    # 12. generate files
    for module in chain(itervalues(lib.switches), itervalues(lib.sboxes), iter((array, ))):
        gen.generate_module(tmpdir.join(module.name + '.v').open(OpenMode.w), module)

def test_complex_array(tmpdir):
    io = Iopad()
    clk = Global('clk', is_clock = True)
    sgmts = [SegmentPrototype('L1', 4, 1), SegmentPrototype('L2', 1, 2)]
    lib = Library()
    gen = VerilogGenerator()

    # 1. create IOB
    iob = IOBlock('mock_iob', 4, io)
    iob.create_global(clk)
    iob.create_input('outpad', 1)
    iob.create_output('inpad', 1)

    # 2. create IOB tiles
    iob_tiles = {}
    for ori in Orientation:
        if ori.is_auto:
            continue
        tile = iob_tiles[ori] = Tile('mock_tile_io' + ori.name[0], iob)
        cboxify(lib, tile, ori.opposite)
        for (position, orientation), cbox_inst in iteritems(tile.cbox_instances):
            generate_fc(cbox_inst.model, sgmts, tile.block, orientation,
                    BlockFCValue(BlockPortFCValue(0.5), BlockPortFCValue(1.0)), position,
                    orientation.case((0, 0), (0, 0), (0, -1), (-1, 0)))
        netify_tile(tile)

    # 3. create CLB
    clb = LogicBlock('mock_clb')
    clb.create_global(clk, Orientation.south)
    clb.create_input('ina', 4, Orientation.west)
    clb.create_output('outa', 2, Orientation.west)
    clb.create_input('inb', 4, Orientation.east)
    clb.create_output('outb', 2, Orientation.east)

    # 4. create CLB tiles
    clb_tile = Tile('mock_tile_clb', clb)
    cboxify(lib, clb_tile)
    for (position, orientation), cbox_inst in iteritems(clb_tile.cbox_instances):
        generate_fc(cbox_inst.model, sgmts, clb_tile.block, orientation,
                BlockFCValue(BlockPortFCValue(0.25), BlockPortFCValue(0.5)), position,
                orientation.case((0, 0), (0, 0), (0, -1), (-1, 0)))
    netify_tile(clb_tile)

    # 5. create BRAM
    bram = LogicBlock('mock_bram', 1, 3)
    bram.create_global(clk, Orientation.south, position = (0, 0))
    bram.create_input('we', 1, Orientation.south, (0, 0))
    bram.create_input('din', 1, Orientation.west, (0, 0))
    bram.create_output('dout', 1, Orientation.east, (0, 0))
    bram.create_input('addr_l', 4, Orientation.west, (0, 1))
    bram.create_input('addr_h', 4, Orientation.west, (0, 2))

    # 6. create BRAM tiles
    bram_tile = Tile('mock_tile_bram', bram)
    cboxify(lib, bram_tile)
    for (position, orientation), cbox_inst in iteritems(bram_tile.cbox_instances):
        generate_fc(cbox_inst.model, sgmts, bram_tile.block, orientation,
                BlockFCValue(BlockPortFCValue(0.25, {'din': 0.5, 'we': 0.5}),
                    BlockPortFCValue(0.5)), position,
                orientation.case((0, 0), (0, 0), (0, -1), (-1, 0)))
    netify_tile(bram_tile)

    # 7. repetitive sub-array
    subarray = Array('mock_sub_array', 3, 3, ChannelCoverage(north = True, east = True))
    subarray.instantiate_element(bram_tile, (2, 0))
    for x in range(2):
        for y in range(3):
            subarray.instantiate_element(clb_tile, (x, y))
    sboxify(lib, subarray)

    # 8. top array
    array = Array('mock_array', 8, 8)
    for i in range(1, 7):
        array.instantiate_element(iob_tiles[Orientation.north], (i, 7))
        array.instantiate_element(iob_tiles[Orientation.east], (7, i))
        array.instantiate_element(iob_tiles[Orientation.south], (i, 0))
        array.instantiate_element(iob_tiles[Orientation.west], (0, i))
    for x in range(1, 7, 3):
        for y in range(1, 7, 3):
            array.instantiate_element(subarray, (x, y))

    # 9 sboxes and more
    for env, sbox in iteritems(lib.sboxes):
        populate_switch_box(sbox, sgmts, env)
        generate_wilton(sbox, sgmts, cycle_free = True)
    netify_array(subarray)
    netify_array(array)

    # 10. switchify!
    for box in chain(itervalues(lib.cboxes), itervalues(lib.sboxes)):
        switchify(lib, box)

    # 11. generate files
    for module in chain(itervalues(lib.switches), itervalues(lib.sboxes), itervalues(lib.cboxes),
            itervalues(iob_tiles), iter((clb_tile, bram_tile, subarray, array))):
        gen.generate_module(tmpdir.join(module.name + '.v').open(OpenMode.w), module)
