# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Abstract

from abc import abstractproperty

__all__ = ['FASMDelegate', 'VPRTimingDelegate']

# ----------------------------------------------------------------------------
# -- VPR Metadata Generation Delegate for Configuration Circuitry ------------
# ----------------------------------------------------------------------------
class FASMDelegate(Abstract):
    """Delegate supplying metadata for configuration circuitry for VPR files generation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractmethod
    def fasm_prefix_for_tile(self, hierarchical_tile_instance):
        """Get the ``fasm_prefix`` string for ``hierarchical_tile_instance``.

        Args:
            hierarchical_tile_instance (:obj:`Sequence` [`AbstractInstance` ]): Full hierarchy from top-level array to
                a specific tile instance

        Returns:
            :obj:`str`: ``fasm_prefix`` for this tile
        """
        raise NotImplementedError

    @abstractmethod
    def fasm_features_for_clusterlike(self, cluster, hierarchy = tuple()):
        """Get the ``fasm_features`` for ``cluster``.

        Args:
            cluster (:obj:`Mode`, :obj:`Cluster`, :obj:`IOBlock` or :obj:`LogicBlock`): The cluster/block module
            hierarchy (:obj:`Sequence` [`AbstractInstance` ]): The hierarchy from block module to the cluster instance

        Returns:
            :obj:`Sequence` [:obj:`str` ]: ``fasm_features`` to be emitted when this cluster is selected
        """
        raise NotImplementedError

    @abstractmethod
    def fasm_lut(self, hierarchical_lut_instance):
        """Get the ``fasm_lut`` string for ``hierarchical_lut_instance``.

        Args:
            lut_instanceshierarchical_lut_instance (:obj:`Sequence` [`AbstractInstance` ]): Full hierarchy from the
                block module to a specific LUT instance. Modes are skipped in the hierarchy because they can be
                tracked using ``parent`` properties

        Returns:
            :obj:`str`: ``fasm_lut`` target bits for the lut instance
        """
        raise NotImplementedError

    @abstractmethod
    def fasm_mux(self, hierarchical_mux_input):
        """Get the ``fasm_mux`` mapping for ``hierarchical_mux_input``.

        Args:
            hierarchical_mux_input (:obj:`tuple` [:obj:`Sequence` [`AbstractInstance` ], `AbstractBit` ]): Full
                hierarchy from the block module to the input bit of the mux to be selected

        Returns:
            :obj:`Sequence` [:obj:`str` ]: ``fasm_features`` to be emitted
        """
        raise NotImplementedError

    @abstractmethod
    def fasm_features_for_rr_edge_switch(self, hierarchical_mux_input):
        """Get the ``fasm_features`` when the ``hierarchical_mux_input`` is selected/

        Args:
            hierarchical_mux_input (:obj:`tuple` [:obj:`Sequence` [`AbstractInstance` ], `AbstractBit` ]): Full
                hierarchy from the top-level array to the input bit to be selected
        
        Returns:
            :obj:`Sequence` [:obj:`str` ]: ``fasm_features`` to be emitted when this switch input is selected
        """
        raise NotImplementedError
