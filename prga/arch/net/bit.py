# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.abc import AbstractBit, AbstractSourceBit, AbstractSinkBit
from prga.arch.net.const import UNCONNECTED
from prga.util import Object, ReadonlySequenceProxy
from prga.exception import PRGAInternalError

__all__ = ['DynamicSourceBit', 'StaticSourceBit', 'DynamicSinkBit', 'StaticSinkBit']

# ----------------------------------------------------------------------------
# -- Base Class for Port/Pin Bits --------------------------------------------
# ----------------------------------------------------------------------------
class _BaseBit(Object, AbstractBit):
    """Base class for all port/pin bits.
    
    Args:
        bus (`AbstractBus`): The bus to which this bit belongs to
        index (:obj:`int`): The index of this bit in the bus
    """

    __slots__ = ['_bus', '_index']
    # == internal API ========================================================
    def __init__(self, bus, index):
        super(_BaseBit, self).__init__()
        self._bus = bus
        self._index = index
       
    def __str__(self):
        return '{}[{}]'.format(self.bus, self.index)

    # == low-level API =======================================================
    @property
    def bus(self):
        """`AbstractBus`: The bus to which this bit belongs to."""
        return self._bus

    @property
    def index(self):
        """:obj:`int`: The index of this bit in the bus."""
        return self._index

    @property
    def direction(self):
        """`PortDirection`: Direction of this net."""
        return self.bus.direction

    @property
    def parent(self):
        """`AbstractModule` or `AbstractInstance`: Parent module/instance of this net."""
        return self.bus.parent

    @property
    def is_clock(self):
        """:obj:`bool`: Test if this is a clock net."""
        return self.bus.is_clock

    @property
    def net_class(self):
        """`NetClass`: Logical class of this net."""
        return self.bus.net_class

    # -- implementing properties/methods required by superclass --------------
    @property
    def net_type(self):
        return self.bus.net_type

    @property
    def is_physical(self):
        return self.bus.is_physical

    @property
    def is_user_accessible(self):
        return self.bus.is_user_accessible

# ----------------------------------------------------------------------------
# -- Base Class for Dynamic Port/Pin Bits ------------------------------------
# ----------------------------------------------------------------------------
class _BaseDynamicBit(_BaseBit):
    """Base class for all dynamic port/pin bits.
    
    Args:
        bus (`AbstractBus`): The bus to which this bit belongs to
        index (:obj:`int`): The index of this bit in the bus
    """

    # == internal API ========================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def _is_static(self):
        return False

    @property
    def _static_cp(self):
        try:
            return self.bus._bits[self.index]
        except AttributeError:
            return None

    def _get_or_create_static_cp(self):
        return self.bus._get_or_create_bit(self.index, False)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def physical_cp(self):
        if self.is_physical:
            return self
        try:
            return self._static_cp.physical_cp
        except AttributeError:
            return None

    @physical_cp.setter
    def physical_cp(self, cp):
        if self.is_physical:
            raise PRGAInternalError("'{}' is physical so no counterpart should be set"
                    .format(self))
        self._get_or_create_static_cp().physical_cp = cp

# ----------------------------------------------------------------------------
# -- Base Class for Static Port/Pin Bits -------------------------------------
# ----------------------------------------------------------------------------
class _BaseStaticBit(_BaseBit):
    """Base class for all static port/pin bits.

    Args:
        bus (`AbstractBus`): The bus to which this bit belongs to
        index (:obj:`int`): The index of this bit in the bus
    """

    __slots__ = ['_physical_cp']
    # == internal API ========================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def _is_static(self):
        return True

    @property
    def _static_cp(self):
        return self

    def _get_or_create_static_cp(self):
        return self

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def physical_cp(self):
        # 0. no physical counterpart if myself is physical
        if self.is_physical:
            return self
        # 1. check ungrouped physical counterpart
        try:
            return self._physical_cp
        except AttributeError:
            pass
        # 2. check grouped physical counterpart
        try:
            return self.bus._physical_cp[self.index]
        except AttributeError:
            pass
        # 3. give up
        return None

    @physical_cp.setter
    def physical_cp(self, cp):
        # 0. shortcut if no changes are to be made
        if cp is self.physical_cp:
            return
        # 1. validate self and parameter
        if self.is_physical:
            raise PRGAInternalError("'{}' is physical so no counterpart should be set"
                    .format(self))
        if cp is not None and not (cp.is_physical and cp.is_sink is self.is_sink):
            raise PRGAInternalError("'{}' is not a valid physical counterpart for '{}'"
                    .format(cp, self))
        # 2. ungroup grouped physical counterpart if there are
        try:
            grouped = self.bus._physical_cp
            for i in range(self.bus.width):
                l = self.bus._get_or_create_bit(i, False)
                p = grouped._get_or_create_bit(i, False)
                l._physical_cp = p
            del self.bus._physical_cp
        except AttributeError:
            pass
        # 3. update
        if cp is None:
            try:
                del self._physical_cp
            except AttributeError:
                pass
        else:
            self._physical_cp = cp._get_or_create_static_cp()

