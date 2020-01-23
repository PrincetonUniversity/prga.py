# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.flow.context import ArchitectureContext
from prga.config.packetizedchain.algorithm.stats import ConfigPacketizedChainStatsAlgorithms as sa
from prga.util import enable_stdout_logging

from prga_tools.packetizedchain.util import packetizedchain_hop2ranges, packetizedchain_packetize

import re   # for the simple FASM, regexp processing is good enough
import struct
from bitarray import bitarray
import logging

__all__ = ['bitgen_packetizedchain']

_logger = logging.getLogger(__name__)
_reprog_param = re.compile("^b(?P<offset>\d+)\[(?P<high>\d+):(?P<low>\d+)\]=(?P<width>\d+)'b(?P<content>[01]+)$")

def bitgen_packetizedchain(context  # architecture context
        , istream                   # input file-like object
        , ostream                   # output file-like object
        ):
    """Generate bitstream for packetizedchain-styled configuration circuitry.

    Args:
        context (`ArchitectureContext`):
        istream (file-like object):
        ostream (file-like object):
    """
    config_width = context.config_circuitry_delegate.config_width
    hop2ranges = packetizedchain_hop2ranges(context)
    # Actual bitstream
    bitsgmts = [bitarray('0') * r for r in hop2ranges]
    # process features
    for lineno, line in enumerate(istream):
        segments = line.strip().split('.')
        if segments[-1] == 'ignored':
            continue
        hop, offset = 0, 0
        for sgmt in segments[:-1]:
            if sgmt[0] == 'h':
                hop += int(sgmt[1:])
            elif sgmt[0] == 'b':
                offset += int(sgmt[1:])
            else:
                raise RuntimeError("LINE {:>08d}: Unknown FASM feature: {}".format(lineno + 1, line.strip()))
        if '[' in segments[-1]:
            matched = _reprog_param.match(segments[-1])
            offset += int(matched.group('offset'))
            segment = bitarray(matched.group('content'), endian = 'little')
            segment.reverse()
            high, low, width = map(lambda x: int(matched.group(x)), ('high', 'low', 'width'))
            if high < low:
                raise RuntimeError("LINE {:>08d}: Invalid range specifier".format(lineno + 1))
            elif width != len(segment):
                raise RuntimeError("LINE {:>08d}: Explicit width specifier mismatches with number of bits"
                        .format(lineno + 1))
            actual_width = high - low + 1
            if actual_width > width:
                segment.extend((False, ) * (actual_width - width))
            bitsgmts[hop][offset + low: offset + low + actual_width] = segment[0: actual_width]
        else:
            bitsgmts[hop][offset + int(segments[-1][1:])] = True
    # assemble
    buf = bitarray(endian='big')        # this is the bit-endianness
    for hop, sgmt in enumerate(bitsgmts):
        # skip if no config data for a hop
        # if not sgmt.any():
        #     continue
        # reverse segment but add header first
        remainder = len(sgmt)
        hoc = bitarray()
        hoc.frombytes(bytes([0xC5, 0X7A, 0X86, 0X1E]))                  # hard-coded HOC magic number
        for hoc_head, effective_payload, hoc_tail in packetizedchain_packetize(remainder):
            # construct head
            header = bitarray(endian='big')
            header.frombytes(bytes([
                context.config_circuitry_delegate.magic_sop,    # Start of packet
                0x01 if hoc_tail else 0x00,                     # msg type (0x01: DATA_LAST, 0x00: DATA)
                ]))
            header.frombytes(struct.pack('>H', hop))
            header.frombytes(struct.pack('>H', effective_payload + (32 if hoc_head else 0) + (32 if hoc_tail else 0) - 1))
            for i in range(len(header) // config_width):
                buf = header[i * config_width : (i+1) * config_width] + buf
                if len(buf) == 64:
                    ostream.write('{:0>16x}'.format(struct.unpack('>Q', buf.tobytes())[0]) + '\n')
                    buf = bitarray(endian='big')
            if hoc_head:
                for i in reversed(range(32 // config_width)):
                    buf = bitarray(reversed(hoc[i * config_width : (i + 1) * config_width])) + buf
                    if len(buf) == 64:
                        ostream.write('{:0>16x}'.format(struct.unpack('>Q', buf.tobytes())[0]) + '\n')
                        buf = bitarray(endian='big')
            for _ in range(effective_payload // config_width):
                buf = bitarray(reversed(sgmt[remainder - config_width:remainder])) + buf
                if len(buf) == 64:
                    ostream.write('{:0>16x}'.format(struct.unpack('>Q', buf.tobytes())[0]) + '\n')
                    buf = bitarray(endian='big')
                remainder -= config_width
            if hoc_tail:
                for i in reversed(range(32 // config_width)):
                    buf = bitarray(reversed(hoc[i * config_width : (i + 1) * config_width])) + buf
                    if len(buf) == 64:
                        ostream.write('{:0>16x}'.format(struct.unpack('>Q', buf.tobytes())[0]) + '\n')
                        buf = bitarray(endian='big')
                break
    # add a end of programming packet
    header = bitarray(endian='big')
    header.frombytes(bytes([
        context.config_circuitry_delegate.magic_sop,    # Start of packet
        0xFF,                                           # msg type: End of programming
        ]))
    for i in range(len(header) // config_width):
        buf = header[i * config_width : (i+1) * config_width] + buf
        if len(buf) == 64:
            ostream.write('{:0>16x}'.format(struct.unpack('>Q', buf.tobytes())[0]) + '\n')
            buf = bitarray(endian='big')
    # align to 64bit
    if len(buf) > 0:
        if len(buf) != 64:
            buf = bitarray('0') * (64 - len(buf)) + buf
        ostream.write('{:0>16x}'.format(struct.unpack('>Q', buf.tobytes())[0]) + '\n')

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
            description="Bitstream generator for packetized-chain-style configuration circuitry")
    
    parser.add_argument('context', type=argparse.FileType(OpenMode.rb),
            help="Pickled architecture context object")
    parser.add_argument('fasm', type=argparse.FileType('r'),
            help="FASM generated by the genfasm util of VPR")
    parser.add_argument('memh', type=argparse.FileType('w'),
            help="Generated bitstream in MEMH format for Verilog simulation")

    args = parser.parse_args()
    enable_stdout_logging(__name__, logging.INFO)
    context = ArchitectureContext.unpickle(args.context)
    _logger.info("Architecture context parsed")
    _logger.info("Configuration chain width: {}"
            .format(context.config_circuitry_delegate.config_width))
    _logger.info("Total number of configuration bits: {}"
            .format(context.config_circuitry_delegate.total_config_bits))
    _logger.info("Total number of hops: {}"
            .format(context.config_circuitry_delegate.total_hopcount))
    bitgen_packetizedchain(context, args.fasm, args.memh)
    _logger.info("Bitstream generated. Bye")
