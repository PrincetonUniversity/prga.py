# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Orientation
from prga.arch.net.common import PortDirection
from prga.arch.net.const import UNCONNECTED
from prga.arch.routing.common import SegmentBridgeID, SegmentBridgeType
from prga.arch.array.port import ArrayExternalInputPort, ArrayExternalOutputPort
from prga.algorithm.design.sbox import SwitchBoxEnvironment
from prga.util import Abstract
from prga.exception import PRGAInternalError

from abc import abstractmethod
from itertools import product

__all__ = ['SwitchBoxLibraryDelegate', 'sboxify', 'netify_array']

# ----------------------------------------------------------------------------
# -- Switch Box Library Delegate ---------------------------------------------
# ----------------------------------------------------------------------------
class SwitchBoxLibraryDelegate(Abstract):
    """Switch box library supplying switch box modules for instantiation."""

    @abstractmethod
    def get_sbox(self, env = SwitchBoxEnvironment(), drive_truncated = True):
        """Get a switch box module.

        Args:
            env (`SwitchBoxEnvironment`):
        """
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
            # TODO: environment!
            array.instantiate_sbox(lib.get_sbox(), pos)

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
            arraynode = subnode.to_bridge_id(bridge_type = SegmentBridgeType.array_regular)
            pin = sbox.all_nodes.get(arraynode)
            if pin is None:
                subdriver = find_segment_driver(sbox.model, subnode, False)
                if subdriver is None:
                    continue
                assert subdriver.net_type.is_pin and subdriver.direction.is_output
                sbox.model.get_or_create_node(arraynode, PortDirection.output).source = subdriver
                return sbox.all_nodes[arraynode]
            elif pin.direction.is_output:
                return pin
    return None

def create_and_connect_cs_bridge(array, source):
    """Create and connect connection box - switch box bridges recursively.

    Args:
        array (`Array`): Parent array of the bridge
        source (`RoutingNodeOutputPin` or `RoutingNodeInputPort`): Bridge driver
    """
    node = source.node
    pos_sbox = node.position - node.orientation.case((0, 1), (1, 0), (0, 0), (0, 0))
    if not array.covers_sbox(pos_sbox):
        for type_ in (SegmentBridgeType.array_cboxout, SegmentBridgeType.array_cboxout2):
            arrayport = array.get_or_create_node(node.to_bridge_id(bridge_type = type_), PortDirection.output)
            if all(bit is UNCONNECTED for bit in arrayport.source) or arrayport.source is source:
                arrayport.source = source
                return
        raise PRGAInternalError("Got the third connection box - switch box bridge: {} in array '{}'"
                .format(node, array))
    sbox = array.get_root_element_for_sbox(pos_sbox)
    if sbox is None:
        return
    if sbox.module_class.is_switch_box:
        for type_ in (SegmentBridgeType.sboxin_cboxout, SegmentBridgeType.sboxin_cboxout2):
            sboxnode = node.to_bridge_id(bridge_type = type_)
            sboxpin = sbox.all_nodes.get(sboxnode, None)
            if sboxpin is None:
                sbox.model.get_or_create_node(sboxnode)
                sbox.all_nodes[sboxnode].source = source
                return
            elif all(bit is UNCONNECTED for bit in sboxpin.source) or sboxpin.source is source:
                sboxpin.source = source
                return
    else:
        for type_ in (SegmentBridgeType.array_cboxout, SegmentBridgeType.array_cboxout2):
            sboxnode = node.to_bridge_id(bridge_type = type_)
            sboxpin = sbox.all_nodes.get(sboxnode, None)
            if sboxpin is None:
                arrayport = sbox.model.get_or_create_node(sboxnode, PortDirection.input_)
                create_and_connect_cs_bridge(sbox.model, arrayport)
                sbox.all_nodes[sboxnode].source = source
            elif all(bit is UNCONNECTED for bit in sboxpin.source) or sboxpin.source is source:
                sboxpin.source = source
                return
    raise PRGAInternalError("Got the third connection box - switch box bridge: {} in array '{}'"
            .format(node, array))

def netify_array(array):
    """Expose ports and connect nets in ``array``.

    Args:
        array (`Array`):
    """
    for x, y in product(range(-1, array.width), range(-1, array.height)):
        element = array.element_instances.get( (x, y), None )
        if element is not None:
            for pin in itervalues(element.all_pins):
                if pin.net_class.is_node:
                    node = pin.node
                    if node.node_type.is_segment_bridge:
                        if node.bridge_type.is_array_regular and pin.direction.is_input:
                            # search for segment driver
                            driver = find_segment_driver(array, node.to_driver_id())
                            if driver is None:
                                continue
                            pin.source = driver
                        elif ((node.bridge_type.is_array_cboxout or node.bridge_type.is_array_cboxout2) and
                                pin.direction.is_output):
                            create_and_connect_cs_bridge(array, pin)
                elif pin.net_class.is_io:
                    node = pin.node
                    if pin.direction.is_input:
                        pin.source = array._add_port(ArrayExternalInputPort(array, node))
                    else:
                        array._add_port(ArrayExternalOutputPort(array, node)).source = pin
                elif pin.net_class.is_global:
                    pin.source = array.get_or_create_global_input(pin.model.global_)
        sbox = array.sbox_instances.get( (x, y), None )
        if sbox is not None:
            for sboxpin in itervalues(sbox.all_nodes):
                node = sboxpin.node
                if not (node.node_type.is_segment_bridge and node.bridge_type.is_sboxin_regular):
                    continue
                driver = find_segment_driver(array, node.to_driver_id())
                if driver is None:
                    continue
                sboxpin.source = driver
