# -*- encoding: ascii -*-

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
