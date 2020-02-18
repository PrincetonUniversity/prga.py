# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .module import Module
from .instance import Instance
from ..net.common import PortDirection
from ..net.util import NetUtils
from ..net.const import Const
from ..net.bus import Port, Pin
from ...exception import PRGAInternalError

from collections import OrderedDict
from itertools import chain, product
from networkx import NetworkXError

import logging
_logger = logging.getLogger(__name__)

__all__ = ['ModuleUtils']

# ----------------------------------------------------------------------------
# -- Module Utilities --------------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleUtils(object):
    """A wrapper class for utility functions for modules."""

    @classmethod
    def _elaborate_clocks(cls, module, instance):
        """Elaborate clock connections for hierarchical instance ``instance`` in ``module``."""
        submodule = instance[0].model if instance else module
        # 1. find all clocks and assign clock groups
        for net in itervalues(submodule.ports):
            if not net.is_clock:
                continue
            if net.clock is not None:
                _logger.warning("Clock '{}' marked as clocked by '{}' in '{}'"
                        .format(net, net.clock, submodule))
            # 1.1 find the predecessor(s) of this net
            net_node = NetUtils._reference(net, instance, coalesced = module._coalesce_connections)
            try:
                predit = module._conn_graph.predecessors( net_node )
                # 1.2 make sure there is one predecessor
                pred_node = next(predit)
            except (NetworkXError, StopIteration):  # no predecessors
                if instance:
                    _logger.warning("Clock '{}' (hierarchy: [{}]) is unconnected"
                            .format(net, ', '.join(map(str, reversed(instance)))))
                module._conn_graph.add_node(net_node, clock_group = net_node)   # clock grouped to itself
                continue
            # 1.3 make sure there is only one predecessor
            try:
                next(predit)
                raise PRGAInternalError("Clock '{}' (hierarchy: [{}]) is connected to multiple sources"
                        .format(net, ', '.join(map(str, reversed(instance)))))
            except StopIteration:
                pass
            # 1.4 use the same clock group as the predecessor
            try:
                module._conn_graph.add_node(net_node,
                        clock_group = module._conn_graph.nodes[pred_node]['clock_group'])
            except KeyError:
                pred_net, pred_hierarchy = NetUtils._dereference(module, pred_node, True,
                        coalesced = module._coalesce_connections)
                raise PRGAInternalError("Clock '{}' (hierarchy: [{}]) is connected to '{}' (hierarchy: [{}]) "
                        .format(net, ', '.join(map(str, reversed(instance))),
                            pred_net, ', '.join(map(str, reversed(pred_hierarchy)))) +
                        "which is not assigned a clock group")
        # 2. find all clocked nets
        hierarchy = tuple(inst.key for inst in instance)
        for net in chain(itervalues(submodule.ports), itervalues(submodule.logics)):
            if (net.net_type.is_port and net.is_clock) or net.clock is None:
                continue
            clock = submodule.ports.get(net.clock)
            if clock is None:
                raise PRGAInternalError("Net '{}' is marked as clocked by '{}' but no such port in '{}'"
                        .format(net, net.clock, submodule))
            elif not clock.is_clock:
                raise PRGAInternalError("Net '{}' is marked as clocked by '{}' but '{}' is not a clock"
                        .format(net, net.clock, clock))
            if module._coalesce_connections:
                clock_node = NetUtils._reference(clock, instance, coalesced = True)
                module._conn_graph.add_node( (net.key, ) + hierarchy,
                        clock = module._conn_graph.nodes[clock_node]['clock_group'] )
            else:
                clock_node = NetUtils._reference(clock, instance)
                for i in range(len(net)):
                    module._conn_graph.add_node( (i, (net.key, ) + hierarchy),
                            clock = module._conn_graph.nodes[clock_node]['clock_group'] )

    @classmethod
    def _elaborate_one(cls, module, instance, skip):
        """Elaborate one hierarchical instance ``instance``."""
        submodule = instance[0].model
        if module._coalesce_connections != submodule._coalesce_connections:
            raise PRGAInternalError(
                    "Module '{}' has `coalesce_connections` {} but submodule '{}' (hierarchy: {}) has it {}"
                    .format(module, "set" if module._coalesce_connections else "unset",
                        submodule, "/".join(i.name for i in reversed(instance)),
                        "set" if submodule._coalesce_connections else "unset"))
        # 1. add connections in this instance to the connection graph
        hierarchy = tuple(inst.key for inst in instance)
        if module._coalesce_connections:
            for u, v in submodule._conn_graph.edges:
                module._conn_graph.add_edge(u + hierarchy, v + hierarchy)
        else:
            for u, v in submodule._conn_graph.edges:
                module._conn_graph.add_edge((u[0], u[1] + hierarchy), (v[0], v[1] + hierarchy))
        # 2. clocks
        cls._elaborate_clocks(module, instance)
        # 3. iterate sub-instances 
        for subinstance in itervalues(submodule.instances):
            hierarchy = (subinstance, ) + instance
            if skip(hierarchy):
                continue
            cls._elaborate_one(module, hierarchy, skip)

    @classmethod
    def elaborate(cls, module, hierarchical = False, skip = lambda instance: False):
        """Elaborate ``module``.

        Args:
            module (`AbstractModule`):
            hierarchical (:obj:`bool`): If set, all nets in the hierarchy are elaborated
            skip (:obj:`Function` [:obj:`Sequence` [`AbstractInstance` ]] -> :obj:`bool`): If ``hierarchical`` is set,
                this is a function testing if a specific hierarchical instance should be skipped during elaboration.
        """
        cls._elaborate_clocks(module, tuple())
        if not hierarchical:
            return
        for instance in itervalues(module.instances):
            hierarchy = (instance, )
            if skip(hierarchy):
                continue
            cls._elaborate_one(module, hierarchy, skip)

    @classmethod
    def convert(cls, module, database, logical = False):
        """Convert old module to new module.

        Args:
            module (`AbstractModule`):
            database (:obj:`MutableMapping`):
            logical (:obj:`bool`): If set, logical view is converted. By default, physical view is converted.
        """
        if module.name in database:
            raise RuntimeError("Module '{}' already converted into database".format(module))
        m = database.setdefault(module.name, Module(module.name, ports = OrderedDict(), instances = OrderedDict(),
            allow_multisource = module.is_leaf_module))
        ports = module.logical_ports if logical else module.physical_ports
        instances = module.logical_instances if logical else module.logical_instances
        # 1. ports
        for port in itervalues(ports):
            m._add_net(Port(m, port.name, port.width,
                port.direction.case(PortDirection.input_, PortDirection.output),
                key = port.key, is_clock = port.is_clock, net_class = port.net_class))
        # 2. instances
        for instance in itervalues(instances):
            model = database.get(instance.model.name)
            if model is None:
                model = cls.convert(instance.model, database)
            m._add_instance(Instance(m, model, instance.name, instance.key))
        # 3. connections
        for port in chain(itervalues(ports),
                iter(pin for instance in itervalues(instances)
                    for pin in itervalues(instance.logical_pins if logical else instance.physical_pins))):
            if not port.is_sink:
                continue
            new_port = m.ports[port.key] if port.net_type.is_port else m.instances[port.parent.key].pins[port.key]
            for i, sink in enumerate(port):
                source = sink.logical_source if logical else sink.physical_source
                if source.net_type.is_const:
                    if source.const_net_type.is_unconnected:
                        continue
                    elif source.const_net_type.is_zero:
                        NetUtils.connect(Const(0), new_port[i])
                    else:
                        NetUtils.connect(Const(1), new_port[i])
                else:
                    new_source = (m.ports[source.bus.key][source.index] if source.net_type.is_port else
                            m.instances[source.bus.parent.key].pins[source.bus.key][source.index])
                    NetUtils.connect(new_source, new_port[i])
        # 4. if this is a leaf module, convert combinational sources to connections
        if module.is_leaf_module:
            for port in itervalues(ports):
                sink = m.ports[port.key]
                try:
                    if port.clock:
                        sink._clock = m.ports[ports[port.clock].key]
                except AttributeError:
                    pass
                if not port.is_sink:
                    continue
                for source_name in port.combinational_sources:
                    source = m.ports[ports[source_name].key]
                    for src, snk in product(source, sink):
                        NetUtils.connect(src, snk)
        # 5. return the converted module
        return m

    @classmethod
    def instantiate(cls, parent, model, name, key = None, **kwargs):
        """Instantiate ``model`` in ``parent``.

        Args:
            parent (`AbstractModule`):
            model (`AbstractModule`):
            name (:obj:`str`): Name of the instance
            key (:obj:`Hashable`): A hashable key used to index the instance in the parent module. If not given
                \(default argument: ``None``\), ``name`` is used by default
            **kwargs: Arbitrary attributes assigned to the instantiated instance
        """
        return parent._add_instance(Instance(parent, model, name, key, **kwargs))

    @classmethod
    def create_port(cls, module, name, width, direction, key = None, clock = None, is_clock = False, **kwargs):
        """Create a port in ``module``.

        Args:
            module (`AbstractModule`):
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Number of bits in the port
            direction (`PortDirection`): Direction of the port
            key (:obj:`Hashable`): A hashable key used to index the instance in the parent module. If not given
                \(default argument: ``None``\), ``name`` is used by default
            is_clock (:obj:`bool`): Test if this is a clock
            **kwargs: Arbitrary attributes assigned to the created port
        """
        return module._add_net(Port(module, name, width, direction, key, clock, is_clock, **kwargs))
