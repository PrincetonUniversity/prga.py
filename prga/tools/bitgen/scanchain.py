# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator

from bitarray import bitarray
import struct

import logging
_logger = logging.getLogger(__name__)

__all__ = ['ScanchainBitstreamGenerator']

class ScanchainBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'scanchain' programming circuitry."""

    __slots__ = ["qwords", "bits"]

    def __init__(self, context):
        super().__init__(context)

        bitstream_size = self.context.summary.scanchain["bitstream_size"]

        # initialize bitstream
        self.qwords = bitstream_size // 64 + (1 if bitstream_size % 64 > 0 else 0)
        self.bits = bitarray('0', endian='little') * (self.qwords * 64)

    def set_bits(self, value, hierarchy = None, inplace = False):
        if hierarchy:
            for i in hierarchy.hierarchy:
                if (bitmap := getattr(i, "scanchain_bitmap", self._none)) is self._none:
                    if (bitmap := getattr(i, "prog_bitmap", self._none)) is self._none:
                        continue

                if bitmap is None:
                    return

                else:
                    value = value.remap(bitmap, inplace = inplace)
                    inplace = True

        for v, (offset, length) in value.breakdown():
            segment = bitarray(bin(v)[2:])
            segment.reverse()
            if length > len(segment):
                segment.extend('0' * (length - len(segment)))

            self.bits[offset : offset + length] = segment

    def generate_bitstream(self, fasm, output, args):
        self.parse_fasm(fasm)

        if isinstance(output, str):
            output = open(output, "w")

        # emit lines in quad words
        for i in reversed(range(self.qwords)):
            output.write('{:0>16x}'.format(struct.unpack('<Q', self.bits[i*64:(i + 1)*64].tobytes())[0]) + '\n')
