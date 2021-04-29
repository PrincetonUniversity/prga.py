# -*- encoding: ascii -*-

from ...netlist.net.util import NetUtils
from ...prog.common import ProgDataValue
from ...util import Object

import re
from collections import namedtuple

import logging
_logger = logging.getLogger(__name__)

class FASMFeatureConn(namedtuple('FASMFeatureConn', 'conn hierarchy', defaults=(None, ))):
    @property
    def type_(self):
        return 'conn'

class FASMFeaturePlain(namedtuple('FASMFeaturePlain', 'feature module hierarchy', defaults=(None, ))):
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
    _none = object()

    def set_bits(self, value, hierarchy = None, *, inplace = False):
        """Update bitstream with the specified ``value`` and ``hierarchy``. Subclass may implement this method to use
        `AbstractBitstreamGenerator.parse_fasm`.

        Args:
            value (`ProgDataValue`):
            hierarchy (`AbstractInstance`):

        Keyword Args:
            inplace (:obj:`bool`): If set, ``value`` may be modified in place.
        """
        raise NotImplementedError

    def parse_feature(self, line):
        """Parse one FASM feature.

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
            return FASMFeatureConn(NetUtils.get_connection(src, sink, skip_validations = True), hierarchy)

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
            return FASMFeaturePlain(last, module, hierarchy)

    def parse_fasm(self, fasm):
        """Parse an FASM file. Calls `AbstractBitstreamGenerator.set_bits`, which must be implemented by a sub-class.

        Args:
            fasm (:obj:`str` or file-like object):
        """
        if isinstance(fasm, str):
            fasm = open(fasm, "r")

        for lineno, line in enumerate(fasm, 1):

            feature = self.parse_feature(line)

            if feature.type_ == "conn":
                if (prog_enable := getattr(feature.conn, "prog_enable", self._none)) is self._none:
                    for net in getattr(feature.conn, "switch_path", tuple()):
                        bus, idx = (net.bus, net.index) if net.net_type.is_bit else (net, 0)
                        self.set_bits(bus.instance.model.prog_enable[idx],
                                bus.instance._extend_hierarchy(above = feature.hierarchy))

                elif prog_enable is None:
                    continue

                else:
                    self.set_bits(prog_enable, feature.hierarchy)

            elif feature.type_ == "param":
                leaf = feature.hierarchy.hierarchy[0]

                if (parameters := getattr(leaf, "prog_parameters", self._none)) is self._none:
                    if (parameters := getattr(leaf.model, "prog_parameters", self._none)) is self._none:
                        continue

                if parameters is None or (bitmap := parameters.get(feature.parameter)) is None:
                    continue

                feature.value.remap(bitmap, inplace = True)
                self.set_bits(feature.value, feature.hierarchy, inplace = True)

            elif feature.type_ == "plain" and feature.feature == "+":
                leaf = feature.hierarchy.hierarchy[0]

                prog_enable = None
                if (feature.module.module_class.is_mode
                        or (prog_enable := getattr(leaf, "prog_enable", self._none)) is self._none):
                    prog_enable = getattr(feature.module, "prog_enable", None)

                if prog_enable is None:
                    continue

                self.set_bits(prog_enable, feature.hierarchy)

            else:
                _logger.warning("[Line {:0>4d}] Unsupported feature: {}".format(lineno, line.strip()))

    def generate_bitstream(self, input_, output):
        """Generate bitstream without storing parsed data.

        Args:
            input_ (:obj:`str` of file-like object):
            output (:obj:`str` of file-like object):
        """
        raise NotImplementedError
