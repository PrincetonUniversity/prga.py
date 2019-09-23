# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import PortDirection
from prga.arch.net.abc import AbstractBus, AbstractPort, AbstractPin
from prga.arch.net.const import UNCONNECTED
from prga.arch.net.bit import DynamicSourceBit, StaticSourceBit, DynamicSinkBit, StaticSinkBit
from prga.util import Object
from prga.exception import PRGAInternalError

from abc import abstractproperty

__all__ = ['BaseClockPort', 'BaseInputPort', 'BaseOutputPort', 'InputPin', 'OutputPin']

# ----------------------------------------------------------------------------
# -- Base Class for Port/Pin Bus ---------------------------------------------
# ----------------------------------------------------------------------------
class _BaseBus(Object, AbstractBus):
    """Base class for all buses.

    Args:
        parent (`AbstractModule` or `AbstractInstance`): parent module/instance of this bus
    """

    __slots__ = ['_parent', '_bits', '_physical_cp']
    # == internal API ========================================================
    def __init__(self, parent):
        super(_BaseBus, self).__init__()
        self._parent = parent

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def parent(self):
        """`AbstractModule` or `AbstractInstance`: Parent module/instance of this port/pin."""
        return self._parent

    @property
    def physical_cp(self):
        # 0. no physical counterpart if myself is physical
        if self.is_physical:
            return self
        # 1. check grouped physical counterpart
        try:
            return self._physical_cp
        except AttributeError:
            pass
        # 2. check ungrouped physical counterpart
        try:
            return tuple(bit._physical_cp for bit in self._bits)
        except AttributeError:
            return None

    @physical_cp.setter
    def physical_cp(self, cp):
        # 1. shortcut if no changes are to be made
        try:
            if cp is self._physical_cp:
                return
        except AttributeError:
            pass
        # 2. validate
        if self.is_physical:
            raise PRGAInternalError("'{}' is physical so no counterpart should be set"
                    .format(self))
        # 3. ``cp`` is ``None`` or a bus
        try:
            if cp is None or cp.is_bus:
                # 3.1 validate
                if cp is not None and not (cp.is_physical and cp.is_sink is self.is_sink):
                    raise PRGAInternalError("'{}' is not a valid physical counterpart for '{}'"
                            .format(cp, self))
                # 3.2 clean up ungrouped physical counterparts
                try:
                    for bit in self._bits:
                        try:
                            del bit._physical_cp
                        except AttributeError:
                            pass
                except AttributeError:
                    pass
                # 3.3 update
                if cp is None:
                    try:
                        del self._physical_cp
                    except AttributeError:
                        pass
                else:
                    self._physical_cp = cp
            elif self.width == 1:
                # 3.4 validate
                if not (cp.is_physical and cp.is_sink is self.is_sink):
                    raise PRGAInternalError("'{}' is not a valid physical counterpart for '{}'"
                            .format(cp, self))
                # 3.5 clean up grouped physical counterpart
                try:
                    del self._physical_cp
                except AttributeError:
                    pass
                # 3.6 update
                self._get_or_create_bit(0, False)._physical_cp = cp._get_or_create_static_cp()
        # 4. ``cp`` is a sequence of bits
        except AttributeError:
            # 4.1 validate
            if not len(cp) == self.width:
                raise PRGAInternalError("Got {} bits but {} expected"
                        .format(len(cp), self.width))
            # 4.2 clean up grouped physical counterpart
            try:
                del self._physical_cp
            except AttributeError:
                pass
            # 4.3 update
            for i, cpbit in enumerate(cp):
                # 4.3.1 validate
                if cpbit is not None and not (cpbit.is_physical and cpbit.is_sink is self.is_sink):
                    raise PRGAInternalError("'{}' is not a valid physical counterpart for '{}'"
                            .format(cp, self[i]))
                # 4.3.2 update
                if cp is None:
                    try:
                        del self._bits[i]._physical_cp
                    except AttributeError:
                        pass
                else:
                    self._get_or_create_bit(i, False)._physical_cp = cp._get_or_create_static_cp()

