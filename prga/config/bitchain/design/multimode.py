# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.multimode.port import MultimodeClockPort, MultimodeInputPort, MultimodeOutputPort
from prga.arch.multimode.multimode import Mode, Multimode
from prga.util import ReadonlyMappingProxy

from abc import abstractproperty

__all__ = ['BitchainMode', 'BitchainMultimode']

# ----------------------------------------------------------------------------
# -- Mode --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class BitchainMode(Mode):
    """one mode of a multi-mode primitive for bitchain-style configuration circuitry.

    args:
        name (:obj:`str`): Name of the mode
        parent (`multimode`): Parent multi-mode primitive of this mode
        config_bit_offset (:obj:`Mapping` [:obj:`str`, :obj:`int` ]): Mapping from sub-instance names to configuration
            bit offsets
        mode_enabling_bits (:obj:`Sequence` [:obj:`int`]): Bits to be set to enable this mode
    """

    __slots__ = ['_config_bit_offset', '_mode_enabling_bits']
    def __init__(self, name, parent, config_bit_offset = {}, mode_enabling_bits = tuple()):
        super(BitchainMode, self).__init__(name, parent)
        self._config_bit_offset = ReadonlyMappingProxy(config_bit_offset)
        self._mode_enabling_bits = mode_enabling_bits

    # == low-level API =======================================================
    @property
    def config_bit_offset(self):
        """:obj:`Mapping` [:obj:`str`, :obj:`int` ]: A mapping from sub-instance names to configuration bit
        offsets."""
        return self._config_bit_offset

    @property
    def mode_enabling_bits(self):
        """:obj:`Sequence` [:obj:`int` ]: Bits to be set to enable this mode."""
        return self._mode_enabling_bits

# ----------------------------------------------------------------------------
# -- Multimode ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class BitchainMultimode(Multimode):
    """Multi-mode primitve for bitchain-style configuration circuitry.

    Args:
        name (:obj:`str`): Name of this module
    """

    # == low-level API =======================================================
    @property
    def config_bit_count(self):
        """Number of configuration bits in this module."""
        return 0
