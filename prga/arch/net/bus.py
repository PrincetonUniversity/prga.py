# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import PortDirection
from prga.arch.net.abc import AbstractBus, AbstractPort, AbstractPin
from prga.arch.net.const import UNCONNECTED
from prga.arch.net.bit import DynamicSourceBit, StaticSourceBit, DynamicSinkBit, StaticSinkBit
from prga.util import Object

from abc import abstractproperty

__all__ = ['BaseClockPort', 'BaseInputPort', 'BaseOutputPort', 'BaseInputPin', 'BaseOutputPin']

# ----------------------------------------------------------------------------
# -- Source Bus --------------------------------------------------------------
# ----------------------------------------------------------------------------
class _SourceBus(Object, AbstractBus):
    """Source bus.

    Args:
        parent (`AbstractModule` or `AbstractInstance`): parent module/instance of this bus
    """

    __slots__ = ['_parent', '_static_bits']
    # == internal API ========================================================
    def __init__(self, parent):
        super(_SourceBus, self).__init__()
        self._parent = parent

    # -- implementing properties/methods required by superclass --------------
    def _get_or_create_bit(self, index, dynamic):
        try:
            return self._static_bits[index]
        except AttributeError:
            if dynamic:
                return DynamicSourceBit(self, index)
            else:
                self._static_bits = tuple(StaticSourceBit(self, i) for i in range(self.width))
                return self._static_bits[index]

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @property
    def parent(self):
        """`AbstractModule` or `AbstractInstance`: Parent module/instance of this port/pin."""
        return self._parent

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_sink(self):
        return False

# ----------------------------------------------------------------------------
# -- Sink Bus ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class _SinkBus(Object, AbstractBus):
    """Sink bus.

    Args:
        parent (`AbstractModule` or `AbstractInstance`): parent module/instance of this bus
    """

    __slots__ = ['_parent', '_static_bits', '_physical_source', '_logical_source']
    # == internal API ========================================================
    def __init__(self, parent):
        super(_SinkBus, self).__init__()
        self._parent = parent

    # -- implementing properties/methods required by superclass --------------
    def _get_or_create_bit(self, index, dynamic):
        try:
            return self._static_bits[index]
        except AttributeError:
            if dynamic:
                return DynamicSinkBit(self, index)
            else:
                self._static_bits = tuple(StaticSinkBit(self, i) for i in range(self.width))
                return self._static_bits[index]

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @property
    def parent(self):
        """`AbstractModule` or `AbstractInstance`: Parent module/instance of this port/pin."""
        return self._parent

    @property
    def physical_source(self):
        """:obj:`Sequence` [`AbstractSourceBit` ]: Physical driver of this bus."""
        # 0. physical source is only valid if this is a physical net
        if not self.is_physical:
            raise PRGAInternalError("'{}' is not a physical net"
                    .format(self))
        # 1. check grouped physical source
        try:
            return self._physical_source
        except AttributeError:
            pass
        # 2. check ungrouped physical source
        return tuple(bit.physical_source for bit in self)

    @physical_source.setter
    def physical_source(self, source):
        # 0. physical source is only valid if this is a physical net
        if not self.is_physical:
            raise PRGAInternalError("'{}' is not a physical net"
                    .format(self))
        # 1. shortcut if no changes are to be made
        try:
            if source is self._physical_source:
                return
        except AttributeError:
            pass
        # 2. if ``source`` is a bus or a bit:
        try:
            if source.is_bus:
                # 2.1 validate
                if not (source.is_physical and not source.is_sink and source.width == self.width):
                    raise PRGAInternalError("'{}' is not a {}-bit physical source bus"
                            .format(source, self.width))
                # 2.2 clean up ungrouped physical sources
                try:
                    for bit in self._static_bits:
                        try:
                            del bit._physical_source
                        except AttributeError:
                            pass
                except AttributeError:
                    pass
                # 2.3 update
                self._physical_source = source
            elif self.width == 1:
                # 2.4 validate
                if not (source.is_physical and not source.is_sink):
                    raise PRGAInternalError("'{}' is not a physical source"
                            .format(source))
                # 2.5 clean up grouped physical source
                try:
                    del self._physical_source
                except AttributeError:
                    pass
                # 2.6 update
                self._get_or_create_bit(0, False)._physical_source = source
        # 3. if ``source`` is a sequence of bits
        except AttributeError:
            # 3.1 validate
            if not len(source) == self.width:
                raise PRGAInternalError("Got {} bits but {} expected"
                        .format(len(source), self.width))
            # 3.2 clean up grouped physical source
            try:
                del self._physical_source
            except AttributeError:
                pass
            # 3.3 create links
            for i, src in enumerate(source):
                # 3.3.1 validate
                if not (src.is_physical and not src.is_sink):
                    raise PRGAInternalError("'{}' is not a physical source"
                            .format(src))
                # 3.3.2 update
                self._get_or_create_bit(i, False)._physical_source = src

    @property
    def logical_source(self):
        """:obj:`Sequence` [`AbstractSourceBit` ]: Logical driver of this bus."""
        # 1. check grouped logical source
        try:
            return self._logical_source
        except AttributeError:
            pass
        # 2. check ungrouped logical source
        return tuple(bit.logical_source for bit in self)

    @logical_source.setter
    def logical_source(self, source):
        # 1. shortcut if no changes are to be made
        try:
            if source is self._logical_source:
                return
        except AttributeError:
            pass
        # 2. if ``source`` is a bus or a bit:
        try:
            if source.is_bus:
                # 2.1 validate
                if not (not source.is_sink and source.width == self.width):
                    raise PRGAInternalError("'{}' is not a {}-bit logical source bus"
                            .format(source, self.width))
                # 2.2 clean up ungrouped logical sources
                try:
                    for bit in self._static_bits:
                        try:
                            del bit._logical_source
                        except AttributeError:
                            pass
                except AttributeError:
                    pass
                # 2.3 update
                self._logical_source = source
            elif self.width == 1:
                # 2.4 validate
                if source.is_sink:
                    raise PRGAInternalError("'{}' is not a logical source"
                            .format(source))
                # 2.5 clean up grouped logical source
                try:
                    del self._logical_source
                except AttributeError:
                    pass
                # 2.6 update
                self._get_or_create_bit(0, False)._logical_source = source
        # 3. if ``source`` is a sequence of bits
        except AttributeError:
            # 3.1 validate
            if not len(source) == self.width:
                raise PRGAInternalError("Got {} bits but {} expected"
                        .format(len(source), self.width))
            # 3.2 clean up grouped logical source
            try:
                del self._logical_source
            except AttributeError:
                pass
            # 3.3 create links
            for i, src in enumerate(source):
                # 3.3.1 validate
                if src.is_sink:
                    raise PRGAInternalError("'{}' is not a logical source"
                            .format(src))
                # 3.3.2 update
                self._get_or_create_bit(i, False)._logical_source = src

    # -- implementing properties/methods required by superclass --------------
    @property
    def is_sink(self):
        return True

