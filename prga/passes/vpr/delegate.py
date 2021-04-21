# -*- encoding: ascii -*-

from ...util import Object, uno
from ...netlist.net.util import NetUtils
from ...exception import PRGAAPIError

__all__ = ['FASMDelegate', 'VPRScalableDelegate']

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class FASMDelegate(Object):
    """FASM delegate used for FASM metadata generation."""

    @classmethod
    def _bitmap(cls, bitmap, allow_alternative = False):
        if allow_alternative and len(bitmap._bitmap) == 2:
            range_ = bitmap._bitmap[0][1]
            return "[{}:{}]".format(range_.offset + range_.length - 1, range_.offset)
        else:
            return "".join("+{}#{}".format(o, l) for _, (o, l) in bitmap._bitmap[:-1])

    @classmethod
    def _value(cls, value, breakdown = False):
        if breakdown:
            return tuple("+{}#{}.~{}'h{:x}".format(o, l, l, v)
                    for v, (o, l) in value.breakdown())
        else:
            return cls._bitmap(value.bitmap) + ".~{}'h{:x}".format(
                    value.bitmap.length, value.value)

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
        # XXX: Pay attention to the trailing comma. This line returns a tuple, not a string
        return "{{{}->{}}}".format(NetUtils._reference(source, byname = True), NetUtils._reference(sink, byname = True)),

    def fasm_params_for_primitive(self, instance = None):
        """Get the "fasm_params" strings for hierarchical primitive ``instance``.

        Args:
            instance (`AbstractInstance`): Hierarchical instance in the logic/io block

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`str` ]: "fasm_param" feature mapping for the primitive instance

        Notes:
            This method is called **ONLY ONCE** for multi-"num_pb" instances.
        """
        return { param: '{}[{}:0]'.format(param, width - 1) 
                for param, width in getattr(instance.model, "parameters", {}).items() }

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
        if module.module_class.is_mode:
            return '@' + module.key
        elif hierarchy is not None:
            return hierarchy.hierarchy[0].name
        else:
            return ''

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
        return '+', 

    def fasm_prefix_for_tile(self, instance = None):
        """Get the prefix for tile ``instance``.

        Args:
            instance (`AbstractInstance`):

        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_prefix" values
        """
        prefix = (".".join(i.name for i in reversed(instance.hierarchy)) + ".") if instance else ""
        retval = []
        for subtile, blkinst in instance.model.instances.items():
            if not isinstance(subtile, int):
                continue
            elif subtile >= len(retval):
                retval.extend(None for _ in range(subtile - len(retval) + 1))
            retval[subtile] = prefix + blkinst.name
        return tuple(retval)

    def fasm_features_for_interblock_switch(self, source, sink, hierarchy = None):
        """Get the "fasm_features" string for the connection from ``source`` to ``sink``.

        Args:
            source: Source net
            sink: Sink net
            hierarchy (`AbstractInstance`): Hierarchy of ``src`` and ``sink`` in the routing box
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_features" values
        """
        prefix = (".".join(i.name for i in reversed(hierarchy.hierarchy)) + ".") if hierarchy else ""
        return tuple(prefix + feature for feature in self.fasm_mux_for_intrablock_switch(source, sink, hierarchy))

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
        self.active_tiles = {}
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
        for k, required in self._rule_args[rule].items():
            v = kwargs.get(k)
            if v is None:
                if required:
                    raise PRGAAPIError("Missing required keyword argument '{}' for rule '{}'".format(k, rule))
            else:
                attrs[k] = v
        self.layout_rules.append( (rule, attrs) ) 
