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
        return self.sboxes.setdefault('mock_sbox', SwitchBox('mock_sbox'))

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
    for sbox in itervalues(lib.sboxes):
        populate_switch_box(sbox, sgmts)
        generate_wilton(sbox, sgmts, cycle_free = True)

    # 10. netify
    netify_array(array)

    # 11. switchify!
    for box in chain(itervalues(lib.cboxes), itervalues(lib.sboxes)):
        switchify(lib, box)

    # 12. generate files
    for module in chain(itervalues(lib.switches), itervalues(lib.sboxes), iter((array, ))):
        gen.generate_module(tmpdir.join(module.name + '.v').open(OpenMode.w), module)
