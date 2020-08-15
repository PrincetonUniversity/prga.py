# -*- encoding: ascii -*-
# Python 2 and 3 compatible
"""Netlist modules."""

from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..net.bus import Port
from ...util import ReadonlyMappingProxy, uno, Enum
from ...exception import PRGAInternalError

from enum import IntFlag

# In Python 3.7 and above, ``dict`` preserves insertion order and is more performant than ``OrderedDict``
OrderedDict = dict

__all__ = ['Module']

# ----------------------------------------------------------------------------
# -- Module ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Module(object):
    """A netlist module.

    Args:
        name (:obj:`str`): Name of the module

    Keyword Args:
        key (:obj:`Hashable`): A hashable key used to index this module in the database. If not set \(default
            argument: ``None``\), ``name`` is used by default
        is_cell (:obj:`bool`): If set to ``True``, this module is created as a cell module. A cell module does not
            contain information about connections. It contains information about timing arcs instead. A cell module
            may still contain sub-instances, but they are only used for tracking the hierarchy. When set, this
            argument overrides ``allow_multisource`` to ``True`` and ``coalesce_connections`` to ``False``.
        allow_multisource (:obj:`bool`): If set to ``True``, a sink net may be driven by multiple source nets.
            Incompatible with ``coalesce_connections``
        coalesce_connections (:obj:`bool`): If set to ``True``, bit-wise connections are not allowed.
            Incompatible with ``allow_multisource``.
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes
    """

    __slots__ = ["_name", "_key", "_children", "_ports", "_instances", "_flags", "__dict__"]

    class __FLAGS(IntFlag):
        NONE = 0
        IS_CELL = 1 << 0
        ALLOW_MULTISOURCE = 1 << 1
        COALESCE_CONNECTIONS = 1 << 2

    # == internal API ========================================================
    def __init__(self, name, *,
            key = None, is_cell = False, allow_multisource = False, coalesce_connections = False,
            **kwargs):

        if not is_cell and allow_multisource and coalesce_connections:
            raise PRGAInternalError("`allow_multisource` and `coalesce_connections` are incompatible")

        self._name = name
        self._key = uno(key, name)
        self._children = OrderedDict()
        self._ports = OrderedDict()
        self._instances = OrderedDict()

        if is_cell:
            self._flags = self.__FLAGS.IS_CELL | self.__FLAGS.ALLOW_MULTISOURCE
        elif allow_multisource:
            self._flags = self.__FLAGS.ALLOW_MULTISOURCE
        elif coalesce_connections:
            self._flags = self.__FLAGS.COALESCE_CONNECTIONS
        else:
            self._flags = self.__FLAGS.NONE

        for k, v in iteritems(kwargs):
            setattr(self, k, v)

    def __repr__(self):
        return 'Module({})'.format(self.name)

    def _add_child(self, child):
        """Add ``child`` into this module.

        Args:
            child (`Instance` or `Port`):

        Returns:
            ``child``
        """
        # check parent
        if child.parent is not self:
            raise PRGAInternalError("{} is not the parent of {}".format(self, child))
        # check name conflict
        if child.name in self._children:
            raise PRGAInternalError("Name '{}' taken by {} in {}"
                    .format(child.name, self._children[child.name], self))
        # check key conflict
        d = self._ports if isinstance(child, Port) else self._instances
        if child.key in d:
            raise PRGAInternalError("Key '{}' taken by {} in {}"
                    .format(child.key, d[child.key], self))
        # add child and return
        return self._children.setdefault(child.name, d.setdefault(child.key, child))

    # == low-level API =======================================================
    @property
    def name(self):
        """:obj:`str`: Name of this module."""
        return self._name

    @property
    def key(self):
        """:obj:`Hashable`: Key of this module in the database."""
        return self._key

    @property
    def children(self):
        """:obj:`Mapping` [:obj:`str`, `Instance` or `Port` ]: A mapping from names to sub-instances or ports in this
        module."""
        return ReadonlyMappingProxy(self._children)

    @property
    def ports(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Port` ]: A mapping from keys to ports in this module."""
        return ReadonlyMappingProxy(self._ports)

    @property
    def instances(self):
        """:obj:`Mapping` [:obj:`Hashable`, `Instance` ]: A mapping from keys to sub-instances in this module."""
        return ReadonlyMappingProxy(self._instances)

    @property
    def parameters(self):
        return ReadonlyMappingProxy(self._parameters)

    @property
    def prototype(self):
        return None

    @property
    def is_cell(self):
        """:obj:`bool`: Test if this module is a cell module."""
        return bool(self._flags & self.__FLAGS.IS_CELL)

    @property
    def allow_multisource(self):
        """:obj:`bool`: Test if sink nets in this module can be driven by more than one source nets."""
        return bool(self._flags & self.__FLAGS.ALLOW_MULTISOURCE)

    @property
    def coalesce_connections(self):
        """:obj:`bool`: Test if bit-wise connections are disallowed in this module."""
        return bool(self._flags & self.__FLAGS.COALESCE_CONNECTIONS)
