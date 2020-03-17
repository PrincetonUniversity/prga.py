# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .exception import PRGAInternalError, PRGAIndexError

from abc import ABCMeta
import enum
import logging
import sys

__all__ = ["ReadonlyMappingProxy", "ReadonlySequenceProxy", "uno", "Abstract", "Object", "Enum",
        'compose_slice', 'enable_stdout_logging']

class ReadonlyMappingProxy(Mapping):
    """A read-only proxy of a :obj:`Mapping` implementation object.

    Args:
        m (:obj:`Mapping`): The :obj:`Mapping` object to be proxied
        filter_ (``lambda (key, value) -> bool``, default=None): An optional filter which filters the :obj:`Mapping`
            items
        cast (``lambda (key) -> key``, default=None): An optional key caster to cast a key in this proxy to a key in
            the proxied mapping
        uncast (``lambda (key) -> key``, default=None): An optional key caster to cast a key in the proxied maping to
            a key in this proxy

    A read-only proxy of a :obj:`Mapping` object. All read-only methods of :obj:`Mapping` are implemented while all
    mutating methods are removed.
    """
    __slots__ = ['m', 'filter_', 'cast', 'uncast']
    def __init__(self, m, filter_=None, cast=None, uncast=None):
        self.m = m              #: the :obj:`Mapping` object to be proxied
        self.filter_ = filter_   #: an optional filter which filters the :obj:`Mapping` items
        self.cast = cast
        self.uncast = uncast

    def __len__(self):
        """Return the number of items in the filtered mapping."""
        if self.filter_ is None:
            return len(self.m)
        else:
            return sum(1 for _ in filter(self.filter_, iteritems(self.m)))

    def __getitem__(self, key):
        """Return the item with key *key* in the proxy.
        
        Args:
            key:

        Raises:
            `KeyError`: Raised if *key* is not in the proxy.
        """
        casted = self.cast(key) if callable(self.cast) else key
        try:
            value = self.m[casted]
        except KeyError:
            raise KeyError(key)
        if self.filter_ is not None and not self.filter_((casted, value)):
            raise KeyError(key)
        else:
            return value

    def __iter__(self):
        """Return an iterator over the keys of the filtered mapping."""
        if callable(self.uncast):
            for k in (filter(self.filter_, iteritems(self.m)) if callable(self.filter_) else iter(self.m)):
                yield self.uncast(k)
        else:
            for k in (filter(self.filter_, iteritems(self.m)) if callable(self.filter_) else iter(self.m)):
                yield k

class ReadonlySequenceProxy(Sequence):
    """A read-only proxy of a :obj:`Sequence` object.

    Args:
        s (:obj:`Sequence`): The :obj:`Sequence` object to be proxied
    """
    __slots__ = ['s']
    def __init__(self, s):
        self.s = s              #: the :obj:`Sequence` object to be proxied

    def __len__(self):
        return len(self.s)

    def __getitem__(self, index):
        return self.s[index]

def uno(*args):
    """Return the first non- None value of the arguments

    Args:
        *args: Variable positional arguments

    Returns:
        The first non-``None`` value or None

    """
    try:
        return next(filter(lambda x: x is not None, args))
    except StopIteration:
        return None

class _InheritDocstringsMeta(ABCMeta):
    """Manually inherit docstrings from superclass. This helps Sphinx for doc generation."""
    def __new__(cls, clsname, bases, attributes):
        dummy = super(_InheritDocstringsMeta, cls).__new__(cls, '_dummy', bases, {})
        for name, attr in iteritems(attributes):
            if isinstance(attr, property) and attr.fget.__doc__ is None:
                superproperty = getattr(dummy, name, None)
                if superproperty is not None:
                    try:
                        attr.fget.__doc__ = superproperty.fget.__doc__
                    except AttributeError:
                        pass
            elif callable(attr):
                if attr.__doc__ is None:
                    try:
                        attr.__doc__ = getattr(dummy, name, None).__doc__
                    except AttributeError:
                        pass
        return super(_InheritDocstringsMeta, cls).__new__(cls, clsname, bases, attributes)

