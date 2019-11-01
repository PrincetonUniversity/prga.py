# -*- encoding: ascii -*-
# mypy: ignore-errors
"""Stuff for Python 2.7+ and 3.3+ compatibility."""

from __future__ import division, absolute_import, print_function

import sys as _sys, os as _os, errno as _errno

if ((_sys.version_info > (3, ) and _sys.version_info < (3, 3)) or
        (_sys.version_info > (2, ) and _sys.version_info < (2, 7))):
    raise RuntimeError("Python 2.7+ or 3.3+ is required to run PRGA")

from future.utils import with_metaclass, raise_from, iteritems, itervalues, string_types
from future.builtins import object, range

try:
    from itertools import imap as map, ifilter as filter, izip as zip
except ImportError:
    pass

try:
    from collections.abc import Sequence, MutableSequence, Mapping, MutableMapping, Hashable, Iterable
except ImportError:
    from collections import Sequence, MutableSequence, Mapping, MutableMapping, Hashable, Iterable

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

    rb = "rb" if _sys.version_info > (3, ) else "r"
    wb = "wb" if _sys.version_info > (3, ) else "w"
    ab = "ab" if _sys.version_info > (3, ) else "a"
    abc = "ab+" if _sys.version_info > (3, ) else "a+"

if _sys.version_info >= (3, 2):
    def makedirs(directory):
        return _os.makedirs(directory, exist_ok=True)
else:
    def makedirs(directory):
        try:
            return _os.makedirs(directory)
        except OSError as e:
            if e.errno != _errno.EEXIST:
                raise
