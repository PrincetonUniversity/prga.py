# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function, unicode_literals
from prga.compatible import *

from prga.arch.net.common import NetClass
from prga.arch.net.bus import BaseClockPort, BaseInputPort, BaseOutputPort, BaseInputPin, BaseOutputPin

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

class TestNetBasic(object):
    def test_net_basic(self):
        module = 'mock_module'
        instance = 'mock_instance'

        i = MockInputPort(module, 'mock_input', 4)
        o = MockOutputPort(module, 'mock_output', 4)