class Abstract(with_metaclass(_InheritDocstringsMeta, object)):
    """Base class for all PRGA abstracts."""
    pass

class _ForceSlotsMeta(_InheritDocstringsMeta):
    """Force __slots__ magic."""
    def __new__(cls, name, bases, attributes):
        attributes.setdefault('__slots__', tuple())
        return super(_ForceSlotsMeta, cls).__new__(cls, name, bases, attributes)

class Object(with_metaclass(_ForceSlotsMeta, object)):
    """Base class for all PRGA objects.
    
    This base class forces usage of slots magic to save memory usage as well as prevent silent errors caused by the
    dynamicity of Python. Dynamicity can be added back by inheriting a class and put ``__dict__`` back to the
    ``__slots__`` list."""
    pass

class Enum(enum.IntEnum):
    """``IntEnum`` enhanced with auto-generated test methods and a few other helpful methods.

    For example:
        >>> class MyEnum(Enum):
        ...     foo = 0
        ...     global_ = 1
        >>> MyEnum.foo.is_foo
        True
        >>> MyEnum.foo.is_global_
        False
        >>> MyEnum.global_.is_global
        True

    Notes:
        If any of the enum values has a trailing underscore, you may omit the trailing underscore
    """
    def __getattr__(self, attr):
        if not attr.startswith('is_'):
            raise AttributeError(attr)
        v = attr[3:]
        try:
            return self is type(self)[v]
        except KeyError:
            try:
                if not v.endswith('_'):
                    return self is type(self)[v + '_']
            except KeyError:
                raise AttributeError(attr)

    def case(self, *args, **kwargs):
        """Use this enum as a variable in a switch-case clause.
        
        Note that ``default`` is a reserved keyword. If set, the value will be used if no matching case specified.
        """
        try:
            return args[self.value]
        except IndexError:
            try:
                return kwargs[self.name]
            except KeyError:
                try:
                    return kwargs['default']
                except KeyError:
                    raise PRGAInternalError("Value unspecified for case {}".format(self))

def enable_stdout_logging(name, level=logging.INFO, verbose=False):
    hdl = logging.StreamHandler(sys.stdout)
    if verbose:
        hdl.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
    else:
        hdl.setFormatter(logging.Formatter('[%(levelname)s] %(message)s'))
    logger = logging.getLogger(name)
    logger.addHandler(hdl)
    logger.setLevel(level)

def _rotation(i, l):
    if i >= 0:
        return i
    else:
        return i + l

def compose_slice(src, dst):
    """``None``, :obj:`int` or :obj:`slice`: Apply :obj:`int` or :obj:`slice` ``dst`` on :obj:`int` or :obj:`slice`
    ``src``.  If any argument is :obj:`slice`, its ``step`` is ignored and treated as ``1``."""
    # calculate source length
    length = 1 if isinstance(src, int) else max(0, src.stop - src.start)
    # fix up dst
    if isinstance(dst, int):
        dst = _rotation(dst, length)
    else:
        dst = slice(_rotation(uno(dst.start, 0), length),
                _rotation(uno(dst.stop, length), length))
    if isinstance(src, int):
        if isinstance(dst, int) and dst == 0:
            return src
        elif isinstance(dst, slice) and dst.start <= 0 < dst.stop:
            return src
        else:
            raise PRGAIndexError("Index out of range")
    else:
        if isinstance(dst, int):
            if 0 <= dst < length:
                return src.start + dst
            else:
                raise PRGAIndexError("Index out of range")
        else:
            start = max(0, dst.start)
            stop = min(length, dst.stop)
            if stop <= start:
                return None
            elif stop == start + 1:
                return src.start + start
            else:
                return slice(src.start + start, src.start + stop)
