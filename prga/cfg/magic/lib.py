# -*- encoding: ascii -*-

from ...core.common import NetClass, ModuleClass, ModuleView
from ...core.context import Context
from ...netlist import TimingArcType, PortDirection, Module, ModuleUtils, NetUtils
from ...passes.translation import SwitchDelegate
from ...passes.vpr.delegate import FASMDelegate
from ...util import Object, uno
from ..common import AbstractConfigCircuitryEntry

__all__ = ['Magic']

# ----------------------------------------------------------------------------
# -- Magic Configuration Circuitry Main Entry --------------------------------
# ----------------------------------------------------------------------------
class Magic(AbstractConfigCircuitryEntry):
    """Entry point for magic configuration (not ASIC implementable)."""

    @classmethod
    def new_context(cls):
        ctx = Context("magic")
        ctx._switch_delegate = SwitchDelegate(ctx)
        ctx._fasm_delegate = FASMDelegate()
        return ctx
