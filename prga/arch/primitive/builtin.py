# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigInputPort
from prga.arch.module.module import BaseModule
from prga.arch.primitive.common import PrimitiveClass, PrimitivePortClass
from prga.arch.primitive.port import PrimitiveClockPort, PrimitiveInputPort, PrimitiveOutputPort
from prga.arch.primitive.primitive import AbstractPrimitive
from prga.exception import PRGAInternalError
from prga.util import ReadonlyMappingProxy

from collections import OrderedDict

__all__ = ['Inpad', 'Outpad', 'Iopad', 'Flipflop', 'LUT', 'SinglePortMemory', 'DualPortMemory']

# ----------------------------------------------------------------------------
# -- Base Class for Built-in Primitives --------------------------------------
# ----------------------------------------------------------------------------
class _BaseBuiltinPrimitive(BaseModule, AbstractPrimitive):
    """Base class for built-in primitives.

    Args:
        name (:obj:`str`): Name of this primitive
    """

    __slots__ = ['_ports']
    def __init__(self, name):
        super(_BaseBuiltinPrimitive, self).__init__(name)
        self._ports = OrderedDict()

# ----------------------------------------------------------------------------
# -- Logical-only Inpad ------------------------------------------------------
# ----------------------------------------------------------------------------
class Inpad(_BaseBuiltinPrimitive):
    """Logical-only input pad.
    
    Args:
        name (:obj:`str`): Name of this primitive
    """

    def __init__(self, name = "inpad"):
        super(Inpad, self).__init__(name)
        self._add_port(PrimitiveOutputPort(self, 'inpad', 1))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def primitive_class(self):
        return PrimitiveClass.inpad

    @property
    def verilog_template(self):
        raise PRGAInternalError("No template for logical-only module '{}'".format(self))

    @property
    def verilog_source(self):
        raise PRGAInternalError("No Verilog source file for logical-only module '{}'".format(self))

# ----------------------------------------------------------------------------
# -- Logical-only Outpad -----------------------------------------------------
# ----------------------------------------------------------------------------
class Outpad(_BaseBuiltinPrimitive):
    """Logical-only output pad.

    Args:
        name (:obj:`str`): Name of this primitive
    """

    def __init__(self, name = "outpad"):
        super(Outpad, self).__init__(name)
        self._add_port(PrimitiveInputPort(self, 'outpad', 1))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def primitive_class(self):
        return PrimitiveClass.outpad

    @property
    def verilog_template(self):
        raise PRGAInternalError("No template for logical-only module '{}'".format(self))

    @property
    def verilog_source(self):
        raise PRGAInternalError("No Verilog source file for logical-only module '{}'".format(self))

# ----------------------------------------------------------------------------
# -- Logical-only Iopad ------------------------------------------------------
# ----------------------------------------------------------------------------
class Iopad(_BaseBuiltinPrimitive):
    """Logical-only configurable input/output pad.

    Args:
        name (:obj:`str`): Name of this primitive
    """

    def __init__(self, name = "iopad"):
        super(Iopad, self).__init__(name)
        self._add_port(PrimitiveInputPort(self, 'outpad', 1))
        self._add_port(PrimitiveOutputPort(self, 'inpad', 1))
        self._add_port(ConfigInputPort(self, 'oe', 1))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def primitive_class(self):
        return PrimitiveClass.iopad

    @property
    def verilog_template(self):
        raise PRGAInternalError("No template for logical-only module '{}'".format(self))

    @property
    def verilog_source(self):
        raise PRGAInternalError("No Verilog source file for logical-only module '{}'".format(self))

# ----------------------------------------------------------------------------
# -- D-Flipflop --------------------------------------------------------------
# ----------------------------------------------------------------------------
class Flipflop(_BaseBuiltinPrimitive):
    """Non-configurable D-flipflop.

    Args:
        name (:obj:`str`): Name of this primitive
    """

    def __init__(self, name = 'flipflop'):
        super(Flipflop, self).__init__(name)
        self._add_port(PrimitiveClockPort(self, 'clk', port_class = PrimitivePortClass.clock))
        self._add_port(PrimitiveInputPort(self, 'D', 1, clock = 'clk', port_class = PrimitivePortClass.D))
        self._add_port(PrimitiveOutputPort(self, 'Q', 1, clock = 'clk', port_class = PrimitivePortClass.Q))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def primitive_class(self):
        return PrimitiveClass.flipflop

    @property
    def verilog_template(self):
        return 'flipflop.tmpl.v'

