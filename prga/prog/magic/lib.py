# -*- encoding: ascii -*-

from ...core.common import NetClass, ModuleClass, ModuleView
from ...core.context import Context
from ...netlist import TimingArcType, PortDirection, Module, ModuleUtils, NetUtils, Const
from ...passes.base import AbstractPass
from ...passes.translation import SwitchDelegate
from ...passes.vpr.delegate import FASMDelegate
from ...util import Object, uno, Enum
from ..common import AbstractProgCircuitryEntry

__all__ = ['Magic']

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class MagicFASMDelegate(FASMDelegate):
    """FASM Delegate for magic programming circuitry (not ASIC implementable).
    
    Args:
        context (`Context`):
    """

    class _T(Enum):
        _ = 0

    __slots__ = ["context"]
    def __init__(self, context):
        self.context = context

    @classmethod
    def __hierarchy_prefix(cls, hierarchy = None):
        if hierarchy is None:
            return ""
        else:
            return ".".join(i.name for i in reversed(hierarchy.hierarchy)) + "."

    def fasm_mux_for_intrablock_switch(self, source, sink, hierarchy = None):
        conn = NetUtils.get_connection(source, sink, skip_validations = True)
        return tuple(feature for feature in getattr(conn, "fasm_features", tuple()))

    def fasm_prefix_for_intrablock_module(self, module, hierarchy = None):
        if hierarchy:
            leaf = hierarchy.hierarchy[0]
            if (reduce_ := getattr(leaf, "prog_data_map", {}).get("$reduce")) is not None:
                if reduce_ == 0:
                    return None
                else:
                    return "+{}".format(reduce_)
            else:
                return leaf.name
        else:
            return None

    def fasm_features_for_intrablock_module(self, module, hierarchy = None):
        leaf = None if hierarchy is None else hierarchy.hierarchy[0]
        if leaf is None or (enable := getattr(leaf, "prog_data_map", {}).get("$enable", self._T._)) is self._T._:
            if (enable := getattr(module, "prog_data_map", {}).get("$enable", self._T._)) is self._T._:
                return tuple()
        value, base, length = enable
        if base == 0:
            return "~{}'h{:x}".format(length, value),
        else:
            return "+{}.~{}'h{:x}".format(base, length, value),

    def fasm_lut(self, instance):
        leaf = instance.hierarchy[0]
        if (lut := getattr(leaf, "prog_data_map", {}).get("$lut", self._T._)) is self._T._:
            if (lut := getattr(leaf.model, "prog_data_map", {}).get("$lut", self._T._)) is self._T._:
                return None
        _, base, length = lut
        return '[{}:{}]'.format(base + length - 1, base)

    def fasm_prefix_for_tile(self, instance):
        prefix = self.__hierarchy_prefix(instance)
        retval = []
        for subtile, blkinst in instance.model.instances.items():
            if not isinstance(subtile, int):
                continue
            elif subtile >= len(retval):
                retval.extend(None for _ in range(subtile - len(retval) + 1))
            retval[subtile] = prefix + blkinst.name
        return tuple(retval)

    def fasm_features_for_interblock_switch(self, source, sink, hierarchy = None):
        conn = NetUtils.get_connection(source, sink, skip_validations = True)
        prefix = self.__hierarchy_prefix(hierarchy)
        return tuple(prefix + feature for feature in getattr(conn, "fasm_features", tuple()))

# ----------------------------------------------------------------------------
# -- Magic Configuration Circuitry Main Entry --------------------------------
# ----------------------------------------------------------------------------
class Magic(AbstractProgCircuitryEntry):
    """Entry point for magic programming circuitry (not ASIC implementable)."""

    @classmethod
    def new_context(cls):
        ctx = Context("magic")
        ctx._switch_delegate = SwitchDelegate(ctx)
        ctx._fasm_delegate = MagicFASMDelegate(ctx)
        return ctx

    class InsertProgCircuitry(AbstractPass):
        """Insert [fake] programming circuitry."""

        @classmethod
        def __process_module(cls, context, logical_module = None, _cache = None):
            """Set ``prog_data`` of leaf modules to default 0, and update programmable connection info."""
            # short alias
            lmod = uno(logical_module, context.database[ModuleView.logical, context.top.key])

            # check if we should process ``logical_module``
            if lmod.module_class in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.prog, ModuleClass.aux):
                return

            # check if we've processed ``logical_module``
            _cache = uno(_cache, set())
            if lmod.key in _cache:
                return
            _cache.add(lmod.key)

            # process ``lmod``
            if (lmod.module_class.is_tile or lmod.module_class.is_array or
                    lmod.module_class.is_slice or lmod.module_class.is_block):
                for i in lmod.instances.values():
                    cls.__process_module(context, i.model, _cache)

            if lmod.module_class.is_slice or lmod.module_class.is_block or lmod.module_class.is_routing_box:
                # connect ``prog_data`` to constant 0
                for i in lmod.instances.values():
                    if (pin := i.pins.get("prog_data")) is not None:
                        NetUtils.connect(Const(0, len(pin)), pin)

                # traverse connection graph and update programmable connections
                # use timing graph instead of conn graph to get the timing arcs passing through switches
                def node_key(n):
                    bus = n.bus if n.net_type.is_bit or n.net_type.is_slice else n
                    model = bus.model if bus.net_type.is_pin else bus
                    if model.net_class in {NetClass.user, NetClass.block, NetClass.global_,
                            NetClass.segment, NetClass.bridge}:
                        return NetUtils._reference(n)
                    else:
                        return None

                g = ModuleUtils.reduce_timing_graph(lmod,
                        blackbox_instance = lambda i: not i.model.module_class.is_switch,
                        node_key = node_key)

                # iterate paths
                umod = context.database[ModuleView.user, lmod.key]
                for startpoint, endpoint, path in g.edges(data="path"):
                    features = []
                    for net in path:
                        idx, bus = (net.index, net.bus) if net.net_type.is_bit else (0, net)
                        if (bus.net_type.is_pin
                                and bus.model.direction.is_input
                                and bus.instance.model.module_class.is_switch):
                            switch = bus.instance
                            features.append(switch.name + ".~{}'h{:x}".format(
                                len(switch.pins["prog_data"]), switch.model.sel_map[idx]))
                    if not features:
                        continue
                    conn = NetUtils.get_connection(NetUtils._dereference(umod, startpoint),
                            NetUtils._dereference(umod, endpoint), skip_validations = True)
                    conn.fasm_features = tuple(features)

        def run(self, context, renderer = None):
            self.__process_module(context)
            AbstractProgCircuitryEntry.buffer_prog_ctrl(context)

        @property
        def key(self):
            return "prog.insertion.magic"

        @property
        def dependences(self):
            return ("translation", )

        @property
        def passes_after_self(self):
            return ("rtl", )
