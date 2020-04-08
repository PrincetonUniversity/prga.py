# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..util import Abstract

from abc import abstractproperty, abstractmethod

__all__ = ['AbstractPass']

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
            context (`Context`): The context which manages all architecture data
        """
        raise NotImplementedError

    @property
    def is_readonly_pass(self):
        """:obj:`bool`: Test if this is a read-only pass that can be run multiple times."""
        return False

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
