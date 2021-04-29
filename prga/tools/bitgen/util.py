# -*- encoding: ascii -*-

from ...util import uno, Object
from ...exception import PRGAInternalError

from bitarray import bitarray
from bitarray.util import zeros, int2ba

__all__ = ['BitstreamSegmentTree', 'CRC']

# ----------------------------------------------------------------------------
# -- Bitstream Segment Tree --------------------------------------------------
# ----------------------------------------------------------------------------
class BitstreamSegmentTree(Object):
    """A red-black tree for managing large-sized, sparse bitstream data.

    Args:
        min_gap (:obj:`int`): Minimum gap between segments. Two segments are merged when the distance between them is
            smaller than this gap

    Algorithmic properties:

    1. [BST] The tree itself is a binary search tree. Data type and ordering defined in property #6.
    2. [RBT:color-palette] Each node is either red or black.
    3. [RBT:black-balance] Each path from root to leaf contains the same number of black nodes.
    4. [RBT:red-isolation] Each parent-child pair cannot be both red.
    5. [Segment] Each node [NOT just leaf nodes!] contains a bitstream segment with an offset, e.g. ``8'hA5 @ [3:11]``.
        This data type is ordered by the range, i.e. ``[0:2] < [3:11]``. Overlapping nodes must be merged, i.e.
        ``[0:4]`` and ``[3:11]`` cannot co-exist in the tree.
    """

    class _Node(object):

        __slots__ = [
                # bit range
                "interval",

                # data
                "data",

                # red-black tree metadata
                "children", "parent", "is_black"]

        L = 0
        R = 1

        def __init__(self, low, high, data,
                parent = None, is_black = False):

            self.data = data
            self.parent = parent
            self.is_black = is_black

            self.interval = [low, high]
            self.children = [None, None]

        def __repr__(self):
            return "BSRBTNode[{}]:{}@{{{}:{}}}".format(
                    "B" if self.is_black else "R", self.data, self.low, self.high)

        # coloring information
        @property
        def is_red(self):
            return not self.is_black

        @is_red.setter
        def is_red(self, v):
            self.is_black = not v

        # range
        @property
        def low(self):
            return self.interval[self.L]

        @low.setter
        def low(self, v):
            self.interval[self.L] = v

        @property
        def high(self):
            return self.interval[self.R]

        @high.setter
        def high(self, v):
            self.interval[self.R] = v

        # node properties
        @property
        def is_root(self):
            return self.parent is None

        @property
        def is_leaf(self):
            return not any(self.children)

        @property
        def is_left(self):
            return self.parent is not None and self is self.parent.left

        @property
        def is_right(self):
            return self.parent is not None and self is self.parent.right

        @property
        def side(self):
            assert self.parent is not None
            return self.parent.children.index(self)

        # children
        @property
        def left(self):
            return self.children[self.L]

        @left.setter
        def left(self, v):
            self.children[self.L] = v

        @property
        def right(self):
            return self.children[self.R]

        @right.setter
        def right(self, v):
            self.children[self.R] = v

        # related nodes
        @property
        def sibling(self):
            if self.parent is None:
                return None
            elif self is self.parent.left:
                return self.parent.right
            else:
                return self.parent.left

        @property
        def grandparent(self):
            if self.parent is None:
                return None
            else:
                return self.parent.parent

        @property
        def uncle(self):
            if self.parent is None:
                return None
            else:
                return self.parent.sibling

        @property
        def close_nephew(self):
            if self.sibling is None:
                return None
            return self.sibling.children[self.side]

        @property
        def distant_nephew(self):
            if self.sibling is None:
                return None
            return self.sibling.children[1 - self.side]

    __slots__ = ["root", "_min_gap"]

    def __init__(self, min_gap = 0):
        self.root = None
        self._min_gap = min_gap

    @classmethod
    def __successor(cls, n):
        """Find the immediate successor of ``n``."""
        if n.right is None:
            if n.parent is None or n.side == cls._Node.R:
                return None
            else:
                return n.parent

        l, p = n.right.left, n.right
        while l:
            l, p = l.left, l

        return p

    @classmethod
    def __predecessor(cls, n):
        """Find the immediate predecessor of ``n``."""
        if n.left is None:
            if n.parent is None or n.side == cls._Node.L:
                return None
            else:
                return n.parent

        r, p = n.left.right, n.left
        while r:
            r, p = r.right, r

        return p

    def __rotate(self, n):
        """Rotate ``n`` and its parent.

        Args:
            n (`BitstreamSegmentTree._Node`): Child node to be rotated

        Notes:
            Property 3-5 may be violated after the rotation.

        Returns:
            `BitstreamSegmentTree._Node`: The old parent of ``n``, i.e. ``p`` in the figure below

        An example \(left rotate\)::

                 g                  g
                  \\                 \\
                   p                 [n]
                  / \\      ==>      / \\
                 s  [n]             p   r
                    / \\           / \\
                   l   r          s   l
        """
        # key parent-child pair
        p = n.parent
        assert p is not None

        # rotate direction
        side = n.side

        # connect l to p
        l = p.children[side] = n.children[1 - side]
        if l is not None: l.parent = p

        # connect n to g
        g = n.parent = p.parent
        if g is not None: g.children[p.side] = n

        # connect p to n
        n.children[1 - side] = p
        p.parent = n

        # update root
        if p is self.root:
            self.root = n

        return p

    def __insert(self, n, p, side):
        """Insert ``n`` as the ``side``-child of ``p``.

        Args:
            n (`BitstreamSegmentTree._Node`): Node to be inserted
            p (`BitstreamSegmentTree._Node`): Parent node
            side (``0`` or ``1``): ``0`` for left, ``1`` for right
        """
        p.children[side] = n
        n.parent = p

        g, u = p.parent, p.sibling
        while p:
            if p.is_black:
                break

            elif g is None:
                p.is_black = True
                break

            elif u is None or u.is_black:
                if n.side != p.side:
                    self.__rotate(n)
                    n, p = p, n

                self.__rotate(p)
                p.is_black = g.is_red = True
                break

            else:
                p.is_black = u.is_black = True
                g.is_red = True
                n, p, g, u = g, g.parent, g.grandparent, g.uncle

    def __postremoval_fix(self, p, side, r = None):
        """Fix red/black coloring after removing black ``side``-child of ``p``.

        Args:
            p (`BitstreamSegmentTree._Node`): Parent node
            side (``0`` or ``1``): ``0`` for left, ``1`` for right
            r (`BitstreamSegmentTree._Node`): Reference node. If specified, this method returns ``True`` if the
                reference node is rotated, either as the parent or the child in a rotation

        Returns:
            :obj:`bool`: Returns ``True`` if ``r`` is moved during the fix.
        """
        s = p.children[1-side]
        c, d = s.children[side], s.children[1-side]
        moved = False

        case = 0
        while True:
            if s.is_red:                        # red S
                case = 1
                break
            elif d is not None and d.is_red:    # black S, red D
                case = 4
                break
            elif c is not None and c.is_red:    # black S/D, red C
                case = 3
                break
            elif p.is_red:                      # black S/D/C, red P
                case = 2
                break
            else:                               # S/D/C/P are all black!
                s.is_red = True

                if p.parent:
                    p, s, c, d, side = p.parent, p.sibling, p.close_nephew, p.distant_nephew, p.side
                else:
                    break

        if case == 0:            # reached root
            return moved

        if case == 1:            # red S => black P/C/D
            moved = (r in (s, self.__rotate(s))) or moved
            p.is_red = s.is_black = True
            s = c               # after transformation, red P, black S
            if (d := s.children[1-side]) and d.is_red:  # red P/D, black S
                case = 4
            elif (c := s.children[side]) and c.is_red:  # red P/C, black S/D
                case = 3
            else:
                case = 2

        if case == 2:           # red P, black S/C/D
            s.is_red = p.is_black = True
            return moved

        if case == 3:           # red P/C, black S/D
            moved = (r in (c, self.__rotate(c))) or moved
            s.is_red = c.is_black = True
            d = s
            s = c

        # final case: red P/D, black S/C
        moved = (r in (s, self.__rotate(s))) or moved
        s.is_black = p.is_black
        p.is_black = d.is_black = True

        return moved

    @classmethod
    def __mergedata(cls, n, c, side):
        """Merge the data of two nodes, ``n`` and ``c``.

        Args:
            n (`BitstreamSegmentTree._Node`): Node that remains after the merge
            c (`BitstreamSegmentTree._Node`): Node to be merged
            side (``0`` or ``1``): ``0`` for left, ``1`` for right
        """
        if side == cls._Node.L:
            n.data = c.data + zeros(n.low - c.high, endian = 'little') + n.data
        else:
            n.data = n.data + zeros(c.low - n.high, endian = 'little') + c.data

        n.interval[side] = c.interval[side]

    @classmethod
    def __merge(cls, n, side):
        """Merge the ``side``-child of ``n`` into ``n``.

        Args:
            n (`BitstreamSegmentTree._Node`):
            side (``0`` or ``1``):

        Returns:
            `BitstreamSegmentTree._Node`: ``n``
        """
        if (c := n.children[side]) is None:
            return n

        cls.__merge(c, cls._Node.L)
        cls.__merge(c, cls._Node.R)
        cls.__mergedata(n, c, side)
        n.children[side] = None

        return n

    def set_data(self, low, high, data):
        """Set ``data`` to the specified interval.

        Args:
            low (:obj:`int`):
            high (:obj:`int`):
            data (`bitarray`_): Little-endian, ``high - low`` -bits bitarray.

        .. _bitarray: https://pypi.org/project/bitarray/
        """
        if self.root is None:
            self.root = self._Node(low, high, data)
            return

        # Adding interval might cause merges, and the post-removal fixes might change tree structure, so we have to do
        # it in a loop
        while True:
            r, p, side = self.root, None, None

            while r:
                if high + self._min_gap < r.low:
                    r, p, side = r.left, r, self._Node.L

                elif r.high + self._min_gap < low:
                    r, p, side = r.right, r, self._Node.R

                else:
                    break

            if r is None:
                self.__insert(self._Node(low, high, data), p, side)
                return

            # ``r`` is out temporary root now, possibly need to merge subtree
            # for quickly get out of the nested loop, use try-except
            try:
                for d in (self._Node.L, self._Node.R):
                    c, p = r.children[d], r

                    while c:
                        if ( (d == self._Node.L and c.high + self._min_gap < low) or
                                (d == self._Node.R and c.low - self._min_gap > high) ) :
                            c, p = c.children[1 - d], c

                        else:
                            # merge the subtree of c
                            self.__merge(c, 1 - d)

                            # update r
                            self.__mergedata(r, c, d)

                            # connect c.child (at most one remaining) to c.parent (p)
                            side = c.side
                            l = p.children[side] = c.children[d]
                            if l is not None: l.parent = p

                            # fix color
                            if c.is_red:
                                # removing a red node is always harmless
                                pass

                            elif l is not None and l.is_red:
                                # promote ``l` from red to black, compensating the loss of ``c``
                                l.is_black = True

                            elif self.__postremoval_fix(p, side, r):
                                # ``r`` is moved after the fix. we need to restart the search from root
                                raise StopIteration     # jump out of the for-while nested loops

                            # terminate if we've covered the interval
                            if ( (d == self._Node.L and r.low + self._min_gap <= low) or
                                    (d == self._Node.R and r.high - self._min_gap >= high) ):
                                break

                            # continue the while loop
                            c, p = l, p

            except StopIteration:
                continue

            # done merging
            # set data
            lower, upper = min(r.low, low), max(r.high, high)
            newdata = zeros(upper - lower, endian = 'little')
            newdata[r.low - lower : r.high - lower] = r.data
            newdata[low - lower : high - lower] = data
            r.data = newdata
            r.interval = [lower, upper]
            return

    def itertree(self, *, r = None):
        """Iterate the tree.

        Yields:
            :obj:`int`: low
            :obj:`int`: high
            `bitarray`_: Little-endian, ``high - low`` -bits bitarray.

        .. _bitarray: https://pypi.org/project/bitarray/
        """
        r = uno(r, self.root)

        if r is None:
            return

        if r.left:
            for i in self.itertree(r = r.left):
                yield i

        yield r.low, r.high, r.data

        if r.right:
            for i in self.itertree(r = r.right):
                yield i

    @property
    def min_gap(self):
        """:obj:`int`: Minimum gap between segments. Two segments are merged when the distance between them is
        smaller than this gap."""
        return self._min_gap

# ----------------------------------------------------------------------------
# -- Cyclic Redundant Code (CRC) Calculator ----------------------------------
# ----------------------------------------------------------------------------
class CRC(Object):
    """A CRC-8 CCITT CRC calculator.

    Args:
        lanes (:obj:`int`): Number of lanes
    """

    __slots__ = ['crc']
    _mask = bitarray('11100000', endian='little')

    def __init__(self, lanes = 1):
        self.crc = list(bitarray('00000000', endian='little') for _ in range(lanes))

    @property
    def lanes(self):
        """:obj:`int`: Number of lanes in this calculator."""
        return len(self.crc)

    def reset(self):
        """Reset the current state."""
        self.crc = list(bitarray('00000000', endian='little') for _ in range(self.lanes))

    def consume(self, v):
        """Consume a `CRC.lanes`-bit value and update the current state.

        Args:
            v (`bitarray`_): A `CRC.lanes`-bit value

        .. _bitarray: https://pypi.org/project/bitarray/
        """
        for i, b in enumerate(v):
            # shift by 1
            self.crc[i] >>= 1

            # inverse under specific conditions
            if self.crc[i][-1] != b:
                self.crc[i] ^= self._mask
