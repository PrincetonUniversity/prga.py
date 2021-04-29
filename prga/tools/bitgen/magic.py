# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator

__all__ = ['MagicBitstreamGenerator']

class MagicBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'magic' programming circuitry."""

    __slots__ = ["prefix", "output"]

    def __init__(self, context, prefix = "dut."):
        super().__init__(context)

        self.prefix = prefix

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

    def set_bits(self, value, hierarchy = None, *, inplace = False):
        path, bitmap = self._process_hierarchy(hierarchy)
        if path is None:
            return

        if bitmap is not None:
            value = value.remap(bitmap, inplace = inplace)

        for v, (o, l) in value.breakdown():
            self.output.write("force {}{}prog_data[{}:{}] = {}'h{:x};\n".format(
                self.prefix, path, o + l - 1, o, l, v))

    def generate_bitstream(self, fasm, output):
        if isinstance(output, str):
            output = open(output, "w")
        self.output = output
        self.parse_fasm(fasm)
