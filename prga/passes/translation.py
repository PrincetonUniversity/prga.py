# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..netlist.module.module import Module
from ..netlist.module.util import ModuleUtils
from ..netlist.net.common import PortDirection
from ..netlist.net.util import NetUtils
from ..core.common import ModuleClass, NetClass, Segment, ModuleView
from ..util import Abstract, Object
from ..exception import PRGAInternalError, PRGAAPIError

from abc import abstractmethod
from collections import OrderedDict
from itertools import chain
from networkx.exception import NetworkXError

__all__ = ['AbstractSwitchDatabase', 'TranslationPass']

# ----------------------------------------------------------------------------
# -- Switch Database ---------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractSwitchDatabase(Abstract):
    """Switch database supplying physical switch modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractmethod
    def get_switch(self, width, module = None):
        """Get a switch module with ``width`` input bits.

        Args:
            width (:obj:`int`): Number of inputs needed
            module (`AbstractModule`): The module to which the switch is going to be added

        Returns:
            `AbstractModule`: Switch module found

        Note:
            The returned switch could have more than ``width`` input bits
        """
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Translation Pass --------------------------------------------------------
# ----------------------------------------------------------------------------
class TranslationPass(Object, AbstractPass):
    """Translate user-defined modules to physical modules."""

    __slots__ = ['switch_database']
    def __init__(self, switch_database):
        self.switch_database = switch_database

    @property
    def key(self):
        return "translation"

    def _process_module(self, module, context, disable_coalesce = False):
        physical = context.database.get((ModuleView.physical, module.key))
        if physical is not None:
            return physical
        if module.module_class not in (ModuleClass.cluster, ModuleClass.io_block, ModuleClass.logic_block,
                ModuleClass.switch_box, ModuleClass.connection_box, ModuleClass.array):
            raise PRGAInternalError("Cannot translate module '{}'. Its module class is {}"
                    .format(module, module.module_class.name))
        kwargs = {
                'ports': OrderedDict(),
                'instances': OrderedDict(),
                'module_class': module.module_class,
                'key': module.key,
                }
        refmap = {}
        if not disable_coalesce and module._coalesce_connections:
            kwargs['coalesced_connections'] = True
        # if not disable_coalesce and module._coalesce_connections:
        #     if (not module.module_class.is_array or
        #             all(i.model.module_class.is_array for i in itervalues(module.instances))):
        #         kwargs['coalesced_connections'] = True
        if module.module_class.is_io_block:
            physical = Module(module.name, refmap = refmap, **kwargs)
            i, o = map(module.instances['io'].pins.get, ('inpad', 'outpad'))
            if i:
                physical_net = ModuleUtils.create_port(
                        physical, '_inpad', 1, PortDirection.input_, net_class = NetClass.io)
                logical_ref = NetUtils._reference(i, coalesced = module._coalesce_connections)
                physical_ref = NetUtils._reference(physical_net, coalesced = physical._coalesce_connections)
                refmap[logical_ref] = physical_ref
            if o:
                physical_net = ModuleUtils.create_port(
                        physical, '_outpad', 1, PortDirection.output, net_class = NetClass.io)
                logical_ref = NetUtils._reference(o, coalesced = module._coalesce_connections)
                physical_ref = NetUtils._reference(physical_net, coalesced = physical._coalesce_connections)
                refmap[logical_ref] = physical_ref
            if i and o:
                ModuleUtils.create_port(physical, '_oe', 1, PortDirection.output, net_class = NetClass.io)
        else:
            physical = Module(module.name, **kwargs)
        for port in itervalues(module.ports):
            net_class = None
            if module.module_class.is_cluster:
                net_class = NetClass.cluster
            elif module.module_class.is_block:
                if hasattr(port, 'global_'):
                    net_class = NetClass.global_
                else:
                    net_class = NetClass.blockport
            elif module.module_class.is_routing_box:
                if isinstance(port.key.prototype, Segment):
                    net_class = NetClass.segment
                else:
                    net_class = NetClass.blockpin
            # elif module.module_class.is_array:
            #     if hasattr(port, 'global_'):
            #         net_class = NetClass.global_
            #     elif isinstance(port.key.prototype, Segment):
            #         net_class = NetClass.segment
            #     else:
            #         net_class = NetClass.blockpin
            if net_class is None:
                raise NotImplementedError("Unsupport net class '{}' of port '{}' in module '{}'"
                        .format(net_class.name, port.name, module.name))
            ModuleUtils.create_port(physical, port.name, len(port), port.direction,
                    key = port.key, is_clock = port.is_clock, net_class = net_class)
        for instance in itervalues(module.instances):
            if instance.name == 'io' and module.module_class.is_io_block:
                continue
            model = self._process_module(instance.model, context,
                    disable_coalesce or not physical._coalesce_connections)
            ModuleUtils.instantiate(physical, model, instance.name, key = instance.key)
        if not module._allow_multisource:
            if module._coalesce_connections is physical._coalesce_connections:
                for u, v in module._conn_graph.edges:
                    physical._conn_graph.add_edge(refmap.get(u, u), refmap.get(v, v))
            else:   # module._coalesce_connections and not physical._coalesce_connections
                for u, v in module._conn_graph.edges:
                    if u in refmap:
                        u = NetUtils._dereference(physical, refmap[u])
                    else:
                        u = NetUtils._dereference(physical, u, coalesced = True)
                    if v in refmap:
                        v = NetUtils._dereference(physical, refmap[v])
                    else:
                        v = NetUtils._dereference(physical, v, coalesced = True)
                    NetUtils.connect(u, v)
        else:
            for net in chain(itervalues(module.ports),
                    iter(pin for instance in itervalues(module.instances) for pin in itervalues(instance.pins))):
                if not net.is_sink:
                    continue
                for bit in net:
                    logical_sink = NetUtils._reference(bit)
                    try:
                        logical_sources = tuple(module._conn_graph.predecessors( logical_sink ))
                    except NetworkXError:
                        logical_sources = tuple()
                    if len(logical_sources) == 0:
                        continue
                    physical_sink = refmap.get(logical_sink, logical_sink)
                    if len(logical_sources) == 1:
                        physical._conn_graph.add_edge(refmap.get(logical_sources[0], logical_sources[0]),
                                physical_sink)
                        continue
                    bit = NetUtils._dereference(physical, physical_sink)
                    switch_model = self.switch_database.get_switch(len(logical_sources), physical)
                    switch_name = ('_sw' + ('_' + bit.hierarchy[-1].name if bit.net_type.is_pin else '') + '_' +
                            (bit.bus.name + '_' + str(bit.index) if bit.bus_type.is_slice else bit.name))
                    switch = ModuleUtils.instantiate(physical, switch_model, switch_name,
                            key = (ModuleClass.switch, ) + physical_sink)
                    for logical_source, switch_input in zip(logical_sources, switch.pins['i']):
                        physical_source = refmap.get(logical_source, logical_source)
                        physical._conn_graph.add_edge(physical_source, NetUtils._reference(switch_input))
                    physical._conn_graph.add_edge(NetUtils._reference(switch.pins['o']), physical_sink)
        if module.module_class.is_io_block:
            print("?")
            pass
        context.database[ModuleView.physical, module.key] = physical
        return physical

    def run(self, context):
        top = context.top
        if top is None:
            raise PRGAAPIError("Top-level array not set yet.")
        self._process_module(top, context)
