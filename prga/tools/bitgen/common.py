# -*- encoding: ascii -*-

from ...prog import ProgDataBitmap, ProgDataValue
from ...util import Object

import re

class AbstractBitstreamGenerator(Object):
    """Abstract base class for bitstream generators."""

    _reprog_bitmap_full = re.compile("(?:<\d+>\d+)+")
    _reprog_bitmap      = re.compile("<(?P<offset>\d+)>(?P<length>\d+)")
    _reprog_last_type0  = re.compile("~(?P<length>\d+)"
            "'(?P<notation>[bdh])(?P<value>[a-fA-F0-9]+)")
    _reprog_last_type1  = re.compile("\[(?P<high>\d+):(?P<low>\d+)\]=(?P<length>\d+)"
            "'(?P<notation>[bdh])(?P<value>[a-fA-F0-9]+)")
    _reprog_last_type2  = re.compile("(?P<bitmap>(?:<\d+>\d+)+)=(?P<length>\d+)'"
            "(?P<notation>[bdh])(?P<value>[a-fA-F0-9]+)")

    def generate_verif(self, summary, fasm, output):
        """Generate bitstream for verification purpose."""
        raise NotImplementedError("Cannot generate bitstream for verification purpose")

    def generate_raw(self, summary, fasm, output):
        """Generate raw bitstream."""
        raise NotImplementedError("Cannot generate raw bitstream")

    def __parse_bitmap(self, s):
        """Parse bitmap."""
        bitmap = []
        for obj in self._reprog_bitmap.finditer(s):
            bitmap.append(tuple(map(int, obj.group("offset", "length"))))
        return bitmap

    def parse_feature(self, line):
        """Parse FASM features.

        Returns:
            :obj:`Sequence` [:obj:`str` ]: uncommon prefixes
            `ProgDataValue`: bitstream values
        """

        # split up
        tokens = line.strip().split(".")

        # process last token first (in case it's not a feature in the standard format)
        value = None
        notations = {"b": 2, "d": 10, "h": 16}
        if (obj := self._reprog_last_type0.fullmatch(tokens[-1])):
            value = ProgDataValue(int(obj.group("value"), notations[obj.group("notation")]),
                    (0, int(obj.group("length"))))
        elif (obj := self._reprog_last_type1.fullmatch(tokens[-1])):
            value = ProgDataValue(int(obj.group("value"), notations[obj.group("notation")]),
                    tuple(map(int, obj.group("low", "length"))))
        elif (obj := self._reprog_last_type2.fullmatch(tokens[-1])):
            value = ProgDataValue(int(obj.group("value"), notations[obj.group("notation")]),
                    *self.__parse_bitmap(obj.group("bitmap")))
        else:
            return tuple(tokens), None

        # process prefixes
        prefixes = []
        standard = True
        for s in reversed(tokens[:-1]):
            if standard and (obj := self._reprog_bitmap_full.fullmatch(s)):
                value.bitmap = value.bitmap.remap(ProgDataBitmap(*self.__parse_bitmap(s)))
            else:
                prefixes.append(s)
                standard = False

        return tuple(reversed(prefixes)), value
