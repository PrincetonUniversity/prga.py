# -*- encoding: ascii -*-

from ...netlist.net.util import NetUtils
from ...prog.common import ProgDataValue
from .common import AbstractBitstreamGenerator

from copy import deepcopy

import logging
_logger = logging.getLogger(__name__)

__all__ = ['MagicBitstreamGenerator']

class MagicBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'magic' programming circuitry."""

    _none = object()

    def _process_hierarchy(self, hierarchy):
        if hierarchy is None:
            return '', None

        path, bitmap = '', None

        for i in hierarchy.hierarchy:
            if (prog_bitmap := getattr(i, "prog_bitmap", self._none)) is not self._none:
                if prog_bitmap is None:
                    return None, None
                else:
                    bitmap = prog_bitmap if bitmap is None else bitmap.remap(prog_bitmap)
            else:
                path = i.name + '.' + path

        return path, bitmap

    def _emit_lines(self, output, value, prefix, hierarchy = None):
        path, bitmap = self._process_hierarchy(hierarchy)
        if path is None:
            return

        if bitmap is not None:
            value = value.remap(bitmap)

        for v, (o, l) in value.breakdown():
            output.write("force {}{}prog_data[{}:{}] = {}'h{:x};\n".format(
                prefix, path, o + l - 1, o, l, v))

    def generate_bitstream(self, fasm, output, *, prefix = 'dut.', verbose = True):
        if isinstance(fasm, str):
            fasm = open(fasm, "r")

        if isinstance(output, str):
            output = open(output, "w")

        for lineno, line in enumerate(fasm, 1):
            if verbose:
                output.write("// [{}:{:0>4d}] {}\n".format(fasm.name, lineno, line.strip()))

            feature = self.parse_feature(line)

            if feature.type_ == "conn":
                if (prog_enable := getattr(feature.conn, "prog_enable", self._none)) is self._none:
                    for net in getattr(feature.conn, "switch_path", tuple()):
                        bus, idx = (net.bus, net.index) if net.net_type.is_bit else (net, 0)
                        self._emit_lines(output, bus.instance.model.prog_enable[idx], prefix,
                                bus.instance._extend_hierarchy(above = feature.hierarchy))

                elif prog_enable is None:
                    continue

                else:
                    self._emit_lines(output, prog_enable, prefix, feature.hierarchy)

            elif feature.type_ == "param":
                leaf = feature.hierarchy.hierarchy[0]

                if (parameters := getattr(leaf, "prog_parameters", self._none)) is self._none:
                    if (parameters := getattr(leaf.model, "prog_parameters", self._none)) is self._none:
                        continue

                if parameters is None or (bitmap := parameters.get(feature.parameter)) is None:
                    continue

                feature.value.remap(bitmap, inplace = True)
                self._emit_lines(output, feature.value, prefix, feature.hierarchy)

            elif feature.type_ == "plain" and feature.feature == "+":
                leaf = feature.hierarchy.hierarchy[0]

                prog_enable = None
                if (feature.module.module_class.is_mode
                        or (prog_enable := getattr(leaf, "prog_enable", self._none)) is self._none):
                    prog_enable = getattr(feature.module, "prog_enable", None)

                if prog_enable is None:
                    continue

                self._emit_lines(output, prog_enable, prefix, feature.hierarchy)

            else:
                _logger.warning("[Line {:0>4d}] Unsupported feature: {}".format(lineno, line.strip()))
