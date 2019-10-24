# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Orientation, Dimension, Global
from prga.arch.net.common import PortDirection
from prga.arch.net.const import UNCONNECTED
from prga.arch.routing.common import SegmentBridgeID, SegmentBridgeType, BlockPortID
from prga.arch.array.port import ArrayExternalInputPort, ArrayExternalOutputPort
from prga.algorithm.design.sbox import SwitchBoxEnvironment
from prga.util import Abstract
from prga.exception import PRGAInternalError

from abc import abstractmethod, abstractproperty
from itertools import product
from collections import OrderedDict

__all__ = ['SwitchBoxLibraryDelegate', 'sboxify', 'netify_array']

# ----------------------------------------------------------------------------
# -- Switch Box Library Delegate ---------------------------------------------
# ----------------------------------------------------------------------------
class SwitchBoxLibraryDelegate(Abstract):
    """Switch box library supplying switch box modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractmethod
    def get_or_create_sbox(self, env = SwitchBoxEnvironment(), drive_truncated = True):
        """Get a switch box module.

        Args:
            env (`SwitchBoxEnvironment`):
        """
        raise NotImplementedError

    @abstractproperty
    def is_empty(self):
        """:obj:`bool`: Test if the library is empty."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Algorithms for Instantiating Switch Boxes in Arrays ---------------------
# ----------------------------------------------------------------------------
def sboxify(lib, array):
    """Instantiate and place switch box instances into ``array``.

    Args:
        lib (`SwitchBoxLibraryDelegate`):
        array (`Array`):
    """
    for x, y in product(range(-1, array.width), range(-1, array.height)):
        pos = (x, y)
        if array.covers_sbox( pos ) and array.get_root_element_for_sbox( pos ) is None:
            env = SwitchBoxEnvironment(
                    not array.covers_channel( (x, y+1), Dimension.y ) or array.runs_channel( (x, y+1), Dimension.y ),
                    not array.covers_channel( (x+1, y), Dimension.x ) or array.runs_channel( (x+1, y), Dimension.x ),
                    not array.covers_channel( (x, y), Dimension.y ) or array.runs_channel( (x, y), Dimension.y ),
                    not array.covers_channel( (x, y), Dimension.x ) or array.runs_channel( (x, y), Dimension.x )
                    )
            array.instantiate_sbox(lib.get_or_create_sbox(env), pos)

# ----------------------------------------------------------------------------
# -- Algorithms for Exposing Ports and Connecting Nets in Arrays -------------
# ----------------------------------------------------------------------------
def find_segment_driver(array, node, create_input = True):
    """Find or create the segment driver for ``node``.

    Args:
        array (`Array`): Find the segment driver in this array
        node (`SegmentID`):
        create_input (:obj:`bool`): If no possible driver found, an input port will be created 
    """
    for sec in range(node.section + 1):
        equiv_node = node - sec
        # 1. is the channel covered?
        if not array.covers_channel(equiv_node.position, node.orientation.dimension):
            if create_input:
                return array.get_or_create_node(equiv_node.to_bridge_id(
                    bridge_type = SegmentBridgeType.array_regular), PortDirection.input_)
            else:
                return None
        # 2. are there wire segments in the channel? 
        if not array.runs_channel(equiv_node.position, node.orientation.dimension):
            return None
        # 3. find the switch box driving the segment
        pos_sbox = equiv_node.position - equiv_node.orientation.case(
                (0, 1), (1, 0), (0, 0), (0, 0))
        if not array.covers_sbox(pos_sbox):
            # create port
            if create_input:
                return array.get_or_create_node(equiv_node.to_bridge_id(
                    bridge_type = SegmentBridgeType.array_regular), PortDirection.input_)
            else:
                return None
        sbox = array.get_root_element_for_sbox(pos_sbox)
        if sbox is None:
            continue
        elif sbox.module_class.is_switch_box:
            try:
                return sbox.all_nodes[equiv_node.move(-sbox.position)]
            except KeyError:
                continue
        elif sbox.module_class.is_array:
            subnode = equiv_node.move(-sbox.position) 
            if not sbox.model.runs_channel(subnode.position, node.orientation.dimension):
                return None
            arraynode = subnode.to_bridge_id(bridge_type = SegmentBridgeType.array_regular)
            pin = sbox.all_nodes.get(arraynode)
            if pin is None:
                subdriver = find_segment_driver(sbox.model, subnode, False)
                if subdriver is None:
                    continue
                assert subdriver.net_type.is_pin and subdriver.direction.is_output
                sbox.model.get_or_create_node(arraynode, PortDirection.output).logical_source = subdriver
                return sbox.all_nodes[arraynode]
            elif pin.direction.is_output:
                return pin
    return None

