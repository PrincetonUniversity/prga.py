# -*- encoding: ascii -*-

from .base import AbstractPass
from ..util import uno
from ..core.common import ModuleView, ModuleClass, NetClass
from ..netlist import NetUtils, ModuleUtils

import logging
_logger = logging.getLogger(__name__)

__all__ = ['SwitchPathAnnotation']

# ----------------------------------------------------------------------------
# -- Switch Path Annotation Pass ---------------------------------------------
# ----------------------------------------------------------------------------
class SwitchPathAnnotation(AbstractPass):
    """Annotate design-view implementation of programmable connections on abstract views."""

    @property
    def key(self):
        return "annotation.switch_path"

    @property
    def dependences(self):
        return ("translation", )

    def __process_module(self, context, abstract = None, _cache = None):
        # short alias
        umod = uno(abstract, context.top)

        # check if we should process ``abstract``
        if umod.module_class.is_primitive:
            return

        # check if we've processed ``abstract`` already
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

        # get design-view implementation
        lmod = context.database[ModuleView.design, umod.key]

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
            switch_path = []
            for net in path:
                idx, bus = (net.index, net.bus) if net.net_type.is_bit else (0, net)
                if (bus.net_type.is_pin
                        and bus.model.direction.is_input
                        and bus.instance.model.module_class.is_switch):
                    switch_path.append(net)

            # annotate
            conn = NetUtils.get_connection(NetUtils._dereference(umod, startpoint),
                    NetUtils._dereference(umod, endpoint), skip_validations = True)
            conn.switch_path = tuple(switch_path)

        _logger.info(" .. Annotated: {}".format(umod))

    def run(self, context):
        self.__process_module(context)
