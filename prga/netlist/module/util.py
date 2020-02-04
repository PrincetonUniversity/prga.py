# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.netlist.net.common import PortDirection
from prga.netlist.net.util import NetUtils
from prga.netlist.net.const import Const
from prga.netlist.net.bus import Port, Pin
from prga.netlist.module.module import Module
from prga.netlist.module.instance import Instance

from collections import OrderedDict
from itertools import chain, product

__all__ = ['ModuleUtils']

# ----------------------------------------------------------------------------
# -- Module Utilities --------------------------------------------------------
# ----------------------------------------------------------------------------
class ModuleUtils(object):
    """A wrapper class for utility functions for modules."""

    @classmethod
    def _elaborate_one(cls, module, instance, skip):
        """Elaborate one hierarchical instance ``instance``."""
        submodule = instance[0].model
        # 1. add connections in this instance to the connection graph
        hierarchy = tuple(inst.key for inst in instance)
        for u, v in submodule._conn_graph.edges:
            module._conn_graph.add_edge(u + hierarchy, v + hierarchy)
        # 2. iterate sub-instances 
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
        # TODO: validate
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
