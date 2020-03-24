# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import Position, Orientation, IOType
from ..exception import PRGAInternalError
from ..util import uno, Object

from collections import OrderedDict

__all__ = ['SummaryUpdate']

# ----------------------------------------------------------------------------
# -- Summary Update ----------------------------------------------------------
# ----------------------------------------------------------------------------
class SummaryUpdate(Object, AbstractPass):
    """Update context summary."""

    @property
    def key(self):
        return "summary"

    @classmethod
    def _iob_orientation(cls, blk_inst):
        position = blk_inst.key[0]
        array = blk_inst.parent
        # find the connection box(es) in this tile
        cbox_presence = tuple(ori for ori in iter(Orientation)
                if not ori.is_auto and (position, ori.to_subtile()) in array.instances)
        if len(cbox_presence) == 0:
            raise PRGAInternalError(
                    "No connection box found around IO block '{}' at {} of array '{}'"
                    .format(blk_inst.model.name, position, array.name))
        elif len(cbox_presence) > 1:
            raise PRGAInternalError(
                    "Multiple connection boxes ({}) found around IO block '{}' at {} of array '{}'"
                    .format(", ".join(ori.name for ori in cbox_presence),
                        blk_inst.model.name, position, array.name))
        ori = cbox_presence[0].opposite
        if not array.edge[ori]:
            raise PRGAInternalError(("Connection box found to the {} of IO block '{}' at {} but "
                "the block is not on the {} edge of the FPGA")
                .format(cbox_presence[0].name, blk_inst.model.name, position, ori.name))
        return ori

    @classmethod
    def _visit_array(cls, summary, array, visited = None, position = Position(0, 0)):
        visited = uno(visited, set())
        if array.module_class.is_nonleaf_array:
            for instance in itervalues(array.instances):
                cls._visit_array(summary, instance.model, visited, position + instance.key)
        else:
            for instance in itervalues(array.instances):
                if instance.model.module_class.is_block:
                    if instance.model.module_class.is_io_block:
                        # Update IO block
                        for iotype, name in ((IOType.ipin, "inpad"), (IOType.opin, "outpad")):
                            if name in instance.model.instances["io"].pins:
                                summary.ios.append( (iotype, position + instance.key[0], int(instance.key[1])) )
                        # update orientations
                        ori = cls._iob_orientation(instance)
                        summary.active_blocks.setdefault(instance.model.key, set()).add(ori)
                    else:
                        summary.active_blocks[instance.model.key] = True
                    if instance.model.key not in visited:
                        visited.add( instance.model.key )
                        cls._visit_module(summary, instance.model, visited)

    @classmethod
    def _visit_module(cls, summary, module, visited):
        for instance in itervalues(module.instances):
            if instance.model.key in visited:
                continue
            visited.add(instance.model.key)
            if instance.model.module_class.is_cluster:
                cls._visit_module(summary, instance.model, visited)
            elif instance.model.module_class.is_primitive:
                primitive = instance.model
                if primitive.primitive_class.is_multimode:
                    for mode in itervalues(primitive.modes):
                        cls._visit_module(summary, mode, visited)
                elif primitive.primitive_class.is_lut:
                    summary.lut_sizes.add( len(primitive.ports['in']) )
                elif primitive.primitive_class.is_memory or primitive.primitive_class.is_custom:
                    summary.active_primitives.add( primitive.key )

    def run(self, context):
        context.summary.ios = []
        context.summary.active_blocks = OrderedDict()
        context.summary.active_primitives = set()
        context.summary.lut_sizes = set()
        self._visit_array(context.summary, context.top)
