# -*- encoding: ascii -*-

from ..util import Object, uno
from ..exception import PRGAInternalError, PRGAAPIError

import networkx as nx
import time

import logging
_logger = logging.getLogger(__name__)

__all__ = ["Flow"]

# ----------------------------------------------------------------------------
# -- Flow --------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Flow(Object):
    """Flow manager of PRGA.
    
    Args:
        *args: Passes
    """

    __slots__ = ["_passes"]
    def __init__(self, *passes):
        self._passes = list(iter(passes))

    def __key_is_prefix(self, key, other):
        """Check if ``key`` is a prefix of ``other``.

        Args:
            key (:obj:`str`): Dot-separated key list
            other (:obj:`str`): Dot-separated key list
        
        Returns:
            :obj:`bool`:
        """
        key, other = map(lambda x: x.split('.'), (key, other))
        if len(key) > len(other):
            return False
        for s, o in zip(key, other):
            if s != o:
                return False
        return True

    def __key_is_irrelevent(self, key, other):
        """Check if ``key`` and ``other`` are not prefix of each other.

        Args:
            key (:obj:`str`): Dot-separated key list
            other (:obj:`str`): Dot-separated key list
        
        Returns:
            :obj:`bool`:
        """
        return not (self.__key_is_prefix(key, other) or self.__key_is_prefix(other, key))

    def add_pass(self, pass_):
        """Add one pass to the flow.

        Args:
            pass_ (`AbstractPass`):
        """
        self._passes.append( pass_ )

    def run(self, context):
        """Run all added passes on ``context``.

        Args:
            context (`Context`):
        """
        if not hasattr(context, "_applied_passes"):
            context._applied_passes = set()
        # 1. resolve dependences/conflicts
        passes = {}
        while self._passes:
            updated = None
            for i, pass_ in enumerate(self._passes):
                if not pass_.is_readonly_pass:
                    # 1.1 is the pass added twice?
                    if pass_.key in passes:
                        raise PRGAAPIError("Pass {} is added twice".format(pass_.key))
                    # 1.2 is the pass already executed?
                    if pass_.key in context._applied_passes:
                        raise PRGAAPIError("Pass {} is already applied to the context".format(pass_.key))
                    # 1.3 any duplicates? 
                    try:
                        duplicate = next(key for key in passes if not self.__key_is_irrelevent(pass_.key, key))
                        raise PRGAAPIError("Pass {} and {} conflict with each other".format(pass_.key, key))
                    except StopIteration:
                        pass
                    try:
                        duplicate = next(key for key in context._applied_passes
                                if not self.__key_is_irrelevent(pass_.key, key))
                        raise PRGAAPIError("Pass {} and {} conflict with each other".format(pass_.key, key))
                    except StopIteration:
                        pass
                # 1.3 any conflicts?
                try:
                    conflict = next(key for key in passes if any(self.__key_is_prefix(rule, key)
                        for rule in pass_.conflicts))
                    raise PRGAAPIError("Pass {} and {} conflict with each other".format(pass_.key, key))
                except StopIteration:
                    pass
                try:
                    conflict = next(key for key in context._applied_passes if any(self.__key_is_prefix(rule, key)
                        for rule in pass_.conflicts))
                    raise PRGAAPIError("Pass {} and {} conflict with each other".format(pass_.key, key))
                except StopIteration:
                    pass
                # 1.4 are all dependences satisfied?
                if all(any(self.__key_is_prefix(rule, key) for key in passes) or
                        any(self.__key_is_prefix(rule, key) for key in context._applied_passes)
                        for rule in pass_.dependences):
                    passes[pass_.key] = pass_
                    updated = i
                    break
            if updated is None:
                missing = {pass_.key: tuple(rule for rule in pass_.dependences
                        if all (not self.__key_is_prefix(rule, key) for key in passes))
                        for pass_ in self._passes}
                raise PRGAAPIError("Missing dependent passes:\n\t" +
                        "\n\t".join(map(lambda kv: "'{}' required by '{}'".format(", ".join(kv[2]), kv[0]),
                            missing.items())))
            else:
                del self._passes[i]
        passes = tuple(passes.values())
        # 2. determine the correct order
        g = nx.DiGraph()
        g.add_nodes_from(range(len(passes)))
        for i, pass_ in enumerate(passes):
            for j, other in enumerate(passes):
                if i == j:
                    continue
                if (any(self.__key_is_prefix(rule, other.key) for rule in pass_.passes_before_self) or
                        any(self.__key_is_prefix(rule, other.key) for rule in pass_.dependences)):
                    # ``other`` must be executed before ``pass_``
                    g.add_edge(j, i)
                if any(self.__key_is_prefix(rule, other.key) for rule in pass_.passes_after_self):
                    # ``other`` cannot be executed before ``pass_``
                    g.add_edge(i, j)
        # sort
        try:
            passes = [passes[i] for i in nx.topological_sort(g)]
        except nx.exception.NetworkXUnfeasible:
            raise PRGAAPIError("Cannot determine a feasible order of the passes")
        # 3. run passes
        for pass_ in passes:
            _logger.info("********************")
            _logger.info("running pass '%s'", pass_.key)
            t = time.time()
            pass_.run(context, context.renderer)
            _logger.info("pass '%s' took %f seconds", pass_.key, time.time() - t)
            context._applied_passes.add(pass_.key)
        # 4. render all files
        context.renderer.render()
