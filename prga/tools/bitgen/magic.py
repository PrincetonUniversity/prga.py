# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator
import argparse, logging

__all__ = ['MagicBitstreamGenerator']

_subparser = argparse.ArgumentParser()
_subparser.add_argument('--prefix', type = str, default = 'dut')
_subparser.add_argument('--checkmode', action = 'store_true')

_logger = logging.getLogger(__name__)

class MagicBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'magic' programming circuitry."""

    __slots__ = ["prefix", "checkmode", "output"]

    def __init__(self, context, prefix = "dut"):
        super().__init__(context)

        self.prefix = prefix
        self.checkmode = False

    def __process_hierarchy(self, hierarchy):
        if hierarchy is None:
            return None, None

        path, bitmap = 'prog_data', None

        for i in hierarchy.hierarchy:
            if ((suffix := getattr(i, "prog_magic_suffix", self._none)) is not self._none
                    or (suffix := getattr(i.model, "prog_magic_suffix", self._none)) is not self._none):
                if suffix is None:
                    return None, None
                else:
                    path = suffix

            elif (prog_bitmap := getattr(i, "prog_bitmap", self._none)) is not self._none:
                if prog_bitmap is None:
                    return None, None
                else:
                    bitmap = prog_bitmap if bitmap is None else bitmap.remap(prog_bitmap)

            else:
                path = i.name + '.' + path

        return path, bitmap

    def parse_fasm(self, fasm):
        if isinstance(fasm, str):
            fasm = open(fasm, "r")

        for lineno, line in enumerate(fasm, 1):

            if (feature := self.parse_feature(line)) is None:
                continue

            elif feature.type_ == "conn":
                if (prog_enable := getattr(feature.conn, "prog_magic_enable", self._none)) is not self._none:
                    pass
                elif (prog_enable := getattr(feature.conn, "prog_enable", self._none)) is self._none:
                    for net in getattr(feature.conn, "switch_path", tuple()):
                        bus, idx = (net.bus, net.index) if net.net_type.is_bit else (net, 0)
                        self.set_bits(bus.instance.model.prog_enable[idx],
                                bus.instance._extend_hierarchy(above = feature.hierarchy))
                    continue

                if prog_enable is None:
                    continue

                else:
                    self.set_bits(prog_enable, feature.hierarchy)

            elif feature.type_ == "param":
                leaf = feature.hierarchy.hierarchy[0]

                if (parameters := getattr(leaf, "prog_magic_parameters", self._none)) is not self._none:
                    pass
                elif (parameters := getattr(leaf.model, "prog_magic_parameters", self._none)) is not self._none:
                    pass
                elif (parameters := getattr(leaf, "prog_parameters", self._none)) is not self._none:
                    pass
                elif (parameters := getattr(leaf.model, "prog_parameters", self._none)) is self._none:
                    continue

                if parameters is None or (bitmap := parameters.get(feature.parameter)) is None:
                    continue

                feature.value.remap(bitmap, inplace = True)
                self.set_bits(feature.value, feature.hierarchy, inplace = True)

            elif feature.type_ == "plain" and feature.feature == "+":
                leaf = feature.hierarchy.hierarchy[0]

                if (not feature.module.module_class.is_mode
                        and (prog_enable := getattr(leaf, "prog_magic_enable", self._none)) is not self._none):
                    pass
                elif (prog_enable := getattr(feature.module, "prog_magic_enable", self._none)) is not self._none:
                    pass
                elif (not feature.module.module_class.is_mode
                        and (prog_enable := getattr(leaf, "prog_enable", self._none)) is not self._none):
                    pass
                else:
                    prog_enable = getattr(feature.module, "prog_enable", None)

                if prog_enable is None:
                    continue

                self.set_bits(prog_enable, feature.hierarchy)

            else:
                _logger.warning("[Line {:0>4d}] Unsupported feature: {}".format(lineno, line.strip()))

    def set_bits(self, value, hierarchy = None, *, inplace = False):
        path, bitmap = self.__process_hierarchy(hierarchy)
        if path is None:
            return

        if bitmap is not None:
            value = value.remap(bitmap, inplace = inplace)

        f = "        force {x}.{p}[{h}:{o}] = {l}'h{v:x};\n"
        if self.checkmode:
            f = \
"""
        if ({x}.{p}[{h}:{o}] != {l}'h{v:x}) begin
            fail = 1'b1;
            $display("[ERROR] {x}.{p}[{h}:{o}] == {l}'h%h != {l}'h{v:x}",
                    {x}.{p}[{h}:{o}]);
        end
"""

        for v, (o, l) in value.breakdown():
            self.output.write(f.format(
                x = self.prefix, p = path, h = o + l - 1, o = o, l = l, v = v))

    def generate_bitstream(self, fasm, output, args):
        if isinstance(output, str):
            output = open(output, "w")
        self.output = output

        ns = _subparser.parse_args(args)
        self.prefix = ns.prefix
        self.checkmode = ns.checkmode

        if self.checkmode:
            self.output.write(
"""// Automatically generated by PRGA
module prga_magic_bitstream_checker;

    reg fail;

    always @(posedge {}.prog_done) begin
        fail = 1'b0;
""".format(self.prefix))

        self.parse_fasm(fasm)

        if self.checkmode:
            self.output.write(
"""
        if (fail) begin
            $display("[ERROR] Magic bitstream check failed. See ERRORs above.");
            $finish;
        end else begin
            $display("[INFO] Magic bitstream check passed. The bitstream seems to be loaded correctly.");
        end

    end

endmodule
""")