# ----------------------------------------------------------------------------
# -- Source Bus --------------------------------------------------------------
# ----------------------------------------------------------------------------
class _SourceBus(_BaseBus, AbstractBus):
    """Source bus.

    Args:
        parent (`AbstractModule` or `AbstractInstance`): parent module/instance of this bus
    """

    # -- implementing properties/methods required by superclass --------------
    def _get_or_create_bit(self, index, dynamic):
        try:
            return self._bits[index]
        except AttributeError:
            if dynamic:
                return DynamicSourceBit(self, index)
            else:
                self._bits = tuple(StaticSourceBit(self, i) for i in range(self.width))
                return self._bits[index]

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def is_sink(self):
        return False

# ----------------------------------------------------------------------------
# -- Sink Bus ----------------------------------------------------------------
# ----------------------------------------------------------------------------
class _SinkBus(_BaseBus, AbstractBus):
    """Sink bus.

    Args:
        parent (`AbstractModule` or `AbstractInstance`): parent module/instance of this bus
    """

    __slots__ = ['_physical_source', '_source']

    # -- implementing properties/methods required by superclass --------------
    def _get_or_create_bit(self, index, dynamic):
        try:
            return self._bits[index]
        except AttributeError:
            if dynamic:
                return DynamicSinkBit(self, index)
            else:
                self._bits = tuple(StaticSinkBit(self, i) for i in range(self.width))
                return self._bits[index]

    # == low-level API =======================================================
    @property
    def source(self):
        """:obj:`Sequence` [`AbstractSourceBit` ]: Logical driver of this bus."""
        # 1. check grouped logical source
        try:
            return self._source
        except AttributeError:
            pass
        # 2. check ungrouped logical source
        return tuple(bit.source for bit in self)

    @source.setter
    def source(self, source):
        # 1. shortcut if no changes are to be made
        try:
            if source is self._source:
                return
        except AttributeError:
            pass
        # 2. if ``source`` is a bus or a bit:
        try:
            if source.is_bus:
                # 2.1 validate
                if not (not source.is_sink and source.width == self.width):
                    raise PRGAInternalError("'{}' is not a {}-bit source bus"
                            .format(source, self.width))
                # 2.2 clean up ungrouped logical sources
                try:
                    for bit in self._bits:
                        try:
                            del bit._source
                        except AttributeError:
                            pass
                except AttributeError:
                    pass
                # 2.3 update
                self._source = source
            elif self.width == 1:
                # 2.4 validate
                if source.is_sink:
                    raise PRGAInternalError("'{}' is not a source"
                            .format(source))
                # 2.5 clean up grouped logical source
                try:
                    del self._source
                except AttributeError:
                    pass
                # 2.6 update
                self._get_or_create_bit(0, False)._source = source
        # 3. if ``source`` is a sequence of bits
        except AttributeError:
            # 3.1 validate
            if not len(source) == self.width:
                raise PRGAInternalError("Got {} bits but {} expected"
                        .format(len(source), self.width))
            # 3.2 clean up grouped logical source
            try:
                del self._source
            except AttributeError:
                pass
            # 3.3 create links
            for i, src in enumerate(source):
                # 3.3.1 validate
                if src.is_sink:
                    raise PRGAInternalError("'{}' is not a source"
                            .format(src))
                # 3.3.2 update
                self._get_or_create_bit(i, False)._source = src

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
                    for bit in self._bits:
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
        return PortDirection.input_

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
        return PortDirection.input_

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
class InputPin(_SinkBus, AbstractPin):
    """Clock or non-clock input pin.

    Args:
        parent (`AbstractInstance`): parent instance of this port
        model (`BaseClockPort` or `BaseInputPort`): model of this pin
    """

    __slots__ = ['_model']
    def __init__(self, parent, model):
        super(InputPin, self).__init__(parent)
        self._model = model

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def model(self):
        return self._model

# ----------------------------------------------------------------------------
# -- Output Pin --------------------------------------------------------------
# ----------------------------------------------------------------------------
class OutputPin(_SourceBus, AbstractPin):
    """Output pin.

    Args:
        parent (`AbstractInstance`): parent instance of this port
        model (`BaseOutputPort`): model of this pin
    """

    __slots__ = ['_model']
    def __init__(self, parent, model):
        super(OutputPin, self).__init__(parent)
        self._model = model

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    @property
    def model(self):
        return self._model