# ----------------------------------------------------------------------------
# -- Dynamic Source Bit ------------------------------------------------------
# ----------------------------------------------------------------------------
class DynamicSourceBit(_BaseDynamicBit, AbstractSourceBit):
    """Dynamic source bit.

    Args:
        bus (`AbstractBus`): The bus to which this bit belongs to
        index (:obj:`int`): The index of this bit in the bus
    """
    pass

# ----------------------------------------------------------------------------
# -- Dynamic Sink Bit --------------------------------------------------------
# ----------------------------------------------------------------------------
class DynamicSinkBit(_BaseDynamicBit, AbstractSinkBit):
    """Dynamic sink bit.

    Args:
        bus (`AbstractBus`): The bus to which this bit belongs to
        index (:obj:`int`): The index of this bit in the bus
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def source(self):
        # 1. check static counterpart's logical source
        try:
            return self._static_cp._source
        except AttributeError:
            pass
        # 2. check grouped logical source
        try:
            return self.bus._source[self.index]
        except AttributeError:
            pass
        # 3. give up
        return UNCONNECTED

    @source.setter
    def source(self, source):
        self._get_or_create_static_cp().source = source

    @property
    def physical_source(self):
        # 0. physical source is only valid if this is a physical net
        if not self.is_physical:
            raise PRGAInternalError("'{}' is not a physical net"
                    .format(self))
        # 1. check static counterpart's physical source
        try:
            return self._static_cp._physical_source
        except AttributeError:
            pass
        # 2. check grouped physical source
        try:
            return self.bus._physical_source[self.index]
        except AttributeError:
            pass
        # 3. default to logical source
        source = self.source
        if source.is_physical:
            return source
        # 4. give up
        return UNCONNECTED

    @physical_source.setter
    def physical_source(self, source):
        # 0. physical source is only valid if this is a physical net
        if not self.is_physical:
            raise PRGAInternalError("'{}' is not a physical net"
                    .format(self))
        self._get_or_create_static_cp().physical_source = source

    @property
    def user_sources(self):
        # 0. user sources are only valid if this is a user-accessible net
        if not self.is_user_accessible:
            raise PRGAInternalError("'{}' is not a user-accessible sink"
                    .format(self))
        # 1. static bits are always created when user sources are involved
        return self._get_or_create_static_cp().user_sources

    def add_user_sources(self, sources):
        # 0. user sources are only valid if this is a user-accessible net
        if not self.is_user_accessible:
            raise PRGAInternalError("'{}' is not a user-accessible sink"
                    .format(self))
        # 1. static bits are always created when user sources are involved
        return self._get_or_create_static_cp().add_user_sources(sources)

    def remove_user_sources(self, sources = None):
        # 0. user sources are only valid if this is a user-accessible net
        if not self.is_user_accessible:
            raise PRGAInternalError("'{}' is not a user-accessible sink"
                    .format(self))
        # 1. static bits are always created when user sources are involved
        return self._get_or_create_static_cp().remove_user_sources(sources)

# ----------------------------------------------------------------------------
# -- Static Source Bit -------------------------------------------------------
# ----------------------------------------------------------------------------
class StaticSourceBit(_BaseStaticBit, AbstractSourceBit):
    """Static source bit.

    Args:
        bus (`AbstractBus`): The bus to which this bit belongs to
        index (:obj:`int`): The index of this bit in the bus
    """
    pass

# ----------------------------------------------------------------------------
# -- Static Sink Bit ---------------------------------------------------------
# ----------------------------------------------------------------------------
class StaticSinkBit(_BaseStaticBit, AbstractSinkBit):
    """Static sink bit.

    Args:
        bus (`AbstractBus`): The bus to which this bit belongs to
        index (:obj:`int`): The index of this bit in the bus
    """

    __slots__ = ['_source', '_physical_source', '_user_sources']

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def source(self):
        # 1. check ungrouped logical source
        try:
            return self._source
        except AttributeError:
            pass
        # 2. check grouped logical source
        try:
            return self.bus._source[self.index]
        except AttributeError:
            pass
        # 3. give up
        return UNCONNECTED

    @source.setter
    def source(self, source):
        # 0. shortcut if no changes are to be made
        if source is self.source:
            return
        # 1. validate self and source
        if source.is_sink:
            raise PRGAInternalError("'{}' is not a source"
                    .format(source))
        # 2. ungroup grouped logical source if there are
        try:
            grouped = self.bus._source
            for i in range(self.bus.width):
                sink = self.bus._get_or_create_bit(i, False)
                sink._source = grouped._get_or_create_bit(i, False)
            del self.bus._source
        except AttributeError:
            pass
        # 3. update
        self._source = source._get_or_create_static_cp()

    @property
    def physical_source(self):
        # 0. physical source is only valid if this is a physical sink
        if not self.is_physical:
            raise PRGAInternalError("'{}' is not a physical sink"
                    .format(self))
        # 1. check ungrouped physical source
        try:
            return self._physical_source
        except AttributeError:
            pass
        # 2. check grouped physical source
        try:
            return self.bus._physical_source[self.index]
        except AttributeError:
            pass
        # 3. default to logical source
        source = self.source
        if source.is_physical:
            return source
        # 4. give up
        return UNCONNECTED

    @physical_source.setter
    def physical_source(self, source):
        # 0. shortcut if no changes are to be made
        if source is self.physical_source:
            return
        # 1. validate self and source
        if not (source.is_physical and not source.is_sink):
            raise PRGAInternalError("'{}' is not a physical source"
                    .format(source))
        # 2. ungroup grouped physical source if there are
        try:
            grouped = self.bus._physical_source
            for i in range(self.bus.width):
                sink = self.bus._get_or_create_bit(i, False)
                sink._physical_source = grouped._get_or_create_bit(i, False)
            del self.bus._physical_source
        except AttributeError:
            pass
        # 3. update
        self._physical_source = source._get_or_create_static_cp()

    @property
    def user_sources(self):
        if not self.is_user_accessible:
            raise PRGAInternalError("'{}' is not a user sink"
                    .format(self))
        try:
            return ReadonlySequenceProxy(self._user_sources)
        except AttributeError:
            return tuple()

    def add_user_sources(self, sources):
        if not self.is_user_accessible:
            raise PRGAInternalError("'{}' is not a user sink"
                    .format(self))
        for s in sources:
            if s.is_sink:
                # we allow non-user sources to be added to this list
                # this is only used for connection box - switch box bridges
                # in other cases, checks are done by caller of this function
                raise PRGAInternalError("'{}' is not a source"
                        .format(s))
            try:
                if s not in self._user_sources:
                    self._user_sources.append(s)
            except AttributeError:
                self._user_sources = [s]

    def remove_user_sources(self, sources = None):
        if not self.is_user_accessible:
            raise PRGAInternalError("'{}' is not a user sink"
                    .format(self))
        if sources is None:
            try:
                del self._user_sources
            except AttributeError:
                pass
        else:
            for s in sources:
                try:
                    self._user_sources.remove(s)
                except ValueError:
                    raise PRGAInternalError("'{}' is not a user source of user sink '{}'"
                            .format(s, self))
