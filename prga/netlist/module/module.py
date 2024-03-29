# -*- encoding: ascii -*-
"""Netlist modules."""

from ..net.bus import Port
from ...util import ReadonlyMappingProxy, uno, Enum, Object
from ...exception import PRGAInternalError

from enum import IntFlag

__all__ = ['Module']

# ----------------------------------------------------------------------------
# -- Module ------------------------------------------------------------------
# ----------------------------------------------------------------------------
class Module(Object):
    """A netlist module.

    Args:
        name (:obj:`str`): Name of the module

    Keyword Args:
        key (:obj:`Hashable`): A hashable key used to index this module in the database. If not set \(default
            argument: ``None``\), ``name`` is used by default
        is_cell (:obj:`bool`): If set to ``True``, this module is created as a cell module. A cell module does not
            contain information about connections. It contains information about timing arcs instead. A cell module
            may still contain sub-instances, but they are only used for tracking the hierarchy. When set, this
            argument overrides ``allow_multisource`` to ``False`` and ``coalesce_connections`` to ``True``.
            ``coalesce_connections`` is forced to ``True`` because VPR does not support bitwise timing arcs for
            models.
        allow_multisource (:obj:`bool`): If set to ``True``, a sink net may be driven by multiple source nets.
            Incompatible with ``coalesce_connections``
        coalesce_connections (:obj:`bool`): If set to ``True``, bit-wise connections are not allowed.
            Incompatible with ``allow_multisource``
        instances (:obj:`MutableMapping` [:obj:`Hashable`, `Instance` ]): Custom instance mapping object. If not
            specified, a :obj:`dict` object will be created and used
        **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
            and accessible as dynamic attributes
    """

    __slots__ = ["_name", "_key", "_children", "_ports", "_instances", "_flags", "__dict__"]

    class _FLAGS(IntFlag):
        NONE = 0
        IS_CELL = 1 << 0
        ALLOW_MULTISOURCE = 1 << 1
        COALESCE_CONNECTIONS = 1 << 2

    # == internal API ========================================================
    def __init__(self, name, *,
            key = None, is_cell = False, allow_multisource = False, coalesce_connections = False,
            instances = None, **kwargs):

        if not is_cell and allow_multisource and coalesce_connections:
            raise PRGAInternalError("`allow_multisource` and `coalesce_connections` are incompatible")

        self._name = name
        self._key = uno(key, name)
        self._children = {}
        self._ports = {}
        self._instances = uno(instances, {})

        if is_cell:
            self._flags = self._FLAGS.IS_CELL | self._FLAGS.COALESCE_CONNECTIONS
        elif allow_multisource:
            self._flags = self._FLAGS.ALLOW_MULTISOURCE
        elif coalesce_connections:
            self._flags = self._FLAGS.COALESCE_CONNECTIONS
        else:
            self._flags = self._FLAGS.NONE

        for k, v in kwargs.items():
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
        if (conflict := self._children.get(child.name)) is not None:
            raise PRGAInternalError("Name '{}' taken by {} in {}"
                    .format(child.name, conflict, self))
        # check key conflict
        elif ((conflict := self._ports.get(child.key)) is not None or
                (conflict := self._instances.get(child.key)) is not None):
            raise PRGAInternalError("Key '{}' taken by {} in {}"
                    .format(child.key, conflict, self))
        # add child and return
        if isinstance(child, Port):
            return self._children.setdefault(child.name, self._ports.setdefault(child.key, child))
        else:
            return self._children.setdefault(child.name, self._instances.setdefault(child.key, child))

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
    def is_cell(self):
        """:obj:`bool`: Test if this module is a cell module."""
        return bool(self._flags & self._FLAGS.IS_CELL)

    @property
    def allow_multisource(self):
        """:obj:`bool`: Test if sink nets in this module can be driven by more than one source nets."""
        return bool(self._flags & self._FLAGS.ALLOW_MULTISOURCE)

    @property
    def coalesce_connections(self):
        """:obj:`bool`: Test if bit-wise connections are disallowed in this module."""
        return bool(self._flags & self._FLAGS.COALESCE_CONNECTIONS)
