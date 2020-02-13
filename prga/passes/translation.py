# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..netlist.module.module import Module
from ..netlist.module.util import ModuleUtils
from ..netlist.net.common import PortDirection
from ..netlist.net.util import NetUtils
from ..core.common import ModuleClass, NetClass, Segment
from ..util import Abstract, Object
from ..exception import PRGAInternalError

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
    def get_switch(self, width):
        """Get a switch module with ``width`` input bits.

        Args:
            width (:obj:`int`): Number of inputs needed

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

    def _process_module(self, module, module_db):
        physical = module_db.get(module.key)
        if physical is not None:
            return physical
        if module.module_class not in (ModuleClass.cluster, ModuleClass.io_block, ModuleClass.logic_block,
                ModuleClass.switch_box, ModuleClass.connection_box, ModuleClass.array):
            raise PRGAInternalError("Cannot translate module '{}'. Its module class is {}"
                    .format(module, module.module_class.name))
        kwargs = {'ports': OrderedDict(), 'instances': OrderedDict(), 'module_class': module.module_class}
        refmap = {}
        if module.key != module.name:
            kwargs['key'] = module.key
        if module.module_class.is_io_block:
            physical = Module(module.name, refmap = refmap, **kwargs)
            i, o = map(lambda x: x in module.instances['io'].pins, ('inpad', 'outpad'))
            if i:
                ModuleUtils.create_port(physical, '_inpad', 1, PortDirection.output, net_class = NetClass.io)
                refmap[0, 'inpad', 'io'] = (0, '_inpad')
            if o:
                ModuleUtils.create_port(physical, '_outpad', 1, PortDirection.input_, net_class = NetClass.io)
                refmap[0, 'outpad', 'io'] = (0, '_outpad')
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
            elif module.module_class.is_array:
                if hasattr(port, 'global_'):
                    net_class = NetClass.global_
                elif isinstance(port.key.prototype, Segment):
                    net_class = NetClass.segment
                else:
                    net_class = NetClass.blockpin
            if net_class is None:
                raise NotImplementedError("Unsupport net class '{}' of port '{}' in module '{}'"
                        .format(net_class.name, port.name, module.name))
            if port.key != port.name:
                ModuleUtils.create_port(physical, port.name, len(port), port.direction,
                        key = port.key, is_clock = port.is_clock, net_class = net_class)
            else:
                ModuleUtils.create_port(physical, port.name, len(port), port.direction,
                        is_clock = port.is_clock, net_class = net_class)
        for instance in itervalues(module.instances):
            if instance.name == 'io' and module.module_class.is_io_block:
                continue
            model = self._process_module(instance.model, module_db)
            if instance.key != instance.name:
                ModuleUtils.instantiate(physical, model, instance.name, key = instance.key)
            else:
                ModuleUtils.instantiate(physical, model, instance.name)
        for net in chain(itervalues(module.ports),
                iter(pin for instance in itervalues(module.instances) for pin in itervalues(instance.pins))):
            if not net.is_sink:
                continue
            for bit in net:
                sink = NetUtils._reference(bit)
                try:
                    sources = tuple(module._conn_graph.predecessors( sink ))
                except NetworkXError:
                    sources = tuple()
                if len(sources) == 0:
                    continue
                sink = refmap.get(sink, sink)
                if len(sources) == 1:
                    physical._conn_graph.add_edge(refmap.get(sources[0], sources[0]), sink)
                    continue
                switch_model = self.switch_database.get_switch(len(sources))
                switch_name = ('_sw' + ('_' + bit.parent.name if bit.net_type.is_pin else '') + '_' +
                        (bit.bus.name + '_' + str(bit.index) if bit.bus_type.is_slice else bit.name))
                switch = ModuleUtils.instantiate(physical, switch_model, switch_name,
                        key = (ModuleClass.switch, ) + sink)
                for source, switch_input in zip(sources, switch.pins['i']):
                    source = refmap.get(source, source)
                    physical._conn_graph.add_edge(source, NetUtils._reference(switch_input))
                physical._conn_graph.add_edge(NetUtils._reference(switch.pins['o']), sink)
        module_db[module.key] = physical
        return physical

    def run(self, context):
        for module in itervalues(context.database.logical_modules):
            self._process_module(module, context.database.physical_modules)
