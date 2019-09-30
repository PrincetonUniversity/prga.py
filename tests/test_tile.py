# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Global, Orientation, Dimension
from prga.arch.primitive.builtin import Iopad, Memory
from prga.arch.block.block import IOBlock, LogicBlock
from prga.arch.routing.common import SegmentPrototype
from prga.arch.switch.switch import ConfigurableMUX
from prga.arch.routing.box import ConnectionBox
from prga.arch.array.tile import Tile
from prga.algorithm.design.cbox import BlockPortFCValue, BlockFCValue, populate_connection_box, generate_fc
from prga.algorithm.design.tile import ConnectionBoxLibraryDelegate, cboxify, netify_tile
from prga.algorithm.design.switch import SwitchLibraryDelegate, switchify
from prga.rtlgen.rtlgen import VerilogGenerator

from itertools import chain

class Library(SwitchLibraryDelegate, ConnectionBoxLibraryDelegate):
    def __init__(self):
        self.switches = {}
        self.cboxes = {}

    def get_switch(self, width, module):
        return self.switches.setdefault(width, ConfigurableMUX(width))

    def get_cbox(self, block, orientation, position = None, channel = (0, 0)):
        orientation, position = block._validate_orientation_and_position(orientation, position)
        name = 'mock_cbox_{}_x{}y{}{}'.format(block.name, position.x, position.y, orientation.name[0])
        return self.cboxes.setdefault(name, ConnectionBox(name, orientation.dimension.perpendicular))

    def get_cbox_double_sided(self, dimension,
            block_ne = None, position_ne = None, block_sw = None, position_sw = None):
        raise NotImplementedError

def test_io_tile(tmpdir):
    io = Iopad()
    block = IOBlock('mock_block', 4, io)
    glb = Global('clk', is_clock = True)
    sgmts = [SegmentPrototype('L1', 4, 1), SegmentPrototype('L2', 1, 2)]
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
        switchify(lib, cbox_inst.model)

    # 5 switchify!
    switchify(lib, block)

    # 6. netify
    netify_tile(tile)

    # 7. generate files
    for module in chain(itervalues(lib.switches), itervalues(lib.cboxes), iter((tile, ))):
        gen.generate_module(tmpdir.join(module.name + '.v').open(OpenMode.w), module)

def test_logic_tile(tmpdir):
    mem = Memory(10, 8, 'mem8Kb')
    block = LogicBlock('mock_block', 1, 3)
    clk = Global('clk', is_clock = True)
    sgmts = [SegmentPrototype('L1', 4, 1), SegmentPrototype('L2', 1, 2)]
    lib = Library()
    gen = VerilogGenerator()

    # 1. add some ports
    block.create_global(clk, Orientation.south, position = (0, 0))
    block.create_input('addr', 10, Orientation.west, (0, 0))
    block.create_input('din', 8, Orientation.west, (0, 1))
    block.create_input('we', 1, Orientation.west, (0, 2))
    block.create_output('dout', 8, Orientation.east, (0, 0))

    # 2. create tile
    tile = Tile('mock_tile', block)

    # 3. cboxify
    cboxify(lib, tile)

    # 4. populate and generate connections
    for (position, orientation), cbox_inst in iteritems(tile.cbox_instances):
        populate_connection_box(cbox_inst.model, sgmts, tile.block, orientation, position,
                orientation.switch((0, 0), (0, 0), (0, -1), (-1, 0)))
        generate_fc(cbox_inst.model, sgmts, tile.block, orientation,
                BlockFCValue(BlockPortFCValue(0.5), BlockPortFCValue(1.0)), position,
                orientation.switch((0, 0), (0, 0), (0, -1), (-1, 0)))
        switchify(lib, cbox_inst.model)

    # 6. netify
    netify_tile(tile)

    # 7. generate files
    for module in chain(itervalues(lib.switches), itervalues(lib.cboxes), iter((tile, ))):
        gen.generate_module(tmpdir.join(module.name + '.v').open(OpenMode.w), module)
