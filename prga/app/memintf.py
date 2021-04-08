# -*- encoding: ascii -*-

from ..util import Object

__all__ = ['MemIntf']

# ----------------------------------------------------------------------------
# -- Memory Interface Definition ---------------------------------------------
# ----------------------------------------------------------------------------
class MemIntf(Object):
    """Memory interface definition.

    Args:
        addr_width (:obj:`int`): Number of bits in the address.
        data_bytes_log2 (:obj:`int`): log2(number of bytes of the data bus)
        size_values (:obj:`Sequence` [:obj:`int` ]): value encoding for ``size`` field
        size_width (:obj:`int`): Number of bits of the ``size`` field
    """

    __slots__ = ["addr_width", "data_bytes_log2", "size_width", "size_values"]
    def __init__(self, addr_width, data_bytes_log2 = 3, size_values = None, size_width = None):
        self.addr_width = addr_width
        self.data_bytes_log2 = data_bytes_log2

        if size_width is None:
            if size_values is None:
                self.size_width = data_bytes_log2.bit_length()
            else:
                self.size_width = max(size_values).bit_length()

        if size_values is None:
            self.size_values = tuple(iter(range(data_bytes_log2 + 1)))
        else:
            self.size_values = tuple(iter(size_values))
