# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.common import Global, Orientation
from prga.arch.primitive.builtin import Flipflop, LUT
from prga.arch.block.cluster import Cluster
from prga.arch.block.block import LogicBlock
from prga.arch.switch.switch import ConfigurableMUX
from prga.algorithm.design.switch import SwitchLibraryDelegate, switchify
from prga.algorithm.design.physical import physicalify
from prga.rtlgen.rtlgen import VerilogGenerator

from itertools import chain

class SwitchLibrary(SwitchLibraryDelegate):
    def __init__(self):
        self.switches = {}

    def get_or_create_switch(self, width, module, in_physical_domain = True):
        return self.switches.setdefault(width, ConfigurableMUX(width))

    @property
    def is_empty(self):
        return False

def test_rtlgen(tmpdir):
    gen = VerilogGenerator()
    lib = SwitchLibrary()

    ff = Flipflop()
    lut = LUT(4)
    clk = Global('clk', is_clock = True)

    # 1. cluster
    cluster = Cluster('mock_cluster')

    # 1.1 add some ports
    cluster.create_clock('clk')
    cluster.create_input('I', 4)
    cluster.create_output('O', 1)

    # 1.2 add some instances
    ffinst = cluster.instantiate(ff, 'ff')
    lutinst = cluster.instantiate(lut, 'lut')

    # 1.3 connect stuff
    cluster.connect(cluster.ports['I'], lutinst.pins['in'])
    cluster.connect(cluster.ports['clk'], ffinst.pins['clk'])
    cluster.connect(lutinst.pins['out'], ffinst.pins['D'])
    cluster.connect(lutinst.pins['out'], cluster.ports['O'])
    cluster.connect(ffinst.pins['Q'], cluster.ports['O'])

    # 1.4 switchify!
    switchify(lib, cluster)
    physicalify(cluster)

    # 2. block
    block = LogicBlock('mock_block')
    
    # 2.1 add some ports
    block.create_global(clk, Orientation.south)
    block.create_input('I', 8, Orientation.west)
    block.create_output('O', 2, Orientation.east)

    # 2.2 add some instances and connections
    for i in range(2):
        clst = block.instantiate(cluster, 'clst' + str(i))
        block.connect(block.ports['clk'], clst.pins['clk'])
        block.connect(block.ports['I'][4 * i: 4 * (i + 1)], clst.pins['I'])
        block.connect(clst.pins['O'], block.ports['O'][i])

    # 2.3 switchify!
    switchify(lib, block)
    physicalify(block)

    # 4. generate files
    for module in chain(itervalues(lib.switches), iter((ff, lut, cluster, block))):
        gen.generate_module(tmpdir.join(module.name + '.v').open(OpenMode.wb), module)
