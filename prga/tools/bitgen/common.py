# -*- encoding: ascii -*-

from ...netlist.net.util import NetUtils
from ...prog.common import ProgDataValue
from ...util import Object

import re
from collections import namedtuple

class FASMFeatureConn(namedtuple('FASMFeatureConn', 'src sink hierarchy', defaults=(None, ))):
    @property
    def type_(self):
        return 'conn'

class FASMFeaturePlain(namedtuple('FASMFeaturePlain', 'feature hierarchy', defaults=(None, ))):
    @property
    def type_(self):
        return 'plain'

class FASMFeatureParam(namedtuple('FASMFeatureParam', 'parameter value hierarchy', defaults=(None, ))):
    @property
    def type_(self):
        return 'param'

class AbstractBitstreamGenerator(Object):
    """Abstract base class for bitstream generators.

    Args:
        context (`Context`):
    """

    __slots__ = ['context']

    def __init__(self, context):
        self.context = context

    _reprog_param = re.compile("(?P<name>\w+)\[(?P<high>\d+):(?P<low>\d+)\]")
    _reprog_value = re.compile("(?P<width>\d+)'(?P<notation>[bdhBDH])(?P<value>[a-fA-F0-9]+)")

    def parse_feature(self, line):
        """Parse FASM features.

        Args:
            line (:obj:`str`):

        Returns:
            `FASMFeatureConn` or `FASMFeaturePlain` or `FASMFeatureParam`:
        """
        # tokenize
        tokens, quoted = [], None
        for token in line.strip().split('.'):
            if not quoted:
                if not token.startswith('{'):
                    tokens.append(token)
                elif not token.endswith('}'):
                    quoted = token[1:]
                else:
                    tokens.append(token[1:-1])
            else:
                if token.endswith('}'):
                    tokens.append(quoted + '.' + token[:-1])
                    quoted = None
                else:
                    quoted += '.' + token

        # hierarchy
        module, instances = self.context.top, []
        for token in tokens[:-1]:

            # handle mode selection
            if token.startswith('@'):
                module = module.modes[token[1:]]

            # get instance
            else:
                instances.append(instance := module.children[token])
                module = instance.model

        hierarchy = (instances[0]._extend_hierarchy(below = tuple(reversed(instances[1:])))
                if instances else None)

        # process the last token
        last = tokens[-1]
        if len(subtokens := last.split('->')) > 1:
            src, sink = map(lambda n: NetUtils._dereference(module, n, byname = True), subtokens)
            return FASMFeatureConn(src, sink, hierarchy)

        elif len(subtokens := last.split('=')) > 1:
            # parameter and range specifier
            obj = self._reprog_param.match(subtokens[0])
            name, high, low = obj.group( "name", "high", "low" )

            # value
            obj = self._reprog_value.match(subtokens[1])
            width, notation, value = obj.group( "width", "notation", "value" )
            value = int(value, {"b": 2, "d": 10, "h": 16, "B": 2, "D": 10, "H": 16}[notation])

            return FASMFeatureParam(name, ProgDataValue(value, (int(low), int(width))), hierarchy)

        else:
            return FASMFeaturePlain(last, hierarchy)

    def generate_verif(self, fasm, output, *args, **kwargs):
        """Generate bitstream for verification purpose."""
        raise NotImplementedError("Cannot generate bitstream for verification purpose")

    def generate_raw(self, fasm, output, *args, **kwargs):
        """Generate raw bitstream."""
        raise NotImplementedError("Cannot generate raw bitstream")
