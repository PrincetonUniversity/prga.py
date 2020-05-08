# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...util import Enum
from ...exception import PRGAAPIError

__all__ = ["PktchainProtocol"]

class PktchainProtocol(object):

    class MSGType(Enum):
        MSG_TYPE_DATA                       = 0x10
        MSG_TYPE_DATA_INIT                  = 0x11
        MSG_TYPE_DATA_CHECKSUM              = 0x12
        MSG_TYPE_DATA_INIT_CHECKSUM         = 0x13
        MSG_TYPE_DATA_ACK                   = 0x14
        MSG_TYPE_TEST                       = 0x20
        MSG_TYPE_ERROR_UNKNOWN_MSG_TYPE     = 0x80
        MSG_TYPE_ERROR_ECHO_MISMATCH        = 0x81
        MSG_TYPE_ERROR_CHECKSUM_MISMATCH    = 0x82

    @classmethod
    def encode_msg_header(cls, type_, x, y, payload):
        if not isinstance(type_, cls.MSGType):
            raise PRGAAPIError("Unknown message type: {:r}".format(type_))
        elif not 0 <= x < (1 << 8):
            raise PRGAAPIError("X position ({}) can not be represented with 8 bits".format(x))
        elif not 0 <= y < (1 << 8):
            raise PRGAAPIError("Y position ({}) can not be represented with 8 bits".format(y))
        elif not 0 <= payload < (1 << 8):
            raise PRGAAPIError("Payload ({}) can not be represented with 8 bits".format(payload))
        return (type_ << 24) | (x << 16) | (y << 16) | payload

    @classmethod
    def decode_msg_header(cls, frame):
        raw_type = (frame >> 24) & 0xff
        x = (frame >> 16) & 0xff
        y = (frame >> 8) & 0xff
        payload = frame & 0xff
        try:
            type_ = cls.MSGType(raw_type)
        except ValueError:
            raise PRGAAPIError("Unknown message type: {:r}".format(raw_type))
        return type_, x, y, payload

    class AXILiteAddr(Enum):
        PRGA_CREG_ADDR_STATE                = 0x00 #: writing to this address triggers some state transition
        PRGA_CREG_ADDR_CONFIG               = 0x01 #: configuration flags
        PRGA_CREG_ADDR_ERR_COUNT            = 0x02 #: number of errors captured. writing ANY value clears all errors
        PRGA_CREG_ADDR_ERR_FIFO             = 0x03 #: [RO] pop error fifo once at a time. Only valid if ERR_COUNT > 0
        PRGA_CREG_ADDR_BITSTREAM_ID         = 0x08 #: ID of the current bitstream. Typically address of the bitstream
        PRGA_CREG_ADDR_BITSTREAM_FIFO       = 0x09 #: [WO] bitstream data fifo

    class AXILiteState(Enum):
        PRGA_STATE_RESET                    = 0x00 #: PRGA is just reset. Write this value to `STATE` to soft reset
        PRGA_STATE_PROGRAMMING              = 0x01 #: Programming PRGA. Write this value to `STATE` to start programming
        PRGA_STATE_PROG_STABILIZING         = 0x02 #: PRGA is programmed. Write this value to indicate end of bitstream
        PRGA_STATE_PROG_ERR                 = 0x03 #: An error occured during programming
        PRGA_STATE_APP_READY                = 0x04 #: PRGA is programmed and the application is ready

    class AXILiteError(Enum):
        PRGA_ERR_PROTOCOL_VIOLATION         = 0x01 #: protocol violated. Violated address: [0 +: ADDR_WIDTH]
        PRGA_ERR_INVAL_WR                   = 0x02 #: invalid write. Violated address: [0 +: ADDR_WIDTH]
        PRGA_ERR_INVAL_RD                   = 0x03 #: invalid read. Violated address: [0 +: ADDR_WIDTH]
        PRGA_ERR_BITSTREAM                  = 0x04 #: bitstream error. Subtype: [-8 -: 8]
        PRGA_ERR_PROG_RESP                  = 0x05 #: programming error. Error message: [0 +: FRAME_SIZE(32)]

    class AXILiteBitstreamError(Enum):
        PRGA_ERR_BITSTREAM_SUBTYPE_INVAL_HEADER         = 0x00
        PRGA_ERR_BITSTREAM_SUBTYPE_UNINITIALIZED_TILE   = 0x01
        PRGA_ERR_BITSTREAM_SUBTYPE_COMPLETED_TILE       = 0x02
        PRGA_ERR_BITSTREAM_SUBTYPE_REINITIALIZING_TILE  = 0x03
        PRGA_ERR_BITSTREAM_SUBTYPE_INCOMPLETE_TILES     = 0x04 #: #tiles: [8 +: 16]
        PRGA_ERR_BITSTREAM_SUBTYPE_ERROR_TILES          = 0x05 #: #tiles: [8 +: 16]

    UserRegAddrWidth = 8
    UserRegDataWidth = 64
