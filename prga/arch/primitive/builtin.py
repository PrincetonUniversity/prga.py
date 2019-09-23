# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigInputPort
from prga.arch.primitive.common import PrimitiveClass, PrimitivePortClass
from prga.arch.primitive.port import PrimitiveClockPort, PrimitiveInputPort, PrimitiveOutputPort
from prga.arch.primitive.primitive import AbstractPrimitive
from prga.exception import PRGAInternalError
from prga.util import ReadonlyMappingProxy, Object

from collections import OrderedDict

__all__ = ['Inpad', 'Outpad', 'Iopad', 'Flipflop', 'LUT', 'SinglePortMemory', 'DualPortMemory']

# ----------------------------------------------------------------------------
# -- Builtin Primitive -------------------------------------------------------
# ----------------------------------------------------------------------------
class BuiltinPrimitive(Object, AbstractPrimitive):
    """Base class fro builtin primitives."""

    __slots__ = ['_ports']
    # == internal API ========================================================
    def _add_port(self):
        raise PRGAInternalError("Cannot add port to built-in primitive '{}'"
                .format(self))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def all_ports(self):
        return ReadonlyMappingProxy(self._ports)

# ----------------------------------------------------------------------------
# -- Logical-only Inpad ------------------------------------------------------
# ----------------------------------------------------------------------------
class Inpad(BuiltinPrimitive):
    """Logical-only input pad."""

    def __init__(self):
        super(Inpad, self).__init__()
        self._ports = OrderedDict(
                (('inpad', PrimitiveOutputPort(self, 'inpad', 1)), ))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def name(self):
        return 'inpad'

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
class Outpad(BuiltinPrimitive):
    """Logical-only output pad."""

    def __init__(self):
        super(Outpad, self).__init__()
        self._ports = OrderedDict(
                (('outpad', PrimitiveInputPort(self, 'outpad', 1)),))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def name(self):
        return 'outpad'

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
class Iopad(BuiltinPrimitive):
    """Logical-only configurable input/output pad."""

    def __init__(self):
        super(Iopad, self).__init__()
        self._ports = OrderedDict((
            ('outpad', PrimitiveInputPort(self, 'outpad', 1)),
            ('inpad', PrimitiveOutputPort(self, 'inpad', 1)),
            ('oe', ConfigInputPort(self, 'oe', 1)),
            ))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def name(self):
        return 'iopad'

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
class Flipflop(BuiltinPrimitive):
    """Non-configurable D-flipflop.

    Args:
        name (:obj:`str`): Name of this primitive
    """

    __slots__ = ['_name', '_verilog_source']
    def __init__(self, name = 'flipflop'):
        super(Flipflop, self).__init__()
        self._name = name
        self._ports = OrderedDict((
            ('clk', PrimitiveClockPort(self, 'clk', port_class = PrimitivePortClass.clock)),
            ('D', PrimitiveInputPort(self, 'D', 1, clock = 'clk', port_class = PrimitivePortClass.D)),
            ('Q', PrimitiveOutputPort(self, 'Q', 1, clock = 'clk', port_class = PrimitivePortClass.Q)),
            ))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

    @property
    def primitive_class(self):
        return PrimitiveClass.flipflop

    @property
    def verilog_template(self):
        return 'flipflop.tmpl.v'

    @property
    def verilog_source(self):
        try:
            return self._verilog_source
        except AttributeError:
            raise PRGAInternalError("Verilog source file not generated for module '{}' yet."
                    .format(self))

    @verilog_source.setter
    def verilog_source(self, source):
        self._verilog_source = source

