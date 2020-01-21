# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.port import ConfigClockPort, ConfigInputPort, ConfigOutputPort
from prga.arch.multimode.port import MultimodeClockPort, MultimodeInputPort, MultimodeOutputPort
from prga.arch.multimode.multimode import Mode, Multimode
from prga.util import ReadonlyMappingProxy

from abc import abstractproperty

__all__ = ['PacketizedchainMode', 'PacketizedchainMultimode']

# ----------------------------------------------------------------------------
# -- Mode --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class PacketizedchainMode(Mode):
    """One mode of a multi-mode primitive for packetized-chain-style configuration circuitry.

    args:
        name (:obj:`str`): Name of the mode
        parent (`PacketizedchainMultimode`): Parent multi-mode primitive of this mode
        config_bitmap (:obj:`Mapping` [:obj:`str`, :obj:`int` ]): Mapping from sub-instance names to configuration
            bit offsets
        mode_enabling_bits (:obj:`Sequence` [:obj:`int` ]): Bits to be set to enable this mode
    """

    __slots__ = ['_config_bitmap', '_mode_enabling_bits']
    def __init__(self, name, parent, config_bitmap = {}, mode_enabling_bits = tuple()):
        super(PacketizedchainMode, self).__init__(name, parent)
        self._config_bitmap = ReadonlyMappingProxy(config_bitmap)
        self._mode_enabling_bits = mode_enabling_bits

    # == low-level API =======================================================
    @property
    def config_bitmap(self):
        """:obj:`Mapping` [:obj:`str`, :obj:`int` ]: A mapping from sub-instance names to configuration bit
        offsets."""
        return self._config_bitmap

    @property
    def mode_enabling_bits(self):
        """:obj:`Sequence` [:obj:`int` ]: Bits to be set to enable this mode."""
        return self._mode_enabling_bits

# ----------------------------------------------------------------------------
# -- Multimode ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class PacketizedchainMultimode(Multimode):
    """Multi-mode primitve for packetized-chain-style configuration circuitry.

    Args:
        name (:obj:`str`): Name of this module
    """

    # == low-level API =======================================================
    @property
    def config_bitcount(self):
        """Number of configuration bits in this module."""
        return 0
