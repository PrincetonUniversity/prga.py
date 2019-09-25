# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.primitive.builtin import LUT
from prga.arch.multimode.multimode import BaseMode, BaseMultimode
from prga.arch.net.port import ConfigInputPort

class MockMultimode(BaseMultimode):
    def create_mode(self, name):
        return self._add_mode(BaseMode(name, self))

def test_multimode():
    mm = MockMultimode('mock_multimode', 'fake_template')
    lut5 = LUT(5)
    lut6 = LUT(6)

    # 1. add some ports
    mm.create_input('in', 6)
    mm.create_output('o6', 1)
    mm.create_output('o5', 1)

    # This is kinda cheating
    mm._add_port(ConfigInputPort(mm, 'cfg_d', 64))

    # 2. create mode: LUT6x1
    l6x1 = mm.create_mode('lut6x1')
    lut6inst = l6x1.instantiate(lut6, 'lut')
    l6x1.connect(l6x1.ports['in'], lut6inst.pins['in'])
    l6x1.connect(lut6inst.pins['out'], l6x1.ports['o6'])

    # This is kinda cheating, too
    lut6inst.all_pins['cfg_d'].source = l6x1.all_ports['cfg_d']

    # 3. create mode: LUT5x2
    l5x2 = mm.create_mode('lut5x2')
    for i in range(2):
        inst = l5x2.instantiate(lut5, 'lut' + str(i))
        l5x2.connect(l5x2.ports['in'][0:5], inst.pins['in'])
        l5x2.connect(inst.pins['out'], l5x2.ports['o6'] if i == 0 else l5x2.ports['o5'])

        inst.all_pins['cfg_d'].source = l5x2.all_ports['cfg_d'][32 * i: 32 * (i + 1)]
