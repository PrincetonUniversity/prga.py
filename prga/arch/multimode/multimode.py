# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.const import UNCONNECTED
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import BaseModule
from prga.arch.module.instance import RegularInstance
from prga.arch.primitive.common import PrimitiveClass
from prga.arch.primitive.primitive import AbstractPrimitive
from prga.arch.block.cluster import ClusterLike
from prga.arch.multimode.port import (MultimodeClockPort, MultimodeInputPort, MultimodeOutputPort,
        ModeInputPort, ModeOutputPort)
from prga.exception import PRGAInternalError

from collections import OrderedDict
from abc import abstractmethod

__all__ = ['Multimode']

# ----------------------------------------------------------------------------
# -- Mode Ports Proxy --------------------------------------------------------
# ----------------------------------------------------------------------------
class _ModePortsProxy(Mapping):
    """Helper class for `Mode._ports` property.

    Args:
        mode (`Mode`): Parent mode
    """

    __slots__ = ["mode"]
    def __init__(self, mode):
        super(_ModePortsProxy, self).__init__()
        self.mode = mode

    def __getitem__(self, key):
        try:
            port = self.mode.parent.all_ports[key]
        except KeyError:
            raise KeyError(key)
        return self.mode._mapped_ports.setdefault(key,
                port.direction.case(ModeInputPort, ModeOutputPort)(self.mode, port))

    def __len__(self):
        return len(self.mode.parent.all_ports)

    def __iter__(self):
        return iter(self.mode.parent.all_ports)

# ----------------------------------------------------------------------------
# -- Mode --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Mode(ClusterLike):
    """One mode of a multi-mode primitive.

    Args:
        name (:obj:`str`): Name of the mode
        parent (`Multimode`): Parent multi-mode primitive of this mode

    Note:
        This class and its API are not enough to describe a mode. Since multi-mode modules
        are usually highly coupled with the configuration circuitry, special ports or more may be needed, for example,
        what to do when this mode is selected.
    """

    __slots__ = ['_parent', '_mapped_ports', '_instances']
    def __init__(self, name, parent):
        super(Mode, self).__init__(name)
        self._parent = parent
        self._mapped_ports = {}
        self._instances = OrderedDict()

    def __str__(self):
        return '{}[{}]'.format(self.parent, self.name)

    # == internal API ========================================================
    @property
    def _ports(self):
        return _ModePortsProxy(self)

    def _validate_model(self, model):
        if not (model.module_class.is_primitive or model.module_class.is_cluster):
            raise PRGAInternalError("Only primitives and clusters may be instantiated in a mode.")

    # == low-level API =======================================================
    @property
    def parent(self):
        """`Multimode`: Parent multi-mode primitive of this mode."""
        return self._parent

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_physical(self):
        return False

    @property
    def module_class(self):
        return ModuleClass.mode

# ----------------------------------------------------------------------------
# -- Multi-mode Primitive ----------------------------------------------------
# ----------------------------------------------------------------------------
class Multimode(BaseModule, AbstractPrimitive):
    """Multi-mode primitve.

    Args:
        name (:obj:`str`): Name of this module
        verilog_template (:obj:`str`): Path to the template (or vanilla Verilog source file)

    Note:
        This class and its API are not enough to describe a multi-mode primitive. Since multi-mode modules
        are usually highly coupled with the configuration circuitry, special ports or more may be needed.
    """

    __slots__ = ['_ports', '_modes', '_verilog_template']
    def __init__(self, name, verilog_template):
        super(Multimode, self).__init__(name)
        self._ports = OrderedDict()
        self._modes = OrderedDict()
        self._verilog_template = verilog_template

    # == internal API ========================================================
    def _add_mode(self, mode):
        """Add a mode to this primitive.

        Args:
            mode (`Mode`):
        """
        if mode.name in self._modes:
            raise PRGAInternalError("Mode '{}' already exist in multi-mode primitive '{}'"
                    .format(mode.name, self))
        return self._modes.setdefault(mode.name, mode)

    # == low-level API =======================================================
    @property
    def modes(self):
        """:obj:`Mapping`: [:obj:`str`, `Mode` ]: A mapping from mode names to modes."""
        return self._modes

    def create_clock(self, name):
        """Create and add a clock input port to this multimode primitive.

        Args:
            name (:obj:`str`): Name of this clock
        """
        return self._add_port(MultimodeClockPort(self, name))

    def create_input(self, name, width, clock = None):
        """Create and add an input port to this multimode primitive.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in this port
            clock (:obj:`str`): If set, this port will be treated as a sequential endpoint sampled at the rising edge
                of ``clock``
        """
        return self._add_port(MultimodeInputPort(self, name, width, clock))

    def create_output(self, name, width, clock = None, combinational_sources = tuple()):
        """Create and add an output port to this multimode primitive.

        Args:
            name (:obj:`str`): Name of this port
            width (:obj:`int`): Number of bits in this port
            clock (:obj:`str`): If set, this port will be treated as a sequential startpoint sampled at the rising edge
                of ``clock``
            combinational_sources (:obj:`Iterable` [:obj:`str` ]): Input ports in the parent primitive from which
                combinational paths exist to this port
        """
        return self._add_port(MultimodeOutputPort(self, name, width, clock, combinational_sources))

    def create_mode(self, name):
        """Create a mode in this multi-mode primitive.

        Args:
            name (:obj:`str`): Name of the mode to create
        """
        return self._add_mode(Mode(name, self))

    # -- implementing properties/methods required by superclass --------------
    @property
    def verilog_template(self):
        return self._verilog_template

    @property
    def primitive_class(self):
        return PrimitiveClass.multimode
