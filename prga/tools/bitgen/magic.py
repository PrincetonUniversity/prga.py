# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator

class MagicBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'magic' programming circuitry."""

    def generate_verif(self, summary, fasm, output):
        if isinstance(fasm, str):
            fasm = open(fasm, "r")

        if isinstance(output, str):
            output = open(output, "w")

        for lineno, line in enumerate(fasm, 1):
            s = ['dut']

            prefixes, value = self.parse_feature(line)
            if value is None:
                continue
            
            for v, (offset, length) in value.breakdown():
                output.write("force dut.{}.prog_data[{}:{}] = {}'h{:x};\n".format(
                    ".".join(prefixes), offset + length - 1, offset, length, v))
