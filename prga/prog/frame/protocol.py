# -*- encoding: ascii -*-

from ...util import Enum

__all__ = ["FrameProtocol"]

class FrameProtocol(object):

    # == Invariant protocol ==================================================
    # -- Programming instructions --------------------------------------------
    class Programming(object):
        """Bitstream composed of sequence of instructions. Each instruction is 4-byte long, big endian. The most
        significant byte is composed of a 4-bit op code, 3 odd parity bits, one for each of the 3 remaining bytes,
        and an additional odd parity bit for the 7 bits mentioned above.

        .. code::

             31    28    27       26       25       24    23    16 15     8 7      0
            +--------+--------+--------+--------+--------+--------+--------+--------+
            |        | parity | parity | parity | parity | byte 2 | byte 1 | byte 0 |
            | opcode |  for   |  for   |  for   |  for   +--------+--------+--------+
            |        | byte 2 | byte 1 | byte 0 | 31:25  |         argument         |
            +--------+--------+--------+--------+--------+--------+--------+--------+

        Instructions:
        - ``SOB``: Start of bitstream. Argument is a magic number: 0xC4816D
        - ``EOB``: End of bitstream. Argument is a magic number: 0xDABA47
        - ``JR``: Jump relative to the current address.
        - ``JAL``: Jump to an absolute address, only modifying the Lower 24 bits. NOT "JUMP-AND-LINK" XD
        - ``JAH``: Jump to an absolute address, only modifying the Higher 24 bits
        - ``JAE``: Jump to an absolute address, only modifying the Extended 24 bits, 71:48. Reserved for Extremely large
          FPGAs
        - ``DATA``: Start of a data segment. The argument is the number of "words" following the instruction, MINUS 1.
          i.e. ``0`` means 1 word, ``15`` means 16 words. The actual payload is aligned to 32-bit boundary
        - ``READ``: Read back a set amount of words. The argument is the number of "words" to read, MINUS 1
        - ``CKSWRL``: Write the Lower 24 bits of the checksum
        - ``CKSWRH``: Write the Higher 24 bits of the checksum
        - ``CKSWRE``: Write the Extended 24 bits, 71:48 of the checksum
        - ``CKSRDL``: Read the Lower 24 bits of the checksum
        - ``CKSRDH``: Read the Higher 24 bits of the checksum
        - ``CKSRDE``: Read the Extended 24 bits , 71:48 of the checksum
        """

        class MSGType(Enum):

            # control instructions
            NOP     = 0x0   # no-op
            SOB     = 0x1   # start of bitstream
            EOB     = 0x2   # end of bitstream

            # address change
            JR      = 0xC
            JAL     = 0xD
            JAH     = 0xE
            JAE     = 0xF

            # data instructions
            DATA    = 0x4
            READ    = 0x8

            # checksum instructions
            CKSWRL  = 0x5
            CKSWRH  = 0x6
            CKSWRE  = 0x7
            CKSRDL  = 0x9
            CKSRDH  = 0xA
            CKSRDE  = 0xB

        class MAGIC(Enum):

            NOP     = 0x000000
            SOB     = 0xC4816D
            EOB     = 0xDABA47
