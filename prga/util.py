# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.exception import PRGAInternalError

from abc import ABCMeta
import enum

__all__ = ["ReadonlyMappingProxy", "ReadonlySequenceProxy", "uno", "Abstract", "Object", "Enum"]

class ReadonlyMappingProxy(Mapping):
    """A read-only proxy of a :obj:`Mapping` implementation object.

    Args:
        m (:obj:`Mapping`): The :obj:`Mapping` object to be proxied
        filter_ (``lambda (key, value) -> bool``, default=None): An optional filter which filters the :obj:`Mapping`
            items

    A read-only proxy of a :obj:`Mapping` object. All read-only methods of :obj:`Mapping` are implemented while all
    mutating methods are removed.
    """
    __slots__ = ['m', 'filter_']
    def __init__(self, m, filter_=None):
        self.m = m              #: the :obj:`Mapping` object to be proxied
        self.filter_ = filter_   #: an optional filter which filters the :obj:`Mapping` items

    def __len__(self):
        """Return the number of items in the filtered mapping."""
        if self.filter_ is None:
            return len(self.m)
        else:
            return sum(1 for _ in filter(self.filter_, iteritems(self.m)))

    def __getitem__(self, key):
        """Return the item with key *key* in the filtered mapping.
        
        Args:
            key:

        Raises:
            `KeyError`: Raised if *key* is not in the filtered mapping.
        """
        try:
            value = self.m[key]
        except KeyError:
            raise KeyError(key)
        if self.filter_ is not None and not self.filter_((key, value)):
            raise KeyError(key)
        else:
            return value

    def __iter__(self):
        """Return an iterator over the keys of the filtered mapping."""
        if self.filter_ is None:
            return iter(self.m)
        else:
            return iter(k for k, _ in filter(self.filter_, iteritems(self.m)))

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

    def switch(self, **kwargs):
        """Use this enum as a variable in a switch clause."""
        try:
            return kwargs[self.name]
        except KeyError:
            raise PRGAInternalError("Value unspecified for case {}".format(self))
