# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator
from ...prog.common import ProgDataBitmap
from ...exception import PRGAAPIError

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

    _none = object()

    def _set_bits(self, value, hierarchy = None, inplace = False):
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

    def generate_bitstream(self, fasm, output):
        if isinstance(fasm, str):
            fasm = open(fasm, "r")

        for lineno, line in enumerate(fasm, 1):

            feature = self.parse_feature(line)

            if feature.type_ == "conn":
                if (prog_enable := getattr(feature.conn, "prog_enable", self._none)) is self._none:
                    for net in getattr(feature.conn, "switch_path", tuple()):
                        bus, idx = (net.bus, net.index) if net.net_type.is_bit else (net, 0)
                        self._set_bits(bus.instance.model.prog_enable[idx],
                                bus.instance._extend_hierarchy(above = feature.hierarchy))

                elif prog_enable is None:
                    continue

                else:
                    self._set_bits(prog_enable, feature.hierarchy)

            elif feature.type_ == "param":
                leaf = feature.hierarchy.hierarchy[0]

                if (parameters := getattr(leaf, "prog_parameters", self._none)) is self._none:
                    if (parameters := getattr(leaf.model, "prog_parameters", self._none)) is self._none:
                        continue

                if parameters is None or (bitmap := parameters.get(feature.parameter)) is None:
                    continue

                feature.value.remap(bitmap, inplace = True)
                self._set_bits(feature.value, feature.hierarchy, True)

            elif feature.type_ == "plain" and feature.feature == "+":
                leaf = feature.hierarchy.hierarchy[0]

                prog_enable = None
                if (feature.module.module_class.is_mode
                        or (prog_enable := getattr(leaf, "prog_enable", self._none)) is self._none):
                    prog_enable = getattr(feature.module, "prog_enable", None)

                if prog_enable is None:
                    continue

                self._set_bits(prog_enable, feature.hierarchy)

            else:
                _logger.warning("[Line {:0>4d}] Unsupported feature: {}".format(lineno, line.strip()))

        if isinstance(output, str):
            output = open(output, "w")

        # emit lines in quad words
        for i in reversed(range(self.qwords)):
            output.write('{:0>16x}'.format(struct.unpack('<Q', self.bits[i*64:(i + 1)*64].tobytes())[0]) + '\n')
