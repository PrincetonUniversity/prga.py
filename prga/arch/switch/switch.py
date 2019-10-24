# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigInputPort
from prga.arch.module.common import ModuleClass
from prga.arch.module.module import AbstractLeafModule, BaseModule
from prga.arch.module.instance import RegularInstance
from prga.arch.switch.port import SwitchInputPort, SwitchOutputPort
from prga.exception import PRGAInternalError
from prga.util import Object, ReadonlyMappingProxy

from abc import abstractproperty
from collections import OrderedDict
import math

__all__ = ['AbstractSwitch', 'ConfigurableMUX']

# ----------------------------------------------------------------------------
# -- Abstract Switch ---------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractSwitch(AbstractLeafModule):
    """Abstract base class for switches."""

    # == low-level API =======================================================
    # -- properties/methods to be overriden by subclasses --------------------
    @abstractproperty
    def switch_inputs(self):
        """:obj:`Sequence` [`AbstractSourceBit` ]: Inputs of this switch."""
        raise NotImplementedError

    @abstractproperty
    def switch_output(self):
        """`AbstractSinkBit`: Output of this switch."""
        raise NotImplementedError

    # -- implementing properties/methods required by superclass --------------
    @property
    def module_class(self):
        return ModuleClass.switch

# ----------------------------------------------------------------------------
# -- Configurable MUX --------------------------------------------------------
# ----------------------------------------------------------------------------
class ConfigurableMUX(BaseModule, AbstractSwitch):
    """Basic type of congigurable MUX.

    Args:
        width (:obj:`int`): Number of inputs of this mux
        name (:obj:`int`): Name of this mux
        in_physical_domain (:obj:`bool`):
    """

    __slots__ = ['_ports', 'in_physical_domain']
    def __init__(self, width, name = None, in_physical_domain = True):
        if width < 2:
            raise PRGAInternalError("Configurable MUX size '{}' not supported. Supported size: width >= 2"
                    .format(width))
        name = name or ('cfg_mux' + str(width))
        super(ConfigurableMUX, self).__init__(name)
        self._ports = OrderedDict()
        self.in_physical_domain = in_physical_domain
        self._add_port(SwitchInputPort(self, 'i', width))
        self._add_port(SwitchOutputPort(self, 'o', 1, combinational_sources = ('i', )))
        self._add_port(ConfigInputPort(self, 'cfg_d', int(math.ceil(math.log(width, 2)))))

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def switch_inputs(self):
        return self._ports['i']

    @property
    def switch_output(self):
        return self._ports['o'][0]

    @property
    def verilog_template(self):
        return 'cfg_mux.tmpl.v'

# ----------------------------------------------------------------------------
# -- Switch Instance ---------------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchInstance(RegularInstance):
    """Switch instances.

    Args:
        parent (`AbstractModule`): parent module of this instance
        model (`AbstractSwitch`): model of this instance
        name (:obj:`str`): name of this instance
    """

    # == low-level API =======================================================
    @property
    def switch_inputs(self):
        return tuple(self.logical_pins[bit.bus.key][bit.index] for bit in self.model.switch_inputs)

    @property
    def switch_output(self):
        return self.logical_pins[self.model.switch_output.bus.key][self.model.switch_output.index]
