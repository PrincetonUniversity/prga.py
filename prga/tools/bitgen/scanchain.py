# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator
from ...exception import PRGAAPIError

from bitarray import bitarray
import struct

class ScanchainBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'scanchain' programming circuitry."""

    def generate_verif(self, summary, fasm, output):
        # process arguments
        if isinstance(fasm, str):
            fasm = open(fasm, "r")

        if isinstance(output, str):
            output = open(output, "w")

        bitstream_size = summary.scanchain["bitstream_size"]

        # initialize bitstream
        qwords = bitstream_size // 64
        remainder = bitstream_size % 64 
        if remainder > 0:
            qwords += 1
        bits = bitarray('0', endian='little') * (qwords * 64)

        # process features
        for lineno, line in enumerate(fasm, 1):
            prefixes, value = self.parse_feature(line)
            if prefixes:
                raise PRGAAPIError("[LINE {:>06d}]: Unexpected prefix '{}'"
                        .format(lineno, ".".join(prefixes)))

            # apply value
            for v, (offset, length) in value.breakdown():
                segment = bitarray(bin(v)[2:])
                segment.reverse()
                if length > len(segment):
                    segment.extend('0' * (length - len(segment)))

                bits[offset : offset + length] = segment

        # emit lines in quad words
        for i in reversed(range(qwords)):
            output.write('{:0>16x}'.format(struct.unpack('<Q', bits[i*64:(i + 1)*64].tobytes())[0]) + '\n')
