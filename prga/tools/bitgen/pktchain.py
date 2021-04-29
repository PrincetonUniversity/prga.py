# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator
from ...exception import PRGAInternalError

from bitarray import bitarray
from itertools import product, count
import struct

class PktchainBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'pktchain' programming circuitry."""

    __slots__ = ["bits"]

    def __init__(self, context):
        super().__init__(context)

        self.bits = [[bitarray('0', endian="little") * leaf
            for leaf in branch] for branch in context.summary.pktchain["fabric"]["branches"]]

    _none = object()
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
        # check pre-built CRC lookup table
        try:
            return cls._reversed_crc_lookup[crc]
        except KeyError:
            raise PRGAInternalError("No prefix checksum found for CRC-8 CCITT value 0x{:08x} prepended with {} zeros"
                    .format(crc, zeros))

    def set_bits(self, value, hierarchy = None, inplace = False):
        branch, leaf = 0, 0

        if hierarchy:
            for i in hierarchy.hierarchy:
                if (bitmap := getattr(i, "scanchain_bitmap", self._none)) is self._none:
                    bitmap = getattr(i, "prog_bitmap", self._none)

                if bitmap is None:
                    return

                elif bitmap is not self._none:
                    value = value.remap(bitmap, inplace = inplace)
                    inplace = True

                if (branchmap := getattr(i, "pktchain_branchmap", None)) is not None:
                    branch, leaf_inc = branchmap[branch]
                    leaf += leaf_inc

        for v, (offset, length) in value.breakdown():
            segment = bitarray(bin(v)[2:])
            segment.reverse()
            if length > len(segment):
                segment.extend('0' * (length - len(segment)))

            self.bits[branch][leaf][offset : offset + length] = segment

    def generate_bitstream(self, fasm, output, args):
        self.parse_fasm(fasm)

        # add CRC
        chain_width = self.context.summary.scanchain["chain_width"]
        for branch in self.bits:
            for leaf_id, leaf_bs in enumerate(branch):
                if len(leaf_bs) == 0:
                    continue

                # generate checksum
                crc = [self.crc(iter(b for i, b in enumerate(reversed(leaf_bs)) if i % (chain_width) == idx))
                        for idx in reversed(range(chain_width))]
                reversed_crc = [self.reverse_crc(c, len(leaf_bs) // chain_width) for c in crc]
                checksum = bitarray(endian="little")

                # fill checksum
                for digit, idx in product(range(8), range(chain_width)):
                    checksum.append(bool(reversed_crc[idx] & (1 << digit)))

                # prepend & append checksum
                fullstream = checksum + leaf_bs + checksum

                # align to 32bit (frame size) boundaries
                if len(fullstream) % 32 != 0:
                    remainder = 32 - len(fullstream) % 32
                    fullstream += bitarray("0", endian="little") * remainder

                branch[leaf_id] = fullstream

        # dump the bitstream (or more precisely, the "packet" stream)
        if isinstance(output, str):
            output = open(output, "w")

        fabric = self.context.summary.pktchain["fabric"]
        protocol = self.context.summary.pktchain["protocol"]
        max_packet_frames = min(256, (2 ** fabric["router_fifo_depth_log2"]) // (32 // fabric["phit_width"])) - 1
        for pkt in count():
            completed = True
            for leaf_id, branch_id in product(reversed(range(len(self.bits[0]))), reversed(range(len(self.bits)))):
                bitstream = self.bits[branch_id][leaf_id]
                if not any(bitstream):
                    continue
                total_frames = len(bitstream) // 32
                if pkt * max_packet_frames >= total_frames:
                    continue
                init = pkt == 0
                checksum = (pkt + 1) * max_packet_frames >= total_frames
                completed = completed and checksum
                msg_type = (protocol.Programming.MSGType.DATA_INIT_CHECKSUM if init and checksum else
                        protocol.Programming.MSGType.DATA_INIT if init and not checksum else
                        protocol.Programming.MSGType.DATA_CHECKSUM if not init and checksum else
                        protocol.Programming.MSGType.DATA)
                payload = min(max_packet_frames, total_frames - pkt * max_packet_frames)
                output.write("// {} packet to ({}, {}), {} frames\n"
                        .format(msg_type.name, branch_id, leaf_id, payload))
                output.write("{:0>8x}\n"
                        .format(protocol.Programming.encode_msg_header(msg_type, branch_id, leaf_id, payload)))
                for i in range(payload):
                    i = total_frames - pkt * max_packet_frames - 1 - i
                    output.write("{:0>8x}\n".format(
                        struct.unpack("<L", bitstream[i*32:(i + 1)*32].tobytes())[0]))
                output.write("\n")
            if completed:
                break

PktchainBitstreamGenerator._reversed_crc_lookup = {
        PktchainBitstreamGenerator.crc(PktchainBitstreamGenerator._int2bitseq(i)): i
        for i in range(256)}
