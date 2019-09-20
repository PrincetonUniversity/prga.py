# -*- encoding: ascii -*-
# mypy: ignore-errors
"""Stuff for Python 2.7+ and 3.3+ compatibility."""

from __future__ import division, absolute_import, print_function

import sys

if ((sys.version_info > (3, ) and sys.version_info < (3, 3)) or
        (sys.version_info > (2, ) and sys.version_info < (2, 7))):
    raise RuntimeError("Python 2.7+ or 3.3+ is required to run PRGA")

from future.utils import with_metaclass, raise_from, iteritems, itervalues, string_types
from future.builtins import object, range

try:
    from itertools import imap as map, ifilter as filter, izip as zip
except ImportError:
    pass

try:
    from collections.abc import Sequence, MutableSequence, Mapping, MutableMapping, Hashable
except ImportError:
    from collections import Sequence, MutableSequence, Mapping, MutableMapping, Hashable

try:
    from io import BytesIO as StringIO
except ImportError:
    try:
        from cStringIO import StringIO
    except ImportError:
        from StringIO import StringIO

class OpenMode(object):
    def __new__(cls):
        raise RuntimeError("Cannot instantiate '{}'".format(cls.__name__))

    r = "rb" if sys.version_info > (3, ) else "r"
    w = "wb" if sys.version_info > (3, ) else "w"
