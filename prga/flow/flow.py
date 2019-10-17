# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import uno, Abstract, Object
from prga.exception import PRGAAPIError

from collections import OrderedDict
from abc import abstractproperty, abstractmethod
import networkx as nx
import time

import logging
_logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# -- Flow --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Flow(Object):
    """Flow manager of PRGA."""

    __slots__ = ['_passes', '_drop_cache_before_start', '_drop_cache_after_end']
    def __init__(self, passes = None,
            drop_cache_before_start = True,
            drop_cache_after_end = True):
        self._passes = list(iter(uno(passes, tuple())))
        self._drop_cache_before_start = drop_cache_before_start
        self._drop_cache_after_end = drop_cache_after_end

    def __key_is_prefix(self, key, other):
        """Check if ``key`` is a prefix of the ``other`` key.
        
        Args:
            key, other (:obj:`str`):
        """
        key, other = map(lambda x: x.split('.'), (key, other))
        if len(key) > len(other):
            return False
        for s, o in zip(key, other):
            if s != o:
                return False
        return True

    def __key_is_irrelevent(self, key, other):
        """Check if the two keys are irrelevent to each other."""
        return not self.__key_is_prefix(key, other) and not self.__key_is_prefix(other, key)

    def add_pass(self, pass_):
        """Add one pass to the flow.

        Args:
            pass_ (`AbstractPass`):
        """
        self._passes.append(pass_)

    def run(self, context):
        """Run the flow."""
        # 1. resolve dependences/conflicts
        passes = OrderedDict()
        while self._passes:
            updated = None
            for i, pass_ in enumerate(self._passes):
                # 1.1 is the exact same pass already run?
                if pass_.key in passes:
                    raise PRGAAPIError("Pass '{}' is added twice".format(pass_.key))
                # 1.2 is there any invalid pass keys?
                try:
                    duplicate = next(key for key in passes if not self.__key_is_irrelevent(pass_.key, key))
                    raise PRGAAPIError("Pass '{}' and '{}' are duplicate, or one is the sub-pass of another"
                            .format(duplicate, pass_.key))
                except StopIteration:
                    pass
                # 1.3 is any pass key in conflict with this key?
                try:
                    conflict = next(key for key in passes if any(self.__key_is_prefix(rule, key) for rule in pass_.conflicts))
                    raise PRGAAPIError("Pass '{}' conflicts with '{}'".format(conflict, pass_.key))
                except StopIteration:
                    pass
                # 1.4 are all the dependences satisfied?
                if all(any(self.__key_is_prefix(rule, key) for key in passes) for rule in pass_.dependences):
                    passes[pass_.key] = pass_
                    updated = i
                    break
            if updated is None:
                missing = {pass_.key: tuple(rule for rule in pass_.dependences
                    if all(not self.__key_is_prefix(rule, key) for key in passes))
                    for pass_ in self._passes}
                raise PRGAAPIError("Missing passes:" +
                        "\n\t".join(map(lambda kv: "{} required by {}".format(', '.join(kv[1]), kv[0]),
                            iteritems(missing))))
            else:
                del self._passes[i]
        passes = tuple(itervalues(passes))
        # 2. order passes
        # 2.1 build a graph
        g = nx.DiGraph()
        g.add_nodes_from(range(len(passes)))
        for i, pass_ in enumerate(passes):
            for j, other in enumerate(passes):
                if i == j:
                    continue
                if (any(self.__key_is_prefix(rule, other.key) for rule in pass_.passes_before_self) or
                        any(self.__key_is_prefix(rule, other.key) for rule in pass_.dependences)):
                    # ``other`` should be executed before ``pass_``
                    g.add_edge(j, i)
                if any(self.__key_is_prefix(rule, other.key) for rule in pass_.passes_after_self):
                    # ``other`` should be executed after ``pass_``
                    g.add_edge(i, j)
        try:
            passes = [passes[i] for i in nx.topological_sort(g)]
        except nx.exception.NetworkXUnfeasible:
            raise PRGAAPIError("Cannot determine a feasible order of the passes")
        # 3. run passes
        if self._drop_cache_before_start:
            context._cache = {}
        for pass_ in passes:
            _logger.info("running pass '%s'", pass_.key)
            t = time.time()
            pass_.run(context)
            # context._passes_applied.add(pass_.key)
            _logger.info("pass '%s' took %f seconds", pass_.key, time.time() - t)
        if self._drop_cache_after_end:
            context._cache = {}

# ----------------------------------------------------------------------------
# -- Abstract Pass -----------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractPass(Abstract):
    """A pass working on the architecture context."""

    @abstractproperty
    def key(self):
        """Key of this pass."""
        raise NotImplementedError

    @abstractmethod
    def run(self, context):
        """Run the pass.

        Args:
            context (`ArchitectureContext`): the context which holds all the internal data
        """
        pass

    @property
    def dependences(self):
        """Passes that this pass depend on."""
        return tuple()

    @property
    def conflicts(self):
        """Passes that should not be used with this pass."""
        return tuple()

    @property
    def passes_before_self(self):
        """Passes that should be executed before this pass."""
        return tuple()

    @property
    def passes_after_self(self):
        """Passes that should be executed after this pass."""
        return tuple()
