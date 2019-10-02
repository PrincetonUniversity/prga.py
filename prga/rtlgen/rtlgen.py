# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.util import Object
from prga.exception import PRGAInternalError

import os
import jinja2 as jj

__all__ = ['NetSlice', 'VerilogGenerator']

# ----------------------------------------------------------------------------
# -- Net Slice ---------------------------------------------------------------
# ----------------------------------------------------------------------------
class NetSlice(Object):
    """Helper class used to slice port/pin buses.

    Args:
        type_ (`NetType`): type of this slice
        bus (`AbstractBus` or `ConstNetType`): the original bus to be sliced, or the constant net type
        start (:obj:`int`): lower index of this slice
        stop (:obj:`int`): higher index of this slice
    """

    __slots__ = ['type_', 'bus', 'start', 'stop']
    def __init__(self, type_, bus, start, stop):
        self.type_ = type_
        self.bus = bus
        self.start = start
        self.stop = stop

    @classmethod
    def CreateOne(cls, bit):
        """Create a slice from a single bit.

        Args:
            bit (`AbstractBit`):
        
        Returns:
            `NetSlice`:
        """
        if bit.net_type.is_const:
            return cls(bit.net_type, bit.const_net_type, 0, 1)
        else:
            return cls(bit.net_type, bit.bus, bit.index, bit.index + 1)

    @classmethod
    def Create(cls, bits):
        """Create a list of slices for a list of bits.

        Args:
            bits (:obj:`Iterable` [`AbstractGenericBit` ]):

        Returns:
            :obj:`list` [`NetSlice` ]:
        """
        l, bundle = [], None
        for bit in bits:
            if bundle is None:
                bundle = cls.CreateOne(bit)
            elif bundle.type_ is bit.net_type:
                if ((bit.net_type.is_const and bit.const_net_type is bundle.bus)
                        or (not bit.net_type.is_const and bit.index == bundle.stop and bit.bus is bundle.bus)):
                    bundle.stop = bundle.stop + 1
                else:
                    l.append(bundle)
                    bundle = cls.CreateOne(bit)
            else:
                l.append(bundle)
                bundle = cls.CreateOne(bit)
        l.append(bundle)
        return l

    @property
    def width(self):
        return self.stop - self.start

# ----------------------------------------------------------------------------
# -- Verilog Generator -------------------------------------------------------
# ----------------------------------------------------------------------------
class VerilogGenerator(object):
    """Verilog generator.
    
    Args:
        additional_template_search_paths (:obj:`Sequence` [:obj:`str` ]): A sequence of additional paths which contain
            verilog source files or verilog templates
    """

    def __init__(self, additional_template_search_paths = tuple()):
        search_paths = [os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')]
        search_paths.extend(additional_template_search_paths)
        self.env = jj.Environment(loader = jj.FileSystemLoader(search_paths))

    def bitslice2verilog(self, slice_):
        if slice_.type_.is_const:
            return str(slice_.width) + "'b" + slice_.bus.case("x", "0", "1")
        elif slice_.type_.is_port:
            if slice_.start == 0 and slice_.stop == slice_.bus.width:
                return slice_.bus.name
            elif slice_.width == 1:
                return '{}[{}]'.format(slice_.bus.name, slice_.start)
            else:
                return '{}[{}:{}]'.format(slice_.bus.name, slice_.stop - 1, slice_.start)
        else:
            if slice_.start == 0 and slice_.stop == slice_.bus.width:
                return '{}__{}'.format(slice_.bus.parent.name, slice_.bus.name)
            elif slice_.width == 1:
                return '{}__{}[{}]'.format(slice_.bus.parent.name, slice_.bus.name, slice_.start)
            else:
                return '{}__{}[{}:{}]'.format(slice_.bus.parent.name, slice_.bus.name, slice_.stop - 1, slice_.start)

    def bits2verilog(self, bits):
        slices = NetSlice.Create(bits)
        if len(slices) == 1:
            if slices[0].type_.is_const and slices[0].bus.is_unconnected:
                return ''
            else:
                return self.bitslice2verilog(slices[0])
        else:
            return '{{{}}}'.format(', '.join(map(self.bitslice2verilog, reversed(slices))))

    def generate_module(self, f, module):
        template = self.env.get_template(module.verilog_template)
        parameters = {
                'module': module,
                'bits2verilog': self.bits2verilog,
                'itervalues': itervalues,
                'iteritems': iteritems,
                }
        template.stream(parameters).dump(f, encoding='ascii')
