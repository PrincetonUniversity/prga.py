# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.primitive.builtin import Flipflop, LUT, Memory
from prga.arch.block.cluster import Cluster

def test_cluster(tmpdir):
    cluster = Cluster('mock_cluster')
    ff = Flipflop()
    lut = LUT(4)

    # 1. add some ports
    cluster.add_clock('clk')
    cluster.add_input('I', 4)
    cluster.add_output('O', 2)

    # 2. add some instances
    ffinst = cluster.instantiate(ff, 'ff')
    lutinst = cluster.instantiate(lut, 'lut')

    # 3. connect stuff
    cluster.connect(cluster.ports['I'], lutinst.pins['in'])
    cluster.connect(cluster.ports['clk'], ffinst.pins['clk'])
    cluster.connect(lutinst.pins['out'], ffinst.pins['D'])
    cluster.connect(lutinst.pins['out'], cluster.ports['O'][0])
    cluster.connect(ffinst.pins['Q'], cluster.ports['O'][1])
