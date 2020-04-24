# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.core.context import Context
from prga.core.common import ModuleView
from prga.exception import PRGAInternalError

class PktchainBitgen(object):
    _reversed_crc_lookup = {}   # to be filled later

    @classmethod
    def _int2bitseq(cls, v, bigendian = True):
        if bigendian:
            for i in reversed(range(v.bit_length())):
                yield 1 if v & (1 << i) else 0
        else:
            for i in range(v.bit_length()):
                yield 1 if v & (1 << i) else 0

    @classmethod
    def crc(cls, seq):
        crc = 0
        for i in seq:
            crc = ((crc << 1) & 0xFF) ^ (0x7 if bool(crc & 0x80) != bool(i) else 0x0)
        return crc

    @classmethod
    def reverse_crc(cls, crc, zeros = 0):
        for i in range(zeros):
            crc = (crc >> 1) ^ (0x83 if crc & 1 else 0x0)
        # brute force: replace with better implementation if this becomes the bottleneck
        try:
            return cls._reversed_crc_lookup[crc]
        except KeyError:
            raise PRGAInternalError("No prefix checksum found for CRC-8 CCITT value 0x{:08x} prepended with {} zeros"
                    .format(crc, zeros))

PktchainBitgen._reversed_crc_lookup = {
        PktchainBitgen.crc(PktchainBitgen._int2bitseq(i)) : i
        for i in range(256)}