# ----------------------------------------------------------------------------
# -- LUT ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class LUT(_BaseBuiltinPrimitive):
    """Look-up table.

    Args:
        width (:obj:`int`): Number of input bits of this LUT
        name (:obj:`str`): Name of this primitive. Default to 'lut{width}'
    """

    def __init__(self, width, name = None):
        if width < 2 or width > 8:
            raise PRGAInternalError("LUT size '{}' not supported. Supported size: 2 <= width <= 8"
                    .format(width))
        name = name or ("lut" + str(width))
        super(LUT, self).__init__(name)
        self._add_port(PrimitiveInputPort(self, 'in', width, port_class = PrimitivePortClass.lut_in))
        self._add_port(PrimitiveOutputPort(self, 'out', 1, combinational_sources = ('in', ),
                port_class = PrimitivePortClass.lut_out))
        self._add_port(ConfigInputPort(self, 'cfg_d', 2 ** width))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def primitive_class(self):
        return PrimitiveClass.lut

    @property
    def verilog_template(self):
        return 'lut.tmpl.v'

# ----------------------------------------------------------------------------
# -- Memory ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Memory(_BaseBuiltinPrimitive):
    """Memory.

    Args:
        addr_width (:obj:`int`): Width of the address bus
        data_width (:obj:`int`): Width of the data bus
        name (:obj:`str`): Name of this memory
        dualport (:obj:`bool`): If set, two set of read/write port are be generated
        transparent (:obj:`bool`): If set, each read/write port is transparent
    """

    __slots__ = ['_addr_width', '_data_width', '_dualport', '_transparent']
    def __init__(self, addr_width, data_width, name = None, dualport = False, transparent = False):
        name = name or '{}p{}ram_a{}_d{}'.format('d' if dualport else 's', 
                't' if transparent else '', addr_width, data_width)
        super(Memory, self).__init__(name)
        self._addr_width = addr_width
        self._data_width = data_width
        self._dualport = dualport
        self._transparent = transparent
        if dualport:
            self._add_port(PrimitiveClockPort(self, 'clk', port_class = PrimitivePortClass.clock))
            self._add_port(PrimitiveInputPort(self, 'aaddr', addr_width, clock = 'clk', port_class =
                    PrimitivePortClass.address1))
            self._add_port(PrimitiveInputPort(self, 'adin', data_width, clock = 'clk', port_class =
                    PrimitivePortClass.data_in1))
            self._add_port(PrimitiveInputPort(self, 'awe', 1, clock = 'clk', port_class =
                    PrimitivePortClass.write_en1))
            self._add_port(PrimitiveOutputPort(self, 'adout', data_width, clock = 'clk', port_class = 
                    PrimitivePortClass.data_out1))
            self._add_port(PrimitiveInputPort(self, 'baddr', addr_width, clock = 'clk', port_class =
                    PrimitivePortClass.address2))
            self._add_port(PrimitiveInputPort(self, 'bdin', data_width, clock = 'clk', port_class =
                    PrimitivePortClass.data_in2))
            self._add_port(PrimitiveInputPort(self, 'bwe', 1, clock = 'clk', port_class =
                    PrimitivePortClass.write_en2))
            self._add_port(PrimitiveOutputPort(self, 'bdout', data_width, clock = 'clk', port_class = 
                    PrimitivePortClass.data_out2))
        else:
            self._add_port(PrimitiveClockPort(self, 'clk', port_class = PrimitivePortClass.clock))
            self._add_port(PrimitiveInputPort(self, 'addr', addr_width, clock = 'clk', port_class =
                    PrimitivePortClass.address))
            self._add_port(PrimitiveInputPort(self, 'din', data_width, clock = 'clk', port_class =
                    PrimitivePortClass.data_in))
            self._add_port(PrimitiveInputPort(self, 'we', 1, clock = 'clk', port_class =
                    PrimitivePortClass.write_en))
            self._add_port(PrimitiveOutputPort(self, 'dout', data_width, clock = 'clk', port_class = 
                    PrimitivePortClass.data_out))

    # == low-level API =======================================================
    @property
    def addr_width(self):
        return self._addr_width

    @property
    def data_width(self):
        return self._data_width

    @property
    def dualport(self):
        return self._dualport

    @property
    def transparent(self):
        return self._transparent

    # -- implementing properties/methods required by superclass --------------
    @property
    def primitive_class(self):
        return PrimitiveClass.memory

    @property
    def verilog_template(self):
        return 'memory.tmpl.v'
