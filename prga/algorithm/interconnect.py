# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Algorithms for building interconnects."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from itertools import product, count, cycle, islice
from bitarray.util import zeros

__all__ = ["InterconnectAlgorithms"]

# ----------------------------------------------------------------------------
# -- Interconnect-Related Algorithms -----------------------------------------
# ----------------------------------------------------------------------------
class InterconnectAlgorithms(object):
    """Wrapper class for all interconnect-related algorithms."""

    @classmethod
    def crossbar(cls, N, M, connectivity, *, n_util = None):
        """Generate ``(n, m)`` pairs so that each ``m`` is paired with ``connectivity`` ``n``s. The goal is
        that each ``n`` is paired with about the same number of ``m``s \(fairness\), while each ``m`` is paired
        with a different composition of ``n``s \(diversity\).

        Args:
            N (:obj:`int`):
            M (:obj:`int`):
            connectivity (:obj:`int`):

        Keyword Args:
            n_util (:obj:`Sequence` [:obj:`int` ]): carry-over state

        Yields:
            :obj:`tuple` (:obj:`int`, :obj:`int`):
        """
        # special cases
        if connectivity == 0:
            return
        elif connectivity >= N:
            for p in product(range(N), range(M)):
                yield p
            return
        # general cases
        period_step = 1 / float(connectivity)

        # utilization of elements in N 
        n_util = n_util or [0 for _ in range(N)]

        # period & phase combo search iterator
        ppit = cycle(product(reversed(range(N - connectivity + 1)), range(N)))

        # for each element in M
        for m in range(M):
            unassigned_left = sum(1 if util == 0 else 0 for util in n_util)

            # if the number of unused tracks happens to be equal to the tracks needed, we don't need to search
            #   ATTENTION: this might affect our period-phase search.e.g. when N = 4, connectivity = 2, we would
            #       expect the pattern to be alternating between 1010 and 0101. But if this short path is enabled, we
            #       would get 1010, 0101, 0101, 1010, 1010 instead
            # if unassigned_left == connectivity:
            #     # apply pattern
            #     for n in range(len(n_util)):
            #         if n_util[n] > 0:
            #             n_util[n] -= 1
            #         else:
            #             yield n, m
            #     continue

            # search the best phase & period combo that maximizes the utilization of previously unused elements in N
            pat, max_unassigned = None, 0
            unassigned_left = min(unassigned_left, connectivity)

            for period, phase in islice(ppit, (N - connectivity + 1) * N):
                pat_tmp = zeros(N)
                period_f = 1 + period * period_step

                fails = 0
                for i in count(phase):
                    idx = round(i * period_f) % N
                    if pat_tmp[idx]:
                        fails += 1
                        if fails == N:
                            break
                    else:
                        pat_tmp[idx] = True
                        if pat_tmp.count() == connectivity:
                            break

                unassigned = sum(1 if n_util[i] == 0 and pat_tmp[i] else 0 for i in range(N))
                if unassigned > max_unassigned:
                    pat, max_unassigned = pat_tmp, unassigned
                    if max_unassigned == unassigned_left:
                        break

            # apply pattern
            for n, flag in enumerate(pat):
                if flag:
                    yield n, m
                    n_util[n] += 1

            # update n_util
            while all(n_util):
                for n in range(len(n_util)):
                    n_util[n] -= 1