# ----------------------------------------------------------------------------
# -- LUT ---------------------------------------------------------------------
# ----------------------------------------------------------------------------
class LUT(BuiltinPrimitive):
    """Look-up table.

    Args:
        width (:obj:`int`): Width of this LUT
        name (:obj:`str`): Name of this primitive. Default to 'lut{width}'
    """

    __slots__ = ['_name', '_width', '_verilog_source']
    def __init__(self, width, name = None):
        if width < 2 or width > 8:
            raise PRGAInternalError("LUT size '{}' not supported. Supported size: 2 <= width <= 8"
                    .format(width))
        super(LUT, self).__init__()
        self._name = name or ("lut" + str(width))
        self._width = width
        self._ports = OrderedDict((
            ('in', PrimitiveInputPort(self, 'in', width, port_class = PrimitivePortClass.lut_in)),
            ('out', PrimitiveOutputPort(self, 'out', 1, port_class = PrimitivePortClass.lut_out)),
            ('cfg_d', ConfigInputPort(self, 'cfg_d', 2 ** width)),
            ))

    # == low-level API =======================================================
    @property
    def width(self):
        return self._width

    # -- implementing properties/methods required by superclass --------------
    @property
    def name(self):
        return self._name

    @property
    def primitive_class(self):
        return PrimitiveClass.lut

    @property
    def verilog_template(self):
        return 'lut.tmpl.v'

    @property
    def verilog_source(self):
        try:
            return self._verilog_source
        except AttributeError:
            raise PRGAInternalError("Verilog source file not generated for module '{}' yet."
                    .format(self))

    @verilog_source.setter
    def verilog_source(self, source):
        self._verilog_source = source

# ----------------------------------------------------------------------------
# -- Memory ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Memory(BuiltinPrimitive):
    """Memory.

    Args:
        addr_width (:obj:`int`): Width of the address bus
        data_width (:obj:`int`): Width of the data bus
        name (:obj:`str`): Name of this memory
        dualport (:obj:`bool`): If set, two set of read/write port are be generated
        transparent (:obj:`bool`): If set, each read/write port is transparent
    """

    __slots__ = ['_name', '_addr_width', '_data_width', '_dualport', '_transparent', '_verilog_source']
    def __init__(self, addr_width, data_width, name = None, dualport = False, transparent = False):
        super(Memory, self).__init__()
        self._addr_width = addr_width
        self._data_width = data_width
        self._name = name or '{}p{}ram_a{}_d{}'.format('d' if dualport else 's', 
                't' if transparent else '', addr_width, data_width)
        self._dualport = dualport
        self._transparent = transparent
        if dualport:
            self._ports = OrderedDict((
                ('clk', PrimitiveClockPort(self, 'clk', port_class = PrimitivePortClass.clock)),
                ('aaddr', PrimitiveInputPort(self, 'aaddr', addr_width, clock = 'clk', port_class =
                    PrimitivePortClass.address1)),
                ('adin', PrimitiveInputPort(self, 'adin', data_width, clock = 'clk', port_class =
                    PrimitivePortClass.data_in1)),
                ('awe', PrimitiveInputPort(self, 'awe', 1, clock = 'clk', port_class =
                    PrimitivePortClass.write_en1)),
                ('adout', PrimitiveOutputPort(self, 'adout', data_width, clock = 'clk', port_class = 
                    PrimitivePortClass.data_out1)),
                ('baddr', PrimitiveInputPort(self, 'baddr', addr_width, clock = 'clk', port_class =
                    PrimitivePortClass.address2)),
                ('bdin', PrimitiveInputPort(self, 'bdin', data_width, clock = 'clk', port_class =
                    PrimitivePortClass.data_in2)),
                ('bwe', PrimitiveInputPort(self, 'bwe', 1, clock = 'clk', port_class =
                    PrimitivePortClass.write_en2)),
                ('bdout', PrimitiveOutputPort(self, 'bdout', data_width, clock = 'clk', port_class = 
                    PrimitivePortClass.data_out2)),
                ))
        else:
            self._ports = OrderedDict((
                ('clk', PrimitiveClockPort(self, 'clk', port_class = PrimitivePortClass.clock)),
                ('addr', PrimitiveInputPort(self, 'addr', addr_width, clock = 'clk', port_class =
                    PrimitivePortClass.address)),
                ('din', PrimitiveInputPort(self, 'din', data_width, clock = 'clk', port_class =
                    PrimitivePortClass.data_in)),
                ('we', PrimitiveInputPort(self, 'we', 1, clock = 'clk', port_class =
                    PrimitivePortClass.write_en)),
                ('dout', PrimitiveOutputPort(self, 'dout', data_width, clock = 'clk', port_class = 
                    PrimitivePortClass.data_out)),
                ))

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
    def name(self):
        return self._name

    @property
    def primitive_class(self):
        return PrimitiveClass.memory

    @property
    def verilog_template(self):
        return 'memory.tmpl.v'

    @property
    def verilog_source(self):
        try:
            return self._verilog_source
        except AttributeError:
            raise PRGAInternalError("Verilog source file not generated for module '{}' yet."
                    .format(self))

    @verilog_source.setter
    def verilog_source(self, source):
        self._verilog_source = source
