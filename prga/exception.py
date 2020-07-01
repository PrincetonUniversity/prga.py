# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""PRGA's exception and error types."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

__all__ = ["PRGAInternalError", "PRGAAPIError", "PRGATypeError", "PRGAIndexError"]

class PRGAInternalError(RuntimeError):
    '''Critical internal error within PRGA flow.

    As an API user, you should never see this type of exception. If you get such an error, please email
    angl@princeton.edu with a detailed description and an example to repeat this error. We thank you for help
    developing PRGA!
    '''
    pass

class PRGAAPIError(PRGAInternalError):
    """An error of an API misuse.

    This error is thrown when the API is not used correctly.
    """
    pass

class PRGATypeError(TypeError):
    """A PRGA-specific type error."""

    def __init__(self, arg, type_, msg = None):
        self.arg = arg
        self.type_ = type_
        self.msg = msg

    def __str__(self):
        return "PRGATypeError: Invalid argument '{}', expecting {}.{}".format(self.arg, self.type_,
                '' if self.msg is None else (' ' + self.msg))

class PRGAIndexError(IndexError):
    """A PRGA-specific index error."""
    pass
