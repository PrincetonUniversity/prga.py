# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Object

__all__ = ['FASMDelegate']

# ----------------------------------------------------------------------------
# -- FASM Delegate -----------------------------------------------------------
# ----------------------------------------------------------------------------
class FASMDelegate(Object):
    """FASM delegate supplying FASM metadata."""

    def fasm_mux_for_intrablock_switch(self, source, sink, hierarchy):
        """Get the "fasm_mux" string for the connection from ``source`` to ``sink``.

        Args:
            source (`AbstractSourceBit`): Source bit
            sink (`AbstractSinkBit`): Sink bit
            hierarchy (:obj:`Sequence` [`AbstractInstance` ]): Hierarchy from the block level
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_mux" features
        """
        return tuple()

    def fasm_prefix_for_intrablock_module(self, module, hierarchy):
        """Get the "fasm_prefix" string for cluster/mode/primitive module ``module``.

        Args:
            module (`AbstractModule`):
            hierarchy (:obj:`Sequence` [`AbstractInstance` ]): Hierarchy from block level

        Returns:
            :obj:`str`: "fasm_prefix" for the module
        """
        return ''

    def fasm_mode(self, hierarchical_instance, mode):
        """Get the "fasm_features" string for multimode instance ``hierarchical_instance`` when it's configured to
        ``mode``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical multimode instance
                from block level
            mode (:obj:`str`):
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_features" features to be emitted for the leaf-level multimode in the
                hierarchy
        """
        return tuple()

    def fasm_lut(self, hierarchical_instance):
        """Get the "fasm_lut" string for LUT instance ``hierarchical_instance``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical instance from block level

        Returns:
            :obj:`str`: "fasm_lut" feature for the LUT instance
        """
        return ''
    
    def fasm_prefix_for_tile(self, hierarchical_instance):
        """Get the "fasm_prefix" strings for the block instances in tile instance ``hierarchical_instance``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical instance from the top-level
                array

        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_prefix" for the block instances
        """
        return tuple()

    def fasm_features_for_routing_switch(self, hierarchical_switch_input):
        """Get the "fasm_features" strings for selecting ``hierarchical_switch_input``.

        Args:
            hierarchical_switch_input (:obj:`Sequence` [`AbstractInstance` ], `AbstractSourceBit`): Hierarchical
                switch input bit
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: "fasm_features" features
        """
        return tuple()

    def fasm_params(self, hierarchical_instance):
        """Get the "fasm_params" strings for primitive instance ``hierarchical_instance``.

        Args:
            hierarchical_instance (:obj:`Sequence` [`AbstractInstance` ]): Hierarchical instance from block level

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`str` ]: "fasm_param" feature mapping for the primitive instance
        """
        return {}