# ----------------------------------------------------------------------------
# -- Clock Port --------------------------------------------------------------
# ----------------------------------------------------------------------------
class BaseClockPort(_SourceBus, AbstractPort):
    """Clock port.

    Args:
        parent (`AbstractModule`): parent module of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def direction(self):
        return PortDirection.input

    @property
    def is_clock(self):
        return True

    @property
    def width(self):
        return 1

# ----------------------------------------------------------------------------
# -- Input Port --------------------------------------------------------------
# ----------------------------------------------------------------------------
class BaseInputPort(_SourceBus, AbstractPort):
    """Non-clock input port.

    Args:
        parent (`AbstractModule`): parent module of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def direction(self):
        return PortDirection.input

    @property
    def is_clock(self):
        return False

# ----------------------------------------------------------------------------
# -- Output Port -------------------------------------------------------------
# ----------------------------------------------------------------------------
class BaseOutputPort(_SinkBus, AbstractPort):
    """Output port.

    Args:
        parent (`AbstractModule`): parent module of this port
    """

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def direction(self):
        return PortDirection.output

    @property
    def is_clock(self):
        return False

# ----------------------------------------------------------------------------
# -- Input Pin ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class BaseInputPin(_SinkBus, AbstractPin):
    """Clock or non-clock input pin.

    Args:
        parent (`AbstractInstance`): parent instance of this port
        model (`BaseClockPort` or `BaseInputPort`): model of this pin
    """

    __slots__ = ['_model']
    def __init__(self, parent, model):
        super(BaseInputPin, self).__init__(parent)
        self._model = model

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def model(self):
        return self._model

# ----------------------------------------------------------------------------
# -- Output Pin --------------------------------------------------------------
# ----------------------------------------------------------------------------
class BaseOutputPin(_SourceBus, AbstractPin):
    """Output pin.

    Args:
        parent (`AbstractInstance`): parent instance of this port
        model (`BaseOutputPort`): model of this pin
    """

    __slots__ = ['_model']
    def __init__(self, parent, model):
        super(BaseOutputPin, self).__init__(parent)
        self._model = model

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def model(self):
        return self._model
