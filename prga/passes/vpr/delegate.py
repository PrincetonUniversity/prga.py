# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ...util import Object, uno
from ...exception import PRGAAPIError

__all__ = ['FASMDelegate', 'VPRScalableDelegate']

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class FASMDelegate(Object):
    """FASM delegate used for FASM metadata generation."""

    def reset(self):
        """Reset the delegate."""
        pass

    def fasm_mux_for_intrablock_switch(self, source, sink, hierarchy = None):
        """Get the "fasm_mux" string for the connection from ``source`` to ``sink``.

        Args:
            source: Source net
            sink: Sink net
            hierarchy (`AbstractInstance`): Hierarchy of ``src`` and ``sink`` in the block.
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_mux" values
        """
        return tuple()

    def fasm_params_for_primitive(self, instance = None):
        """Get the "fasm_params" strings for hierarchical primitive ``instance``.

        Args:
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`str` ]: "fasm_param" feature mapping for the primitive instance

        Notes:
            This method is called **ONLY ONCE** for multi-"num_pb" instances.
        """
        return {}

    def fasm_prefix_for_intrablock_module(self, module, hierarchy = None):
        """Get the prefix for ``module`` in intra-block ``hierarchy``.

        Args:
            module (`Module`): The leaf module to be prefixed
            hierarchy (`AbstractInstance`):

        Returns:
            :obj:`str`: "fasm_prefix" value

        Notes:
            This method is called for **EACH** multi-"num_pb" instances.
        """
        return None

    def fasm_features_for_intrablock_module(self, module, hierarchy = None):
        """Get the features for ``module`` in intra-block ``hierarchy``.

        Args:
            module (`Module`): The leaf module to be prefixed
            hierarchy (`AbstractInstance`):

        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_features" values

        Notes:
            This method is called **ONLY ONCE** for multi-"num_pb" instances.
        """
        return tuple()

    def fasm_lut(self, instance):
        """Get the "fasm_lut" strings for hierarchical LUT ``instance``.

        Args:
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block

        Returns:
            :obj:`str`: "fasm_lut" value

        Notes:
            This method is called for **EACH** multi-"vpr_pb" instances.
        """
        return None

    def fasm_prefix_for_tile(self, instance = None):
        """Get the prefix for tile ``instance``.

        Args:
            instance (`AbstractInstance`):

        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_prefix" values
        """
        return tuple()

    def fasm_features_for_interblock_switch(self, source, sink, hierarchy = None):
        """Get the "fasm_features" string for the connection from ``source`` to ``sink``.

        Args:
            source: Source net
            sink: Sink net
            hierarchy (`AbstractInstance`): Hierarchy of ``src`` and ``sink`` in the routing box
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_features" values
        """
        return tuple()

# ----------------------------------------------------------------------------
# -- Scalable Architecture Delegate ------------------------------------------
# ----------------------------------------------------------------------------
class VPRScalableDelegate(Object):
    """Delegate for generating a scalable VPR architecture XML.
    
    Args:
        aspect_ratio (:obj:`float`): Aspect ratio of the fabric

    Keyword Args:
        device (:obj:`Mapping`): Overwrite the auto-generated dummy `device`_ tag in the output VPR specs

    .. _device:
        https://docs.verilogtorouting.org/en/latest/arch/reference/#arch-device-info
    """

    __slots__ = ['active_tiles', 'device', 'layout_rules', 'aspect_ratio']
    def __init__(self, aspect_ratio, *, device = None):
        self.aspect_ratio = aspect_ratio
        self.active_tiles = OrderedDict()
        self.device = uno(device, {})
        self.layout_rules = []

    _rule_args = {
            "fill": {},
            "perimeter": {},
            "corners": {},
            "single": {"x": True, "y": True},
            "col": {"startx": True, "repeatx": False, "starty": False, "incry": False},
            "row": {"starty": True, "repeaty": False, "startx": False, "incrx": False},
            "region": {"startx": False, "endx": False, "repeatx": False, "incrx": False,
                "starty": False, "endy": False, "repeaty": False, "incry": False},
            }

    def add_layout_rule(self, rule, priority, tile, **kwargs):
        """Add a layout rule.

        Args:
            rule (:obj:`str`): `Grid Location Tag`_ type in VPR specs.
            priority (:obj:`int`): `Priority`_ attribute of the rule.
            tile (`Module`): The tile for the rule. Use ``None`` to explicitly add rules for empty tiles.

        Keyword Args:
            **kwargs: Refer to the attributes requirement for each type of rule under the `Grid Location Tag`_ section
                in VPR's documentation

        .. _Grid Location Tag: https://docs.verilogtorouting.org/en/latest/arch/reference/#grid-location-tags
        .. _Priority: https://docs.verilogtorouting.org/en/latest/arch/reference/#grid-location-tags
        """
        if rule not in self._rule_args:
            raise PRGAAPIError("Unknown rule type: {}".format(rule))
        if tile is not None:
            self.active_tiles[tile.key] = True
        # assemble the rule
        attrs = {"type": "EMPTY" if tile is None else tile.name, "priority": priority}
        for k, required in iteritems(self._rule_args[rule]):
            v = kwargs.get(k)
            if v is None:
                if required:
                    raise PRGAAPIError("Missing required keyword argument '{}' for rule '{}'".format(k, rule))
            else:
                attrs[k] = v
        self.layout_rules.append( (rule, attrs) ) 
