# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.module.common import ModuleClass
from prga.arch.module.module import AbstractLeafModule, BaseLeafModule
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
class CustomPrimitive(BaseLeafModule, AbstractPrimitive):
    """User-defined primitives.
    
    Args:
        name (:obj:`str`): Name of this primitive
        verilog_template (:obj:`str`): Path to the template (or vanilla Verilog source file)
    """

    __slots__ = ['_verilog_template']
    def __init__(self, name, verilog_template):
        super(CustomPrimitive, self).__init__(name)
        self._verilog_template = verilog_template

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return self._verilog_template

    @property
    def primitive_class(self):
        return PrimitiveClass.custom

    # == high-level API ======================================================
    def add_clock(self, name):
        """Create and add a clock input port to this primitive.

        Args:
            name (:obj:`str`): Name of this clock
        """
        return self._add_port(PrimitiveClockPort(self, name))

    def add_input(self, name, width, clock = None):
        """Create and add an input port to this primitive.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in this port
            clock (:obj:`str`): If set, this port will be treated as a sequential endpoint sampled at the rising edge
                of ``clock``
        """
        return self._add_port(PrimitiveInputPort(self, name, width, clock))

    def add_output(self, name, width, clock = None, combinational_sources = tuple()):
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
