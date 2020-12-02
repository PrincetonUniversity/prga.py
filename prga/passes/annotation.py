# -*- encoding: ascii -*-

from .base import AbstractPass
from ..util import uno
from ..core.common import ModuleView, ModuleClass, NetClass
from ..netlist import NetUtils, ModuleUtils

__all__ = ['LogicalPathAnnotationPass']

# ----------------------------------------------------------------------------
# -- Logical Path Annotation Pass --------------------------------------------
# ----------------------------------------------------------------------------
class LogicalPathAnnotationPass(AbstractPass):
    """Annotate logical implementation of programmable connections on user views."""

    @property
    def key(self):
        return "annotation.logical_path"

    @property
    def dependences(self):
        return ("translation", )

    def __process_module(self, context, user_module = None, _cache = None):
        # short alias
        umod = uno(user_module, context.top)

        # check if we should process ``user_module``
        if umod.module_class.is_primitive:
            return

        # check if we've processed ``user_module`` already
        _cache = uno(_cache, set())
        if umod.key in _cache:
            return
        _cache.add(umod.key)

        # process submodules (instances)
        for i in umod.instances.values():
            self.__process_module(context, i.model, _cache)

        # shortcut for arrays and tiles
        if umod.module_class in (ModuleClass.array, ModuleClass.tile):
            return

        # get logical implementation
        lmod = context.database[ModuleView.logical, umod.key]

        # traverse connection graph and update programmable connections
        # use timing graph instead of conn graph to get the timing arcs passing through switches
        def node_key(n):
            bus = n.bus if n.net_type.is_bit or n.net_type.is_slice else n
            model = bus.model if bus.net_type.is_pin else bus
            if model.net_class in (NetClass.user, NetClass.block, NetClass.global_,
                    NetClass.segment, NetClass.bridge):
                return NetUtils._reference(n)
            else:
                return None

        g = ModuleUtils.reduce_timing_graph(lmod,
                blackbox_instance = lambda i: not i .model.module_class.is_switch,
                node_key = node_key)

        # iterate paths
        for startpoint, endpoint, path in g.edges(data="path"):
            logical_path = []
            for net in path:
                idx, bus = (net.index, net.bus) if net.net_type.is_bit else (0, net)
                if (bus.net_type.is_pin
                        and bus.model.direction.is_input
                        and bus.instance.model.module_class.is_switch):
                    logical_path.append(net)

            # annotate
            conn = NetUtils.get_connection(NetUtils._dereference(umod, startpoint),
                    NetUtils._dereference(umod, endpoint), skip_validations = True)
            conn.logical_path = tuple(logical_path)

    def run(self, context, renderer = None):
        self.__process_module(context)
