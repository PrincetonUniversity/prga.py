# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from itertools import product
import math

__all__ = ["InterconnectAlgorithms"]

# ----------------------------------------------------------------------------
# -- Interconnect-Related Algorithms -----------------------------------------
# ----------------------------------------------------------------------------
class InterconnectAlgorithms(object):
    """Wrapper class for all interconnect-related algorithms."""

    @classmethod
    def crossbar(cls, N, M, connectivity, *, n_selected = None):
        """Generate ``(n, m)`` pairs so that each ``m`` is paired with ``connectivity`` ``n``s. The goal is
        that each ``n`` is paired with about the same number of ``m``s \(fairness\), while each ``m`` is paired
        with a different composition of ``n``s \(diversity\).

        Args:
            N (:obj:`int`):
            M (:obj:`int`):
            connectivity (:obj:`int`):

        Keyword Args:
            n_selected (:obj:`Sequence` [:obj:`int` ]): carry-over state
        """
        # special cases
        if connectivity == 0:
            return
        elif connectivity >= N:
            for p in product(range(N), range(M)):
                yield p
            return
        # general cases
        step = float(N) / float(connectivity)
        n_selected = n_selected or ([0] * N)

        for m in range(M):
            offset = 0
            max_unassigned = 0

            for i in range(0, int(step)):
                if ((unassigned := sum(1 if n_selected[int(i + j * step) % N] == 0 else 0 for j in
                    range(connectivity))) > max_unassigned):
                    offset = i
                    max_unassigned = unassigned

            for j in range(connectivity):
                n = int(offset + j * step) % N
                yield n, m
                n_selected[n] += 1

            while all(n_selected):
                for n in range(len(n_selected)):
                    n_selected[n] -= 1
