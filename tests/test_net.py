# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.net.common import NetClass
from prga.arch.net.const import UNCONNECTED
from prga.arch.net.bus import BaseClockPort, BaseInputPort, BaseOutputPort, BaseInputPin, BaseOutputPin
from prga.exception import PRGAInternalError

import pytest

class MockClockPort(BaseClockPort):
    __slots__ = ['name', 'net_class', 'is_physical', 'is_user_accessible']
    def __init__(self, parent, name,
            net_class = NetClass.slice_, is_physical = True, is_user_accessible = True):
        super(MockClockPort, self).__init__(parent)
        self.name = name
        self.net_class = net_class
        self.is_physical = is_physical
        self.is_user_accessible = is_user_accessible

class MockInputPort(BaseInputPort):
    __slots__ = ['name', 'width', 'net_class', 'is_physical', 'is_user_accessible']
    def __init__(self, parent, name, width,
            net_class = NetClass.slice_, is_physical = True, is_user_accessible = True):
        super(MockInputPort, self).__init__(parent)
        self.name = name
        self.width = width
        self.net_class = net_class
        self.is_physical = is_physical
        self.is_user_accessible = is_user_accessible

class MockOutputPort(BaseOutputPort):
    __slots__ = ['name', 'width', 'net_class', 'is_physical', 'is_user_accessible']
    def __init__(self, parent, name, width,
            net_class = NetClass.slice_, is_physical = True, is_user_accessible = True):
        super(MockOutputPort, self).__init__(parent)
        self.name = name
        self.width = width
        self.net_class = net_class
        self.is_physical = is_physical
        self.is_user_accessible = is_user_accessible

class MockInputPin(BaseInputPin):
    __slots__ = ['is_physical']
    def __init__(self, parent, model, is_physical = True):
        super(MockInputPin, self).__init__(parent, model)
        self.is_physical = is_physical

class MockOutputPin(BaseOutputPin):
    __slots__ = ['is_physical']
    def __init__(self, parent, model, is_physical = True):
        super(MockOutputPin, self).__init__(parent, model)
        self.is_physical = is_physical

def test_physical_source():
    module = 'mock_module'
    i = MockInputPort(module, 'mock_input', 4)
    o = MockOutputPort(module, 'mock_output', 4)

    # 2. connect bus
    o.physical_source = i
    assert not o[0]._is_static
    assert not o[0].physical_source._is_static

    # 3. save a dynamic object
    do0 = o[0]
    di0 = i[0]

    # 4. bit-wise assignment
    o[2].physical_source = i[1]
    assert o[2]._is_static
    assert o[2].physical_source is i[1]
    assert o[0]._is_static
    assert i[0]._is_static
    assert o[0].physical_source is i[0]
    assert o.physical_source == (i[0], i[1], i[1], i[3])

    # 5. use stale dynamic handler
    assert do0.physical_source is i[0]
    assert di0 is not i[0]
    do0.physical_source = i[3]
    o[3].physical_source = di0
    assert o[0].physical_source is i[3]
    assert o[3].physical_source is i[0]

def test_logical_source():
    module = 'mock_module'
    i = MockInputPort(module, 'mock_input', 4)
    o = MockOutputPort(module, 'mock_output', 4)

    # 2. connect bus
    o.logical_source = i
    assert not o[0]._is_static
    assert not o[0].logical_source._is_static

    # 3. save a dynamic object
    do0 = o[0]
    di0 = i[0]

    # 4. bit-wise assignment
    o[2].logical_source = i[1]
    assert o[2]._is_static
    assert o[2].logical_source is i[1]
    assert o[0]._is_static
    assert i[0]._is_static
    assert o[0].logical_source is i[0]
    assert o.logical_source == (i[0], i[1], i[1], i[3])

    # 5. use stale dynamic handler
    assert do0.logical_source is i[0]
    assert di0 is not i[0]
    do0.logical_source = i[3]
    o[3].logical_source = di0
    assert o[0].logical_source is i[3]
    assert o[3].logical_source is i[0]

def test_physical_cp():
    module = 'mock_module'
    l = MockInputPort(module, 'l', 4, is_physical = False)
    p = MockInputPort(module, 'p', 4)

    # 2. check initial physical counterpart
    assert l.physical_cp is None

    # 3. set physical counterpart
    l.physical_cp = p
    for i, bit in enumerate(l.physical_cp):
        assert not bit._is_static
        assert bit.bus is p
        assert bit.index == i

    # 4. save a dynamic object
    dl0 = l[0]
    dp0 = p[0]

    # 5. bit-wise assignment
    l[2].physical_cp = p[1]
    assert l[2]._is_static
    assert l[2].physical_cp is p[1]
    assert l[0]._is_static
    assert p[0]._is_static
    assert l[0].physical_cp is p[0]
    assert l.physical_cp == (p[0], p[1], p[1], p[3])

    # 6. user stale dynamic handler
    assert dl0.physical_cp is p[0]
    assert dp0 is not p[0]
    dl0.physical_cp = p[3]
    l[3].physical_cp = dp0
    assert l[0].physical_cp is p[3]
    assert l[3].physical_cp is p[0]

def test_regular_net():
    module = 'mock_module'

    # 1. create ports
    i = MockInputPort(module, 'i', 4)
    o = MockOutputPort(module, 'o', 4)
    li = MockInputPort(module, 'li', 4, is_physical = False)

    # 2. connect bus
    o.logical_source = i
    assert not o[0]._is_static
    assert not o[0].logical_source._is_static
    for idx, bit in enumerate(o.physical_source):
        assert not bit._is_static
        assert bit.bus is i
        assert bit.index is idx

    # 3. bit-wise
    o[0].logical_source = li[0]
    assert o[2]._is_static
    assert o[2].logical_source is i[2]
    assert o[0]._is_static
    assert i[0]._is_static
    assert li[0]._is_static
    assert o[0].logical_source is li[0]
    assert o[0].physical_source is UNCONNECTED