def create_and_connect_cs_bridge(array, source, create_output = True):
    """Create and connect connection box - switch box bridges recursively.

    Args:
        array (`Array`): Parent array of the bridge
        source (`RoutingNodeOutputPin` or `RoutingNodeInputPort`): Bridge driver
        create_output (:obj:`bool`): If no sink pin found, an output port will be created
    """
    node = source.node
    pos_sbox = node.position - node.orientation.case((0, 1), (1, 0), (0, 0), (0, 0))
    if not array.covers_sbox(pos_sbox):
        for type_ in (SegmentBridgeType.array_cboxout, SegmentBridgeType.array_cboxout2):
            arraynode = node.to_bridge_id(bridge_type = type_)
            arrayport = array.all_nodes.get(arraynode, None)
            if arrayport is None:
                if create_output:
                    array.get_or_create_node(arraynode, PortDirection.output).logical_source = source
                return
            elif arrayport.logical_source is source:
                return
        raise PRGAInternalError("Got the third connection box - switch box bridge: {} in array '{}'"
                .format(node, array))
    sbox = array.get_root_element_for_sbox(pos_sbox)
    if sbox is None:
        return
    if sbox.module_class.is_switch_box:
        for type_ in (SegmentBridgeType.sboxin_cboxout, SegmentBridgeType.sboxin_cboxout2):
            sboxnode = node.move(-sbox.position).to_bridge_id(bridge_type = type_)
            sboxpin = sbox.all_nodes.get(sboxnode, None)
            if sboxpin is None:
                sbox.model.get_or_create_node(sboxnode)
                sbox.all_nodes[sboxnode].logical_source = source
                return
            elif all(bit is UNCONNECTED for bit in sboxpin.logical_source) or sboxpin.logical_source is source:
                sboxpin.logical_source = source
                return
    else:
        for type_ in (SegmentBridgeType.array_cboxout, SegmentBridgeType.array_cboxout2):
            sboxnode = node.move(-sbox.position).to_bridge_id(bridge_type = type_)
            sboxpin = sbox.all_nodes.get(sboxnode, None)
            if sboxpin is None:
                arrayport = sbox.model.get_or_create_node(sboxnode, PortDirection.input_)
                create_and_connect_cs_bridge(sbox.model, arrayport)
                sbox.all_nodes[sboxnode].logical_source = source
                return
            elif all(bit is UNCONNECTED for bit in sboxpin.logical_source) or sboxpin.logical_source is source:
                sboxpin.logical_source = source
                return
        raise PRGAInternalError("Got the third connection box - switch box bridge: {} in array '{}'"
                .format(node, array))

def netify_array(array, top = False):
    """Expose ports and connect nets in ``array``.

    Args:
        array (`Array`):
        top (:obj:`bool`): If set, ``array`` is treated as the top array. Global wires are connected to the bound
            external input port, instead of a hierarchical global input port
    """
    extinputs = [[{} for _ in range(array.height)] for _ in range(array.width)]
    for x, y in product(range(-1, array.width), range(-1, array.height)):
        element = array.element_instances.get( (x, y), None )
        if element is not None:
            snapshot = OrderedDict(iteritems(element.all_pins))
            for pin in itervalues(snapshot):
                if pin.net_class.is_node:
                    node = pin.node
                    if node.node_type.is_segment_bridge:
                        if node.bridge_type.is_array_regular and pin.direction.is_input:
                            # search for segment driver
                            driver = find_segment_driver(array, node.to_driver_id(), not top)
                            if driver is None:
                                continue
                            pin.logical_source = driver
                        elif ((node.bridge_type.is_array_cboxout or node.bridge_type.is_array_cboxout2) and
                                pin.direction.is_output):
                            create_and_connect_cs_bridge(array, pin, not top)
                elif pin.net_class.is_io:
                    node = pin.node
                    if pin.direction.is_input:
                        exti = pin.physical_source = array._add_port(ArrayExternalInputPort(array, node))
                        extinputs[x][y].setdefault(node.subblock, []).append(exti)
                    else:
                        array._add_port(ArrayExternalOutputPort(array, node)).physical_source = pin
        sbox = array.sbox_instances.get( (x, y), None )
        if sbox is not None:
            snapshot = OrderedDict(iteritems(sbox.all_nodes))
            for sboxpin in itervalues(snapshot):
                node = sboxpin.node
                if not (node.node_type.is_segment_bridge and node.bridge_type.is_sboxin_regular):
                    continue
                driver = find_segment_driver(array, node.to_driver_id(), not top)
                if driver is None:
                    continue
                sboxpin.logical_source = driver
    for x, y in product(range(-1, array.width), range(-1, array.height)):
        element = array.element_instances.get( (x, y), None )
        if element is not None:
            for pin in itervalues(element.physical_pins):
                if pin.net_class.is_global:
                    global_ = pin.model.global_
                    if top:
                        if not global_.is_bound:
                            raise PRGAInternalError("Global wire '{}' is not bound to an IOB yet"
                                    .format(global_.name))
                        drivers = extinputs[global_.bound_to_position.x][global_.bound_to_position.y].get(
                                global_.bound_to_subblock, tuple())
                        if len(drivers) == 0:
                            raise PRGAInternalError(
                                    "Global wire '{}' bound to ({}, {}, {}), but no external input found"
                                    .format(global_.name, global_.bound_to_position.x, global_.bound_to_position.y,
                                        global_.bound_to_subblock))
                        elif len(drivers) > 1:
                            raise PRGAInternalError(
                                    "Global wire '{}' bound to ({}, {}, {}), but multiple external inputs found"
                                    .format(global_.name, global_.bound_to_position.x, global_.bound_to_position.y,
                                        global_.bound_to_subblock))
                        elif drivers[0].width != global_.width:
                            raise PRGAInternalError(
                                    ("Global wire '{}' bound to ({}, {}, {}), but its width ({}) does not match the "
                                        "width ({}) of the external input port '{}'")
                                    .format(global_.name, global_.bound_to_position.x, global_.bound_to_position.y,
                                        global_.bound_to_subblock, global_.width, drivers[0].width, drivers[0]))
                        pin.physical_source = drivers[0]
                    else:
                        pin.physical_source = array.get_or_create_global_input(pin.model.global_)
