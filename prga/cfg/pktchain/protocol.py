# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...util import Enum
from ...exception import PRGAAPIError

__all__ = ["PktchainProtocol"]

class PktchainProtocol(object):

    # == Invariant protocol ==================================================
    # -- Programming packets -------------------------------------------------
    class Programming(object):
        class MSGType(Enum):
            # control packets
            SOB                         = 0x01  # start of bitstream
            EOB                         = 0x02  # end of bitstream
            TEST                        = 0x20
            # effective programming packets
            DATA                        = 0x40
            DATA_INIT                   = 0x41
            DATA_CHECKSUM               = 0x42
            DATA_INIT_CHECKSUM          = 0x43
            # responses
            DATA_ACK                    = 0x80
            ERROR_UNKNOWN_MSG_TYPE      = 0x81
            ERROR_ECHO_MISMATCH         = 0x82
            ERROR_CHECKSUM_MISMATCH     = 0x83
            ERROR_FEEDTHRU_PACKET       = 0x84

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
            return (type_ << 24) | (x << 16) | (y << 8) | payload

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

    # -- AXILite Controller Interface ----------------------------------------
    class AXILiteController(object):
        DATA_WIDTH_LOG2 = 6
        ADDR_WIDTH = 9
        USER_ADDR_WIDTH = 8
        USER_ADDR_PREFIX = 1
        USER_DATA_WIDTH_LOG2 = 5

        class ADDR(Enum):
            STATE           = 0x00 #: writing to this address triggers some state transition
            CONFIG          = 0x01 #: configuration flags
            ERR_FIFO        = 0x02 #: pop error fifo once at a time. Write clears the FIFO
            BITSTREAM_ID    = 0x08 #: ID of the current bitstream. Typically address of the bitstream
            BITSTREAM_FIFO  = 0x09 #: [WO] bitstream data fifo
            UCLK_DIV        = 0x10 #: user clock divisor (uclk = clk / 2 / (divisor + 1))
            UREG_TIMEOUT    = 0x11 #: user register timeout (in user clock cycles)
            URST            = 0x12 #: [WO] reset user application (and recover from previous timeout errors)
            UERR_FIFO       = 0x13 #: pop user error fifo once at a time. Write clears the FIFO

        class State(Enum):
            RESET               = 0x00 #: PRGA is just reset. Write this value to `STATE` to soft reset
            PROGRAMMING         = 0x01 #: Programming PRGA. Write this value to `STATE` to start programming
            PROG_STABILIZING    = 0x02 #: PRGA is programmed. Write this value to indicate end of bitstream
            PROG_ERR            = 0x03 #: An error occured during programming
            APP_READY           = 0x04 #: PRGA is programmed and the application is ready

        class Error(Enum):
            NONE                = 0x00 #: invalid error (default return value when err fifo is empty)
            PROTOCOL_VIOLATION  = 0x01 #: protocol violated. Violated address: [0 +: ADDR_WIDTH]
            INVAL_WR            = 0x02 #: invalid write. Violated address: [0 +: ADDR_WIDTH]
            INVAL_RD            = 0x03 #: invalid read. Violated address: [0 +: ADDR_WIDTH]
            BITSTREAM           = 0x04 #: bitstream error. Subtype: [-8 -: 8]
            PROG_RESP           = 0x05 #: programming error. Error message: [0 +: FRAME_SIZE(32)]
            UREG_WR             = 0x06 #: user register write error. UREG address: [0 +: USER_ADDR_WIDTH].
                                        #   {req_timeout, resp_timeout, bresp}: [USER_ADDR_WIDTH +: 4]

        class BitstreamError(Enum):
            EXPECTING_SOB           = 0x01 #: waiting for SOB packet but got something else
            UNEXPECTED_SOB          = 0x02 #: not expecting an SOB packet

            INVAL_RESP              = 0x03 #: invalid response
            ERR_RESP                = 0x04 #: erroneous response

            INVAL_PKT               = 0x05 #: invalid packet
            ERR_PKT                 = 0x06 #: erroneous packet

            INCOMPLETE_TILES        = 0x07 #: #tiles: [0 +: 2 * PRGA_PKTCHAIN_POS_WIDTH]
            ERROR_TILES             = 0x08 #: #tiles: [0 +: 2 * PRGA_PKTCHAIN_POS_WIDTH]

        @classmethod
        def decode_error(cls, e):
            raw_type = (e >> 56) & 0xff
            try:
                t = cls.Error(raw_type)
            except ValueError:
                raise PRGAAPIError("Unknown error type: {:r}".format(raw_type))
            if t.is_NONE:
                return {"type": t}
            elif t.is_PROTOCOL_VIOLATION or t.is_INVAL_WR or t.is_INVAL_RD:
                return {"type": t, "addr": e & ((1 << cls.ADDR_WIDTH) - 1)}
            elif t.is_BITSTREAM:
                raw_subtype = (e >> 48) & 0xff
                try:
                    sub_t = cls.BitstreamError(raw_subtype)
                except ValueError:
                    raise PRGAAPIError("Unknown bitstream sub-error type: {:r}".format(raw_subtype))
                if sub_t.is_INCOMPLETE_TILES or sub_t.is_ERROR_TILES:
                    return {"type": t, "subtype": sub_t, "n_tiles": e & 0xffff}
                elif (sub_t.is_EXPECTING_SOB or sub_t.is_UNEXPECTED_SOB or
                        sub_t.is_INVAL_RESP or sub_t.is_ERR_RESP or
                        sub_t.is_INVAL_PKT or sub_t.is_ERR_PKT):
                    return {"type": t, "subtype": sub_t, "packet": e & 0xffffffff}
                else:
                    raise NotImplementedError("Unknown bitstream sub-error type: {:r}".format(sub_t))
            elif t.is_PROG_RESP:
                return {"type": t, "packet": e & 0xffffffff}
            elif t.is_UREG_WR:
                return {"type": t, "addr": e & ((1 << cls.USER_ADDR_WIDTH) - 1),
                        "resp": e & ((1 << (cls.USER_ADDR_WIDTH + 2)) - (1 << (cls.USER_ADDR_WIDTH))),
                        "resp_timeout": bool(e & (1 << (cls.USER_ADDR_WIDTH + 2))),
                        "req_timeout": bool(e & (1 << (cls.USER_ADDR_WIDTH + 3))),}
            else:
                raise NotImplementedError("Unknown error type: {:r}".format(t))
