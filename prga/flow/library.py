# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

__doc__ = """
builtin library delegates.
"""

from prga.arch.common import Orientation
from prga.arch.primitive.builtin import Inpad, Outpad, Iopad, Flipflop, LUT
from prga.arch.switch.switch import ConfigurableMUX
from prga.arch.routing.box import ConnectionBox, SwitchBox
from prga.algorithm.design.switch import SwitchLibraryDelegate
from prga.algorithm.design.array import SwitchBoxLibraryDelegate
from prga.algorithm.design.tile import ConnectionBoxLibraryDelegate
from prga.util import Abstract, Object
from prga.exception import PRGAInternalError

import re
from abc import abstractproperty

__all__ = ['BuiltinPrimitiveLibrary', 'BuiltinSwitchLibrary', 'BuiltinConnectionBoxLibrary', 'BuiltinSwitchBoxLibrary']

# ----------------------------------------------------------------------------
# -- Abstract Base Library ---------------------------------------------------
# ----------------------------------------------------------------------------
class _BaseLibrary(Object):
    """Abstract base class for all libraries.

    Args:
        context (`ArchiectureContext`): architecture context that the library is bound to
    """

    __slots__ = ['_context']
    def __init__(self, context):
        super(_BaseLibrary, self).__init__()
        self._context = context

    # == low-level API =======================================================
    @property
    def context(self):
        """`ArchiectureContext`: The architecture context that the library is bound to."""
        return self._context

# ----------------------------------------------------------------------------
# -- Primitive Library Delegate ----------------------------------------------
# ----------------------------------------------------------------------------
class PrimitiveLibraryDelegate(Abstract):
    """Primitive library supplying primitive modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractmethod
    def get_or_create_primitive(self, name):
        """Get or create the primitive named ``name``.

        Args:
            name (:obj:`str`): Name of the primitive
        """
        raise NotImplementedError

    @abstractproperty
    def is_empty(self):
        """:obj:`bool`: Test if the library is empty."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Primitive Library -------------------------------------------------------
# ----------------------------------------------------------------------------
class BuiltinPrimitiveLibrary(_BaseLibrary, PrimitiveLibraryDelegate):
    """Built-in primitive library."""

    __slots__ = ['_is_empty']
    def __init__(self, context):
        super(BuiltinPrimitiveLibrary, self).__init__(context)
        self._is_empty = True

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    def get_or_create_primitive(self, name):
        module = self.context._modules.get(name)
        if module is not None:
            if not module.module_class.is_primitve:
                raise PRGAInternalError("Existing module named '{}' is not a primitive"
                        .format(name))
            return module
        self._is_empty = False
        if name == 'inpad':
            return self.context._modules.setdefault(name, Inpad(name))
        elif name == 'outpad':
            return self.context._modules.setdefault(name, Outpad(name))
        elif name == 'iopad':
            return self.context._modules.setdefault(name, Iopad(name))
        elif name == 'flipflop':
            return self.context._modules.setdefault(name, Flipflop(name))
        matched = re.match('^lut(?P<width>[2-8])$', name)
        if matched:
            return self.context._modules.setdefault(name, LUT(int(matched.group('width'))))
        raise PRGAInternalError("No built-in primitive named '{}'"
                .format(name))

    @property
    def is_empty(self):
        return self._is_empty

# ----------------------------------------------------------------------------
# -- Switch Library ----------------------------------------------------------
# ----------------------------------------------------------------------------
class BuiltinSwitchLibrary(_BaseLibrary, SwitchLibraryDelegate):
    """Built-in switch library."""

    __slots__ = ['_switches']
    def __init__(self, context):
        super(BuiltinSwitchLibrary, self).__init__(context)
        self._switches = {}

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    def get_or_create_switch(self, width, module):
        switch = self._switches.get(width)
        if switch is not None:
            return switch
        switch = self._switches.setdefault(width, ConfigurableMUX(width))
        return self.context._modules.setdefault(switch.name, switch)

    @property
    def is_empty(self):
        return len(self._switches) == 0

# ----------------------------------------------------------------------------
# -- Connection Box Library --------------------------------------------------
# ----------------------------------------------------------------------------
class BuiltinConnectionBoxLibrary(_BaseLibrary, ConnectionBoxLibraryDelegate):
    """Built-in connection box library."""

    __slots__ = ['_cboxes']
    def __init__(self, context):
        super(BuiltinConnectionBoxLibrary, self).__init__(context)
        self._cboxes = {}   # map from (block name, orientation, position) to (cbox, channel)

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    def get_or_create_cbox(self, block, orientation, position = None, channel = (0, 0)):
        orientation, position = block._validate_orientation_and_position(orientation, position)
        key = (block.name, orientation, position)
        cbox, prev_channel = self._cboxes.get(key, (None, None))
        if cbox is not None:
            if prev_channel == channel: 
                return cbox
            else:
                raise PRGAInternalError(
                        "Connection box to the {} of block {} at {} previously created with channel at {}"
                        .format(orientation.name, block, position, channel))
        name = 'cbox_{}_x{}y{}{}'.format(block.name, position.x, position.y, orientation.name[0])
        cbox, _ = self._cboxes.setdefault(key,
                (ConnectionBox(name, orientation.dimension.perpendicular), channel))
        return self.context._modules.setdefault(name, cbox)

    @property
    def is_empty(self):
        return len(self._cboxes) == 0

# ----------------------------------------------------------------------------
# -- Switch Box Library ------------------------------------------------------
# ----------------------------------------------------------------------------
class BuiltinSwitchBoxLibrary(_BaseLibrary, SwitchLibraryDelegate):
    """Built-in switch box library."""

    __slots__ = ['_sboxes']
    def __init__(self, context):
        super(BuiltinSwitchBoxLibrary, self).__init__(context)
        self._sboxes = {}   # map from (switch box environment, drive truncated) to sbox

    # == low-level API =======================================================
    # -- implementing properties/methods required by superclass --------------
    def get_or_create_sbox(self, env = SwitchBoxEnvironment(), drive_truncated = True):
        sbox = self._sboxes.get( (env, drive_truncated) )
        if sbox is not None:
            return sbox
        name = 'sbox_{}'.format(''.join(map(lambda d: d.name[0],
            filter(lambda d: not d.is_auto and env[d], Orientation))))
        sbox = self._sboxes.setdefault( (env, drive_truncated), SwitchBox(name))
        return self.context._modules.setdefault(name, sbox)

    @property
    def is_empty(self):
        return len(self._sboxes) == 0
