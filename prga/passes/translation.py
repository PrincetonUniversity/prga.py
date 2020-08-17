# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..netlist import PortDirection, Module, ModuleUtils, NetUtils
from ..core.common import ModuleClass, NetClass, IOType, ModuleView, SegmentID, BlockPinID, Position
from ..util import Object, uno
from ..exception import PRGAInternalError, PRGAAPIError

from abc import abstractmethod
from itertools import chain
from networkx.exception import NetworkXError

import logging
_logger = logging.getLogger(__name__)

__all__ = ['AbstractSwitchDatabase', 'TranslationPass']

# ----------------------------------------------------------------------------
# -- Switch Database ---------------------------------------------------------
# ----------------------------------------------------------------------------
class AbstractSwitchDatabase(Object):
    """Switch database supplying logical switch modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractmethod
    def get_switch(self, width, module = None):
        """Get a switch module with ``width`` input bits.

        Args:
            width (:obj:`int`): Number of inputs needed
            module (`Module`): The module in which the switch is going to be added

        Returns:
            `Module`: Switch module found

        Note:
            The returned switch could have more than ``width`` input bits
        """
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Translation Pass --------------------------------------------------------
# ----------------------------------------------------------------------------
class TranslationPass(AbstractPass):
    """Translate modules in user view to logical view.

    Args:
        top (`Module`): Top-level array in user view. The top array from the context is selected by default

    Keyword Args:
        create_blackbox_for_undefined_primitives (:obj:`bool`): `TranslationPass` does not know how to translate
            primitives. By default, if the logical view is not defined for a primitive, an error is raised.
            If ``create_blackbox_for_undefined_primitives`` is set to ``True``, an empty logical view is created in
            this case.
    """

    __slots__ = ['top', 'create_blackbox_for_undefined_primitives']
    def __init__(self, top = None, *, create_blackbox_for_undefined_primitives = False):
        self.top = top
        self.create_blackbox_for_undefined_primitives = create_blackbox_for_undefined_primitives

    # @classmethod
    # def _u2l(cls, logical_model, user_ref):
    #     # "_logical_cp" mapping is a mapping from user node reference to logical node reference
    #     # both input and output reference are coalesced if and only if ``user_model`` coalesces connections
    #     d = getattr(logical_model, "_logical_cp", None)
    #     if d is None:
    #         return user_ref
    #     else:
    #         return d.get(user_ref, user_ref)

    # @classmethod
    # def _l2u(cls, logical_model, logical_ref):
    #     d = getattr(logical_model, "_user_cp", None)
    #     if d is None:
    #         return logical_ref
    #     else:
    #         return d.get(logical_ref, logical_ref)

    # @classmethod
    # def _register_u2l(cls, logical_model, user_net, logical_net, coalesced = False):
    #     user_node = NetUtils._reference(user_net, coalesced = coalesced)
    #     logical_node = NetUtils._reference(logical_net, coalesced = coalesced)
    #     # user -> logical
    #     try:
    #         d = logical_model._logical_cp
    #     except AttributeError:
    #         d = logical_model._logical_cp = {}
    #     d[user_node] = logical_node
    #     # logical -> user
    #     try:
    #         d = logical_model._user_cp
    #     except AttributeError:
    #         d = logical_model._user_cp = {}
    #     d[logical_node] = user_node

    @property
    def key(self):
        return "translation"

    def _process_module(self, module, context, *, disable_coalesce = False, is_top = False):
        # shortcut if the module is already processed
        if (logical := context._database.get((ModuleView.logical, module.key))) is not None:
            return logical

        # make sure the user module is tranlatible
        if not (module.module_class.is_cluster or
                module.module_class.is_block or
                module.module_class.is_routing_box or
                module.module_class.is_tile or
                module.module_class.is_array): 
            if self.create_blackbox_for_undefined_primitives and module.module_class.is_primitive:
                pass
            else:
                raise PRGAInternalError("Cannot translate module '{}'. Its module class is {:r}"
                        .format(module, module.module_class))

        # prepare the arguments for creating a new module
        kwargs = {
                'view': ModuleView.logical,
                'module_class': module.module_class,
                'key': module.key,
                }

        # propagate primitive_class
        if module.module_class.is_primitive:
            kwargs["primitive_class"] = module.primitive_class
            kwargs["is_cell"] = True
        elif not disable_coalesce and module.coalesce_connections:
            kwargs['coalesce_connections'] = True

        # create logical module
        logical = Module(module.name, **kwargs)

        # translate ports
        for port in itervalues(module.ports):
            attrs = {"key": port.key, "is_clock": port.is_clock}
            if module.module_class.is_primitive:
                attrs["net_class"] = NetClass.user
                if (port_class := getattr(port, "port_class", None)) is not None:
                    attrs["port_class"] = port_class
            elif module.module_class.is_cluster:
                attrs["net_class"] = NetClass.user
            elif module.module_class.is_block:
                if hasattr(port, 'global_'):
                    attrs["net_class"] = NetClass.global_
                else:
                    attrs["net_class"] = NetClass.block
            elif module.module_class.is_routing_box:
                if port.key.node_type.is_segment:
                    attrs["net_class"] = NetClass.segment
                else:
                    attrs["net_class"] = NetClass.bridge
            elif module.module_class.is_array or module.module_class.is_tile:
                attrs["net_class"] = NetClass.bridge
            if "net_class" not in attrs:
                raise NotImplementedError("Could not deduct net class of {}".format(port))
            ModuleUtils.create_port(logical, port.name, len(port), port.direction, **attrs)

        # translate instances
        for instance in itervalues(module.instances):
            logical_model = self._process_module(instance.model, context,
                    disable_coalesce = disable_coalesce or not logical.coalesce_connections)
            logical_instance = ModuleUtils.instantiate(logical, logical_model, instance.name, key = instance.key)

            # for global wires
            if is_top:
                raise NotImplementedError
            else:
                for pin in itervalues(instance.pins):
                    if (global_ := getattr(pin.model, "global_", None)) is not None:
                        if (port := logical.ports.get(global_.name)) is None:
                            port = ModuleUtils.create_port(logical, global_.name, global_.width, PortDirection.input_,
                                    net_class = NetClass.global_, global_ = global_)
                        NetUtils.connect(port, NetUtils._dereference(logical, NetUtils._reference(pin)))

            # for IOs
            if ((logical.module_class.is_io_block and instance.key == "io") or
                    (logical.module_class.is_tile and logical_model.module_class.is_io_block)):
                for iotype in IOType:
                    if (pin := logical_instance.pins.get(iotype)) is None:
                        continue
                    port = None
                    if logical.module_class.is_io_block:
                        port = ModuleUtils.create_port(logical,
                                iotype.case("_ipin", "_opin", "_oe"), 1, pin.model.direction,
                                key = iotype, net_class = NetClass.io)
                    else:
                        port = ModuleUtils.create_port(logical,
                                '{}_x0y0_{:d}'.format(iotype.name, instance.key), len(pin), pin.model.direction,
                                key = (iotype, Position(0, 0), instance.key), net_class = NetClass.io)
                    if port.direction.is_input:
                        NetUtils.connect(port, pin)
                    else:
                        NetUtils.connect(pin, port)

            # # and also IO pins of arrays
            # elif logical_model.module_class.is_array or logical_model.module_class.is_tile:
            #     for key, pin in iteritems(logical_instance.pins):
            #         if not pin.model.net_class.is_io:
            #             continue
            #         iotype, pos, subtile = newkey = key[0], key[1] + instance.key, key[2]
            #         port = ModuleUtils.create_port(logical, "{}_x{}y{}_{:d}".format(iotype.name, *pos, subtile),
            #                 len(pin), pin.model.direction, key = newkey, net_class = NetClass.io)
            #         if port.direction.is_input:
            #             global_ = globals_.pop( port.key[1:], None )
            #             if global_ is not None:
            #                 self._register_u2l(logical, global_, port, module.coalesce_connections)
            #             NetUtils.connect(port, pin)
            #         else:
            #             NetUtils.connect(pin, port)
        # # raise error for unbound globals
        # for port in itervalues(globals_):
        #     raise PRGAInternalError("Global wire '{}' bound to subtile {} at {} but no IO input found there"
        #             .format(port.global_.name, port.global_.bound_to_subtile, port.global_.bound_to_position))

        # translate connections
        if module.module_class.is_primitive:
            pass
        elif module.coalesce_connections:
            for net in ModuleUtils._iter_nets(module):
                if net.is_sink:
                    logical_src, logical_sink = map(lambda x: NetUtils._dereference(logical, NetUtils._reference(x)),
                            (NetUtils.get_source(net), net))
                    NetUtils.connect(logical_src, logical_sink)
        elif module.allow_multisource:
            for net in ModuleUtils._iter_nets(module):
                if not net.is_sink:
                    continue
                for bit in net:
                    if len(user_srcs := NetUtils.get_multisource(bit)) == 0:
                        continue
                    bitref = NetUtils._reference(bit)
                    logical_sink = NetUtils._dereference(logical, bitref)
                    if len(user_srcs) == 1:
                        NetUtils.connect(NetUtils._dereference(logical, NetUtils._reference(user_srcs)), logical_sink)
                        continue
                    switch_model = context.switch_database.get_switch(len(user_srcs), logical)
                    switch_name = ["_sw"]
                    if net.net_type.is_pin:
                        switch_name.append( net.instance.name )
                        switch_name.append( net.model.name )
                    else:
                        switch_name.append( net.name )
                    if bit.net_type.is_bit:
                        switch_name.append( str(bit.index) )
                    switch = ModuleUtils.instantiate(logical, switch_model, "_".join(switch_name),
                            key = (ModuleClass.switch, bitref))
                    NetUtils.connect(
                            tuple(NetUtils._dereference(logical, NetUtils._reference(src)) for src in user_srcs), 
                            switch.pins["i"])
                    NetUtils.connect(switch.pins["o"], logical_sink)

                    if bit.net_type.is_bit:
                        if bit.bus.net_type.is_pin:
                            switch_name.append( bit.bus.instance.name )
                            switch_name.append( bit.bus.model.name )
                        else:
                            switch_name.append( bit.bus.name )
                        switch_name.append( str(bit.index) )
        else:
            for net in ModuleUtils._iter_nets(module):
                if not net.is_sink:
                    continue
                for bit in net:
                    if (src := NetUtils.get_source(bit, return_none_if_unconnected = True)) is None:
                        continue
                    NetUtils.connect(NetUtils._dereference(logical, NetUtils._reference(src)),
                            NetUtils._dereference(logical, bit))

        # add to the database
        context._database[ModuleView.logical, module.key] = logical
        _logger.info("Translated: {}".format(module))
        return logical

    def run(self, context, renderer = None):
        top = uno(self.top, context.top)
        if top is None:
            raise PRGAAPIError("Top-level array not set yet.")
        # recursively process modules
        system_top = self._process_module(top, context, is_top = True)
        if top is context.top:
            context.system_top = system_top
