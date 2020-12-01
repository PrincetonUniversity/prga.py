# -*- encoding: ascii -*-

from .common import AbstractBitstreamGenerator
from ...exception import PRGAAPIError

import re

class MagicBitstreamGenerator(AbstractBitstreamGenerator):
    """Bitstream generator for 'magic' programming circuitry."""

    _reprog_assign = re.compile("^\[(?P<high>\d+):(?P<low>\d+)\]=(?P<width>\d+)'b(?P<value>[01]+)$")

    def generate_verif(self, summary, fasm, output):
        if isinstance(fasm, str):
            fasm = open(fasm, "r")

        if isinstance(output, str):
            output = open(output, "w")

        for lineno, line in enumerate(fasm, 1):
            s = ['dut']
            base, range_, value = 0, None, None
            for token in line.strip().split("."):
                if token.startswith("~"):
                    if value is not None:
                        raise PRGAAPIError("Multiple values at line No. {}".format(lineno))
                    width, value = token[1:].split("'h")
                    width = int(width)
                    value = int(value, 16)
                    if range_ is not None and range_ != width:
                        raise PRGAAPIError("Width mismatch at line No. {}".format(lineno))
                    range_ = width
                elif token.startswith("+"):
                    base += int(token[1:])
                elif token.startswith("["):
                    if value is not None:
                        raise PRGAAPIError("Multiple values at line No. {}".format(lineno))
                    elif (matched := self._reprog_assign.match(token)) is None:
                        raise PRGAAPIError("Invalid token '{}' at line No. {}".format(token, lineno))
                    high, low, width = map(int, matched.group("high", "low", "width"))
                    value = int(matched.group("value"), 2)
                    if high != low + width - 1:
                        raise PRGAAPIError("Width mismatch at line No. {}".format(lineno))
                    elif range_ is not None and range_ != width:
                        raise PRGAAPIError("Width mismatch at line No. {}".format(lineno))
                    range_ = width
                else:
                    s.append(token)
            output.write("\t\tforce {}.prog_data[{}:{}] = {}'h{:x};\n".format(
                ".".join(s), base + range_ - 1, base, range_, value))
