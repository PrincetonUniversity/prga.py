# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator
from ...exception import PRGAInternalError
from ...util import uno

from bitarray import bitarray, frozenbitarray
from bitarray.util import int2ba

__all__ = ['FrameBitstreamGenerator']

class FrameBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'frame' programming circuitry."""

    __slots__ = ["bits", "word_size"]

    class _FrameDataTreeNode(object):

        __slots__ = [
                # data only for the current node
                "addr_low", "addr_high", "data",

                # data for the subtree
                "addr_min", "addr_max",

                # tree metadata
                "left", "right", "parent"]

        _zero = bitarray('0', endian='little')

        def __init__(self, addr_low, addr_high, data,
                addr_min = None, addr_max = None,
                left = None, right = None, parent = None):

            self.addr_low = addr_low
            self.addr_high = addr_high
            self.data = data    # little-endian bitarray
            self.addr_min = uno(addr_min, addr_low)
            self.addr_max = uno(addr_max, addr_high)
            self.left = left
            self.right = right
            self.parent = parent

        @classmethod
        def itertree(cls, root):
            if root is None:
                return

            for x in cls.itertree(root.left):
                yield x

            yield root

            for x in cls.itertree(root.right):
                yield x

        @classmethod
        def _rotate_left(cls, node):
            assert node.right is not None

            new = node.right
            node.right = new.left
            if node.right is not None:
                node.addr_max = node.right.addr_max
                node.right.parent = node
            else:
                node.addr_max = node.addr_high

            new.left = node
            node.parent = new
            new.addr_min = node.addr_min

            return new

        @classmethod
        def _rotate_right(cls, node):
            assert node.left is not None

            new = node.left
            node.left = new.right
            if node.left is not None:
                node.addr_min = node.left.addr_min
                node.left.parent = node
            else:
                node.addr_min = node.addr_low

            new.right = node
            node.parent = new
            new.addr_max = node.addr_max

            return new

        @classmethod
        def _merge_subtree(cls, word_size, node):
            if node.left is not None:
                cls._merge_subtree(word_size, node.left)
                cls._merge_left(word_size, node)

            if node.right is not None:
                cls._merge_subtree(word_size, node.right)
                cls._merge_right(word_size, node)

        @classmethod
        def _merge_left(cls, word_size, node):
            assert node.left is not None
            assert node.left.right is None

            node.data = (node.left.data
                    + cls._zero * (word_size * (node.addr_low - node.left.addr_low) - len(node.left.data))
                    + node.data)
            node.addr_low = node.left.addr_low
            node.left = node.left.left
            if node.left is not None:
                node.left.parent = node

        @classmethod
        def _merge_right(cls, word_size, node):
            assert node.right is not None
            assert node.right.left is None

            node.data = (node.data
                    + cls._zero * (word_size * (node.right.addr_low - node.addr_low) - len(node.data))
                    + node.right.data)
            node.addr_high = node.right.addr_high
            node.right = node.right.right
            if node.right is not None:
                node.right.parent = node

        @classmethod
        def set_(cls, root, word_size, addr_low, data, bitoffset):
            bitrem = (bitoffset + len(data)) % word_size
            if bitrem > 0:
                bitrem = word_size - bitrem

            addr_high = (addr_low
                    + (bitoffset + len(data)) // word_size
                    + (1 if bitrem else 0))

            if root is None:
                return cls(addr_low, addr_high, cls._zero * bitoffset + data + cls._zero * bitrem)

            cur = root
            while True:
                # case 1. strict left
                if addr_high < cur.addr_low:
                    if cur.left is None:
                        new = cls(addr_low, addr_high,
                                cls._zero * bitoffset + data + cls._zero * bitrem,
                                parent = cur)
                        cur.left = new
                        cur.addr_min = addr_low

                        break
                    else:
                        cur = cur.left
                        continue

                # case 2. strict right
                if addr_low > cur.addr_high:
                    if cur.right is None:
                        new = cls(addr_low, addr_high,
                                cls._zero * bitoffset + data + cls._zero * bitrem,
                                parent = cur)
                        cur.right = new
                        cur.addr_max = addr_high

                        break
                    else:
                        cur = cur.right
                        continue

                intersect_left  = cur.left  is not None and addr_low  <= cur.left.addr_max
                intersect_right = cur.right is not None and addr_high >= cur.right.addr_min

                # case 3. challenging: nodes-merging is possible
                if intersect_left:
                    # rotate
                    left = cur.left
                    while True:
                        if addr_low < left.addr_low:
                            if left.left is None:
                                break
                            else:
                                left = cls._rotate_right(left)
                                cur.left, left.parent = left, cur
                        elif addr_low > left.addr_high:
                            if left.right is None:
                                break
                            else:
                                left = cls._rotate_left(left)
                                cur.left, left.parent = left, cur
                        else:
                            break

                    # merge the right subtree of ``left`` into it
                    if left.right is not None:
                        cls._merge_subtree(word_size, left.right)
                        cls._merge_right(word_size, left)

                    # merge ``left`` into ``cur``
                    cls._merge_left(word_size, cur)

                if intersect_right:
                    # rotate
                    right = cur.right
                    while True:
                        if addr_high > right.addr_high:
                            if right.right is None:
                                break
                            else:
                                right = cls._rotate_left(right)
                                cur.right, right.parent = right, cur
                        elif addr_high < right.addr_low:
                            if right.left is None:
                                break
                            else:
                                right = cls._rotate_right(right)
                                cur.right, right.parent = right, cur
                        else:
                            break

                    # merge the left subtree of ``right`` into it
                    if right.left is not None:
                        cls._merge_subtree(word_size, right.left)
                        cls._merge_left(word_size, right)

                    # merge ``right`` into ``cur``
                    cls._merge_right(word_size, cur)

                # safe data update
                if addr_low < cur.addr_low:
                    cur.data = cls._zero * (cur.addr_low - addr_low) * word_size + cur.data
                    cur.addr_low = min(cur.addr_low, addr_low)
                    cur.addr_min = min(cur.addr_low, cur.addr_min)
                else:
                    bitoffset += word_size * (addr_low - cur.addr_low)

                if addr_high > cur.addr_high:
                    cur.data = cur.data + cls._zero * (addr_high - cur.addr_high) * word_size
                    cur.addr_high = max(cur.addr_high, addr_high)
                    cur.addr_max = max(cur.addr_high, cur.addr_max)

                cur.data[bitoffset : bitoffset + len(data)] = data

                break

            # update ancestors?
            while (cur.parent is not None
                    and (cur.parent.addr_min > cur.addr_min or cur.parent.addr_max < cur.addr_max)):
                cur.parent.addr_min = min(cur.parent.addr_min, cur.addr_min)
                cur.parent.addr_max = max(cur.parent.addr_max, cur.addr_max)
                cur = cur.parent

            return root

        @classmethod
        def print_(cls, root, p = print):
            row = [ [root], [] ]
            while any(row[0]):
                row[1] = row[0]
                row[0] = []

                s = []
                for n in row[1]:
                    if n is None:
                        s.append('nil')
                        row[0].extend( (None, None) )
                    else:
                        s.append('{{{}{}:{}{}}}'.format(
                            "{}-".format(n.addr_min) if n.addr_min < n.addr_low else '',
                            n.addr_low, n.addr_high,
                            "-{}".format(n.addr_max) if n.addr_max > n.addr_high else ''))
                        row[0].extend( (n.left, n.right) )
                p(', '.join(s))

    def __init__(self, context):
        super().__init__(context)

        self.bits = [[{ "block": [], "cbox": [], "sbox": [] }
            for y in range(context.top.height)]
            for x in range(context.top.width)]
        self.word_size = context.summary.frame["word_size"]

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
