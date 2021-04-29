# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator
from .util import BitstreamSegmentTree, CRC
from ...exception import PRGAInternalError
from ...util import uno

from bitarray.util import int2ba, zeros, ba2hex, parity
from struct import unpack
from itertools import chain, repeat

__all__ = ['FrameBitstreamGenerator']

class FrameBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'frame' Programming circuitry."""

    __slots__ = ["bst", "output",
            "offset_x", "offset_y",
            "offset_subblock_id", "offset_cbox_id", "offset_sbox_id",
            "cbox_base", "sbox_base", "block_base",
            "word_size", "protocol",
            ]

    def __init__(self, context):
        super().__init__(context)

        self.bst = None
        self.output = None

        self.offset_y           = context.summary.frame["addr_width"]["tile"]
        self.offset_x           = self.offset_y + context.summary.frame["addr_width"]["y"]
        self.offset_subblock_id = context.summary.frame["addr_width"]["block"]
        self.offset_cbox_id     = context.summary.frame["addr_width"]["cbox"]
        self.offset_sbox_id     = context.summary.frame["addr_width"]["sbox"]
        self.sbox_base          = 0
        self.cbox_base          = 3 << (self.offset_y - 2)
        self.block_base         = 2 << (self.offset_y - 2)
        self.word_size          = context.summary.frame["word_width"]
        self.protocol           = context.summary.frame["protocol"]

    def _emit_inst(self, opcode, argument = None):
        """Emit an instruction.

        Args:
            opcode (`FrameProtocol.Programming.MSGType`):
            argument (:obj:`int`):
        """
        if opcode.is_NOP:
            argument = int2ba( self.protocol.Programming.MAGIC.NOP, length = 24, endian = 'big' )
        elif opcode.is_SOB:
            argument = int2ba( self.protocol.Programming.MAGIC.SOB, length = 24, endian = 'big' )
        elif opcode.is_EOB:
            argument = int2ba( self.protocol.Programming.MAGIC.EOB, length = 24, endian = 'big' )
        elif argument is None:
            raise PRGAInternalError("Argument cannot be empty for instruction type {}"
                    .format(opcode.name))
        elif opcode.is_JR:
            argument = int2ba( argument, length = 24, endian = 'big', signed = True )
        else:
            argument = int2ba( argument, length = 24, endian = 'big' )

        inst = int2ba( opcode << 4, length = 8, endian = 'big' ) + argument
        inst[4] = parity(inst[ 8:16])
        inst[5] = parity(inst[16:24])
        inst[6] = parity(inst[24:32])
        inst[7] = parity(inst[ 0: 7])

        self.output.write(ba2hex(inst) + " // {}, 0x{:0>6s}\n".format(opcode.name, ba2hex(argument)))

    def set_bits(self, value, hierarchy = None, *, inplace = False):
        x, y, type_, id_, baseaddr = 0, 0, None, 0, 0

        if hierarchy:
            for i in hierarchy.hierarchy:
                # bitmap?
                if (bitmap := getattr(i, "frame_bitmap", self._none)) is self._none:
                    bitmap = getattr(i, "prog_bitmap", self._none)

                if bitmap is None:
                    return

                elif bitmap is not self._none:
                    value = value.remap(bitmap, inplace = inplace)
                    inplace = True

                # baseaddr?
                if baseaddr_inc := getattr(i, "frame_baseaddr", None):
                    baseaddr += baseaddr_inc

                # hierarchy adjustments
                if i.model.module_class.is_block:
                    type_, id_ = "block", i.key

                elif i.model.module_class.is_connection_box:
                    type_, id_ = "cbox", i.frame_id

                elif i.model.module_class.is_switch_box:
                    type_, id_ = "sbox", i.frame_id
                    x += i.key[0][0]
                    y += i.key[0][1]

                elif i.model.module_class.is_tile or i.model.module_class.is_array:
                    x += i.key[0]
                    y += i.key[1]

        addr = (x << self.offset_x) + (y << self.offset_y) + baseaddr
        if type_ == "block":
            addr += self.block_base + (id_ << self.offset_subblock_id)
        elif type_ == "sbox":
            addr += self.sbox_base + (id_ << self.offset_sbox_id)
        elif type_ == "cbox":
            addr += self.cbox_base + (id_ << self.offset_cbox_id)
        else:
            raise PRGAInternalError("Unknown module type: {}".format(type_))
        addr *= self.word_size

        for v, (offset, length) in value.breakdown():
            segment = int2ba(v, length = length, endian = 'little')
            self.bst.set_data(addr + offset, addr + offset + length, segment)

    def generate_bitstream(self, fasm, output, args):
        # use margin `32 + self.word_size` to avoid aligned overwrite
        self.bst = BitstreamSegmentTree(32 + self.word_size)
        self.parse_fasm(fasm)

        if isinstance(output, str):
            output = open(output, 'w')
        self.output = output

        # a few header comments
        self.output.write("// Frame-based bitstream\n// Word size: {}\n"
                .format(self.word_size) )

        # emit an SOB instruction
        self._emit_inst(self.protocol.Programming.MSGType.SOB)
        self.output.write('\n')
        addr = 0

        # # initialize CRC
        # crc = CRC(self.word_size)
        # word_cnt = 0

        # output data
        for offset, high, data in self.bst.itertree():
            self.output.write("// Write bits {}:{}\n".format(high - 1, offset))
            baseaddr = offset // self.word_size

            # jump?
            if (diff := baseaddr - addr) != 0 and -(1 << 23) <= diff < (1 << 23):
                self._emit_inst(self.protocol.Programming.MSGType.JR, diff)
            else:
                if (baseaddr & (0xFFFFFF << 48)) != (addr & (0xFFFFFF << 48)):
                    self._emit_inst(self.protocol.Programming.MSGType.JAE, baseaddr >> 48)
                if (arg := baseaddr & (0xFFFFFF << 24)) != (addr & (0xFFFFFF << 24)):
                    self._emit_inst(self.protocol.Programming.MSGType.JAH, arg >> 24)
                if (arg := baseaddr & 0xFFFFFF) != (addr & 0xFFFFFF):
                    self._emit_inst(self.protocol.Programming.MSGType.JAL, arg)

            # align to word size
            if rem := offset % self.word_size:
                data = zeros(rem, endian='little') + data

            if rem := len(data) % self.word_size:
                data = data + zeros(self.word_size - rem, endian='little')

            # emit "data" instruction
            self._emit_inst(self.protocol.Programming.MSGType.DATA, len(data) // self.word_size - 1)

            # emit data
            for i in range(0, len(data), 32):
                d = data[i:i+32]
                d += zeros(32 - len(d), endian='little')
                self.output.write('{:0>8x}\n'.format(unpack('<L', d.tobytes())[0]))

            addr = baseaddr + len(data) // self.word_size
            self.output.write("\n")

        # output EOB
        self._emit_inst(self.protocol.Programming.MSGType.EOB)
