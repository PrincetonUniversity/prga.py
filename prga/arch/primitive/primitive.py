# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.module.common import ModuleClass
from prga.arch.module.module import AbstractLeafModule, BaseModule
from prga.arch.primitive.common import PrimitiveClass
from prga.arch.primitive.port import PrimitiveClockPort, PrimitiveInputPort, PrimitiveOutputPort
from prga.exception import PRGAInternalError
from prga.util import ReadonlyMappingProxy

from abc import abstractproperty
from collections import OrderedDict

__all__ = ['AbstractPrimitive', 'CustomPrimitive']

# ----------------------------------------------------------------------------
# -- Abstract Primitive ------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractPrimitive(AbstractLeafModule):
    """Abstract base class for primitives."""

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.primitive

    # # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractproperty
    def primitive_class(self):
        """`PrimitiveClass`: Logical class of this primitive."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- User-Defined Primitive --------------------------------------------------
# ----------------------------------------------------------------------------
class CustomPrimitive(BaseModule, AbstractPrimitive):
    """User-defined primitives.
    
    Args:
        name (:obj:`str`): Name of this primitive
        verilog_template (:obj:`str`): Path to the template (or vanilla Verilog source file). If set, this custom
            primitive becomes physical. Otherwise, it is logical-only
    """

    __slots__ = ['_ports', '_verilog_template']
    def __init__(self, name, verilog_template = None):
        super(CustomPrimitive, self).__init__(name)
        self._ports = OrderedDict()
        self._verilog_template = verilog_template

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        if self._verilog_template is None:
            raise PRGAInternalError("Primitive '{}' is a logical-only module with no verilog template"
                    .format(self))
        return self._verilog_template

    @verilog_template.setter
    def verilog_template(self, template):
        self._verilog_template = template

    @property
    def in_physical_domain(self):
        return self._verilog_template is not None

    @property
    def primitive_class(self):
        return PrimitiveClass.custom

    # == high-level API ======================================================
    def create_clock(self, name):
        """Create and add a clock input port to this primitive.

        Args:
            name (:obj:`str`): Name of this clock
        """
        return self._add_port(PrimitiveClockPort(self, name))

    def create_input(self, name, width, clock = None):
        """Create and add an input port to this primitive.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in this port
            clock (:obj:`str`): If set, this port will be treated as a sequential endpoint sampled at the rising edge
                of ``clock``
        """
        return self._add_port(PrimitiveInputPort(self, name, width, clock))

    def create_output(self, name, width, clock = None, combinational_sources = tuple()):
        """Create and add an output port to this primitive.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in this port
            clock (:obj:`str`): If set, this port will be treated as a sequential startpoint sampled at the rising edge
                of ``clock``
            combinational_sources (:obj:`Iterable` [:obj:`str` ]): Input ports in the parent primitive from which
                combinational paths exist to this port
        """
        return self._add_port(PrimitiveOutputPort(self, name, width, clock, combinational_sources))
