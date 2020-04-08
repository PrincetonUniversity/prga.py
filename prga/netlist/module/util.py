# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .module import Module
from .instance import Instance
from ..net.common import PortDirection
from ..net.util import NetUtils
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

    # @classmethod
    # def _elaborate_clocks(cls, module, instance = None):
    #     """Elaborate clock connections for hierarchical instance ``instance`` in ``module``."""
    #     model = instance.model if instance else module
    #     # 1. find all clocks and assign clock groups
    #     for net in itervalues(instance.pins if instance else module.ports):
    #         port = net if net.net_type.is_port else net.model
    #         if not port.is_clock:
    #             continue
    #         if port.clock is not None:
    #             _logger.warning("Clock '{}' marked as clocked by '{}' in '{}'"
    #                     .format(port, port.clock, model))
    #         # 1.1 find the predecessor(s) of this net
    #         net_node = NetUtils._reference(net, coalesced = module._coalesce_connections)
    #         try:
    #             predit = module._conn_graph.predecessors( net_node )
    #             # 1.2 make sure there is one predecessor
    #             pred_node = next(predit)
    #         except (NetworkXError, StopIteration):  # no predecessors
    #             if instance:
    #                 _logger.warning("Clock '{}' is unconnected".format(net))
    #             # module._conn_graph.setdefault("clock_groups", {}).setdefault(net_node, []).append( net_node )
    #             module._conn_graph.add_node(net_node, clock_group = net_node)   # clock grouped to itself
    #             continue
    #         # 1.3 make sure there is only one predecessor
    #         try:
    #             next(predit)
    #             raise PRGAInternalError("Clock '{}' is connected to multiple sources".format(net))
    #         except StopIteration:
    #             pass
    #         # 1.4 get the clock group of the predecessor
    #         try:
    #             clock_group = module._conn_graph.nodes[pred_node]['clock_group']
    #         except KeyError:
    #             pred_net = NetUtils._dereference(module, pred_node,
    #                     coalesced = module._coalesce_connections)
    #             raise PRGAInternalError("Clock '{}' is connected to '{}' which is not assigned into any clock group"
    #                     .format(net, pred_net))
    #         # 1.5 assign this clock into the predecessor's clock group
    #         # module._conn_graph["clock_groups"][clock_group].append( net_node )
    #         module._conn_graph.add_node(net_node, clock_group = clock_group)
    #     # 2. find all clocked nets
    #     for net in itervalues(instance.pins if instance else module.ports):
    #         port = net if net.net_type.is_port else net.model
    #         if port.is_clock or port.clock is None:
    #             continue
    #         clock = model.ports.get(port.clock)
    #         if clock is None:
    #             raise PRGAInternalError("'{}' is marked as clocked by '{}' but no such port in '{}'"
    #                     .format(port, port.clock, model))
    #         elif not clock.is_clock:
    #             raise PRGAInternalError("Net '{}' is marked as clocked by '{}' but '{}' is not a clock"
    #                     .format(port, port.clock, clock))
    #         if instance:
    #             clock = clock._to_pin(instance)
    #         if module._coalesce_connections:
    #             clock_node = NetUtils._reference(clock, coalesced = True)
    #             module._conn_graph.add_node( NetUtils._reference(net, coalesced = True),
    #                     clock = module._conn_graph.nodes[clock_node]['clock_group'] )
    #         else:
    #             clock_node = NetUtils._reference(clock)
    #             for bit in net:
    #                 module._conn_graph.add_node( NetUtils._reference(bit),
    #                         clock = module._conn_graph.nodes[clock_node]['clock_group'] )

    # @classmethod
    # def _elaborate(cls, module, instance, skip):
    #     """Elaborate one hierarchical instance ``instance``."""
    #     submodule = instance.model
    #     if module._coalesce_connections != submodule._coalesce_connections:
    #         raise PRGAInternalError(
    #                 "Module '{}' has `coalesce_connections` {} but submodule '{}' (hierarchy: {}) has it {}"
    #                 .format(module, "set" if module._coalesce_connections else "unset",
    #                     submodule, "/".join(i.name for i in reversed(instance)),
    #                     "set" if submodule._coalesce_connections else "unset"))
    #     # 1. add connections in this instance to the connection graph
    #     hierarchy = instance.hierarchical_key
    #     if module._coalesce_connections:
    #         for u, v in submodule._conn_graph.edges:
    #             module._conn_graph.add_edge(u + hierarchy, v + hierarchy)
    #     else:
    #         for u, v in submodule._conn_graph.edges:
    #             module._conn_graph.add_edge((u[0], u[1] + hierarchy), (v[0], v[1] + hierarchy))
    #     # 2. clocks
    #     cls._elaborate_clocks(module, instance)
    #     # 3. iterate sub-instances 
    #     for subinstance in itervalues(submodule.instances):
    #         hierarchy = instance.delve(subinstance)
    #         if skip(hierarchy):
    #             continue
    #         cls._elaborate(module, hierarchy, skip)
    #     # 4. register this instance as elaborated
    #     module._elaborated.add( instance.hierarchical_key )

    # @classmethod
    # def elaborate(cls, module, hierarchical = False, skip = lambda instance: False):
    #     """Elaborate ``module``.

    #     Args:
    #         module (`AbstractModule`):
    #         hierarchical (:obj:`bool`): If set, all nets in the hierarchy are elaborated
    #         skip (:obj:`Function` [`AbstractInstance` ] -> :obj:`bool`): If ``hierarchical`` is set,
    #             this is a function testing if a specific hierarchical instance should be skipped during elaboration.
    #     """
    #     cls._elaborate_clocks(module)
    #     if not hierarchical:
    #         return
    #     for instance in itervalues(module.instances):
    #         if not skip(instance):
    #             cls._elaborate(module, instance, skip)

    @classmethod
    def create_port(cls, module, name, width, direction, *, key = None, is_clock = False, **kwargs):
        """Create a port in ``module``.

        Args:
            module (`AbstractModule`):
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Number of bits in the port
            direction (`PortDirection`): Direction of the port

        Keyword Args:
            key (:obj:`Hashable`): A hashable key used to index the port in the parent module. If not given
                \(default argument: ``None``\), ``name`` is used by default
            is_clock (:obj:`bool`): Mark this as a clock
            **kwargs: Arbitrary attributes assigned to the created port
        """
        if is_clock and width != 1:
            raise PRGAInternalError("Clock port must be 1-bit wide")
        # check name conflict
        if name in module._children:
            raise PRGAInternalError("Name '{}' already taken by {} in {}"
                    .format(name, module._children[name], module))
        # check key conflict
        new = Port(module, name, width, direction, key = key, is_clock = is_clock, **kwargs)
        value = module._ports.setdefault(new.key, new)
        if value is not new:
            raise PRGAInternalError("Key '{}' already taken by {} in {}"
                    .format(new.key, value, module))
        return module._children.setdefault(name, value)

    @classmethod
    def instantiate(cls, module, model, name, *, key = None, **kwargs):
        """Instantiate ``model`` in ``parent``.

        Args:
            module (`AbstractModule`):
            model (`AbstractModule`):
            name (:obj:`str`): Name of the instance

        Keyword Args:
            key (:obj:`Hashable`): A hashable key used to index the instance in the parent module. If not given
                \(default argument: ``None``\), ``name`` is used by default
            **kwargs: Arbitrary attributes assigned to the instantiated instance
        """
        if module.is_cell:
            raise PRGAInternalError("Cannot instantiate {} in {}".format(model, module))
        # check name conflict
        if name in module._children:
            raise PRGAInternalError("Name '{}' already taken by {} in {}"
                    .format(name, module._children[name], module))
        # check key conflict
        new = Instance(module, model, name, key = key, **kwargs)
        value = module._instances.setdefault(new.key, new)
        if value is not new:
            raise PRGAInternalError("Key '{}' already taken by {} in {}".format(new.key, value, module))
        return module._children.setdefault(name, value)
