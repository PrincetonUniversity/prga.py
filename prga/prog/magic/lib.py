# -*- encoding: ascii -*-

from ..common import AbstractProgCircuitryEntry
from ...core.common import ModuleClass, ModuleView
from ...netlist import NetUtils, Const
from ...passes.translation import SwitchDelegate
from ...renderer.lib import BuiltinCellLibrary
from ...util import Object, uno, Enum
from ...exception import PRGAInternalError

import logging
_logger = logging.getLogger(__name__)

__all__ = ['Magic']

# ----------------------------------------------------------------------------
# -- Magic Programming Circuitry Main Entry ----------------------------------
# ----------------------------------------------------------------------------
class Magic(AbstractProgCircuitryEntry):
    """Entry point for magic programming circuitry (not ASIC implementable)."""

    @classmethod
    def materialize(cls, ctx, inplace = False):
        ctx = super().materialize(ctx, inplace = inplace)
        ctx._switch_delegate = SwitchDelegate(ctx)

        BuiltinCellLibrary.install_stdlib(ctx)
        BuiltinCellLibrary.install_design(ctx)

        return ctx

    @classmethod
    def _insert_prog_circuitry(cls, context, design_view = None, _cache = None):
        # short alias
        lmod = uno(design_view, context.database[ModuleView.design, context.top.key])

        # check if we should process ``design_view``
        if lmod.module_class in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.prog, ModuleClass.aux):
            return

        # check if we've processed ``design_view``
        _cache = uno(_cache, set())
        if lmod.key in _cache:
            return
        _cache.add(lmod.key)

        # process ``lmod``
        if (lmod.module_class.is_tile or lmod.module_class.is_array or
                lmod.module_class.is_slice or lmod.module_class.is_block):
            for i in lmod.instances.values():
                cls._insert_prog_circuitry(context, i.model, _cache)

        if lmod.module_class.is_slice or lmod.module_class.is_block or lmod.module_class.is_routing_box:
            # connect ``prog_data`` to constant 0
            for i in lmod.instances.values():
                if (pin := i.pins.get("prog_data")) is not None:
                    NetUtils.connect(Const(0, len(pin)), pin)

        _logger.info(" .. Inserted: {}".format(lmod))

    @classmethod
    def insert_prog_circuitry(cls, context):
        cls._insert_prog_circuitry(context)
        cls.buffer_prog_ctrl(context)
