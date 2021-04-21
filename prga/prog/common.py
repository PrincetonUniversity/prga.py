# -*- encoding: ascii -*-

from ..netlist import ModuleUtils, NetUtils, PortDirection
from ..core.common import ModuleClass, ModuleView, NetClass
from ..renderer import FileRenderer
from ..util import Object, Enum, uno
from ..exception import PRGAInternalError

from abc import abstractmethod
from collections import namedtuple
from bisect import bisect
from copy import deepcopy

__all__ = ["ProgDataBitmap", "ProgDataValue"]

ProgDataRange = namedtuple("ProgDataRange", "offset length")

class ProgDataBitmap(object):

    __slots__ = ["_bitmap"]
    def __init__(self, *args):
        self._construct(args)

    def __repr__(self):
        return "ProgDataBitmap({})".format(
                ", ".join("[{}+:{}]->[{}+:{}]".format(offset, range_.length, range_.offset, range_.length)
                    for offset, range_ in self._bitmap[:-1]))

    @property
    def length(self):
        """:obj:`int`: Length of the bitmap."""
        return self._bitmap[-1][0]

    def _construct(self, args):
        bitmap, offset = [], 0
        for arg in args:
            arg = ProgDataRange(*arg)
            bitmap.append( (offset, arg) )
            offset += arg.length
        bitmap.append( (offset, None) )
        self._bitmap = tuple(bitmap)

    def query(self, offset, length):
        """Query how ``offset +: length`` should be mapped.

        Args:
            offset (:obj:`int`): Source offset
            length (:obj:`int`):

        Yields:
            `ProgDataRange`: Destination offset and length
        """
        lo = 0
        while length:
            lo = bisect(self._bitmap, (offset + 1, ), lo)
            src, range_ = self._bitmap[lo - 1]
            if range_ is None:
                raise PRGAInternalError("Bit offset ({}) out of bitmap bound ({})".format(offset, src))
            maxlen = min(length, src + range_.length - offset)
            yield ProgDataRange(range_.offset + (offset - src), maxlen)
            length -= maxlen
            offset += maxlen

    def remap(self, bitmap, *, inplace = False):
        """Remap ``self`` onto ``bitmap``.

        Args:
            bitmap (`ProgDataBitmap`):

        keyword Args:
            inplace (:obj:`bool`):

        Returns:
            `ProgDataBitmap`:
        """
        args = []
        for _, srcmap in self._bitmap[:-1]:
            for dstmap in bitmap.query(*srcmap):
                args.append(dstmap)
        if inplace:
            self._construct(args)
            return self
        else:
            return type(self)(*args)

class ProgDataValue(object):

    __slots__ = ["value", "bitmap"]
    def __init__(self, value, *args):
        self.value = value
        self.bitmap = ProgDataBitmap(*args)

    def __repr__(self):
        return "ProgDataValue({}'h{:x}, {})".format(
                self.bitmap.length, self.value, repr(self.bitmap))

    def remap(self, bitmap, *, inplace = False):
        """Remap this value onto ``bitmap``.

        Args:
            bitmap (`ProgDataBitmap`):

        keyword Args:
            inplace (:obj:`bool`):

        Returns:
            `ProgDataValue`:
        """
        v = self if inplace else deepcopy(self)
        v.bitmap.remap(bitmap, inplace = True)
        return v

    def breakdown(self):
        """Break bitmapped value into multiple simple values.

        Yields:
            :obj:`tuple` [:obj:`int`, `ProgDataRange` ]: value and range
        """
        for src, range_ in self.bitmap._bitmap[:-1]:
            yield (self.value >> src) & ((1 << range_.length) - 1), range_

# ----------------------------------------------------------------------------
# -- Programming Circuitry Main Entry ----------------------------------------
# ----------------------------------------------------------------------------
class AbstractProgCircuitryEntry(Object):
    """Abstract base class for programming circuitry entry point."""

    @classmethod
    def buffer_prog_ctrl(cls, context, design_view = None, _cache = None):
        """Buffer and balance basic programming ctrl signals: ``prog_clk``, ``prog_rst`` and ``prog_done``.

        Args:
            context (`Context`):
            design_view (`Module`): This method inserts the programming ctrl signals recursively into sub-modules
                of ``design_view``. It starts with ``context.top`` by default.
            _cache (:obj:`MutableMapping` [:obj:`Hashable`, :obj:`int`]): Mapping from module keys to levels of
                buffering inside the corresponding modules

        Returns:
            :obj:`int`: Levels of buffering of ``prog_rst`` and ``prog_done``
        """
        _cache = uno(_cache, {})

        # short alias
        m = uno(design_view, context.database[ModuleView.design, context.top.key])

        # check if we need to process this module
        if m.module_class in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.prog, ModuleClass.aux):
            return 0
        # check if we've processed this module already
        elif (l := _cache.get(m.key)) is not None:
            return l

        # create programming ctrl signals
        signals = {
                "prog_clk": ModuleUtils.create_port(m, 'prog_clk', 1, PortDirection.input_,
                    is_clock = True, net_class = NetClass.prog),
                "prog_rst": ModuleUtils.create_port(m, 'prog_rst', 1, PortDirection.input_,
                    net_class = NetClass.prog),
                "prog_done": ModuleUtils.create_port(m, 'prog_done', 1, PortDirection.input_,
                    net_class = NetClass.prog),
                }
        
        # depending on design-view module class, [recursively] buffer signals
        if m.module_class.is_slice:
            # no more buffering inside slices, but we need to connect nets
            for i in m.instances.values():
                if (l := cls.buffer_prog_ctrl(context, i.model, _cache)) != 0:
                    raise PRGAInternalError("Unexpected buffering inside {}".format(i))
                for name, port in signals.items():
                    if (pin := i.pins.get(name)) is not None:
                        NetUtils.connect(port, pin)
            _cache[m.key] = 0
            return 0

        elif (m.module_class.is_block or m.module_class.is_routing_box or
                m.module_class.is_tile or m.module_class.is_array):
            # classify instances by the levels of buffers inside them
            levels = [[]]
            for i in m.instances.values():
                l = cls.buffer_prog_ctrl(context, i.model, _cache)
                if l >= len(levels):
                    levels.extend([] for _ in range(l - len(levels) + 1))
                levels[l].append(i)

            # balance buffering to ensure rst/done reaches the leaf modules in the same cycle
            #
            #   NOTES:
            #       The balancing algorithm here is pretty naive. We don't analyze the fanout of the buffering.
            buf_rst_prev, buf_done_prev = None, None
            for l, instances in enumerate(levels):
                # insert buffers
                buf_rst = ModuleUtils.instantiate(m, context.database[ModuleView.design, "prga_simple_buf"],
                        "i_buf_prog_rst_l{}".format(l))
                signals.setdefault("prog_rst_l0", buf_rst.pins["Q"]) 
                buf_done = ModuleUtils.instantiate(m, context.database[ModuleView.design, "prga_simple_bufr"],
                        "i_buf_prog_done_l{}".format(l))
                NetUtils.connect(signals["prog_clk"],    buf_rst.pins["C"])
                NetUtils.connect(signals["prog_clk"],    buf_done.pins["C"])
                NetUtils.connect(signals["prog_rst_l0"], buf_done.pins["R"])

                # connect buffer outputs to sub-module inputs
                for i in instances:
                    if (pin := i.pins.get("prog_clk")) is not None:
                        NetUtils.connect(signals["prog_clk"], pin)
                    if (pin := i.pins.get("prog_rst")) is not None:
                        NetUtils.connect(buf_rst.pins["Q"], pin)
                    if (pin := i.pins.get("prog_done")) is not None:
                        NetUtils.connect(buf_done.pins["Q"], pin)

                # prepare for the next iteration
                if buf_rst_prev is not None:
                    NetUtils.connect(buf_rst.pins["Q"],  buf_rst_prev.pins["D"])
                    NetUtils.connect(buf_done.pins["Q"], buf_done_prev.pins["D"])
                buf_rst_prev, buf_done_prev = buf_rst, buf_done

            # last-level buffering
            NetUtils.connect(signals["prog_rst"],  buf_rst_prev.pins["D"])
            NetUtils.connect(signals["prog_done"], buf_done_prev.pins["D"])

            _cache[m.key] = len(levels)
            return len(levels)

    @classmethod
    @abstractmethod
    def insert_prog_circuitry(cls, context, *args, **kwargs):
        """Insert programming circuitry into the FPGA. This method will be called by the `ProgCircuitryInsertion`
        pass.

        Args:
            context (`Context`):
        """
        raise NotImplementedError

    @classmethod
    def materialize(cls, ctx, inplace = False, **kwargs):
        """Materialize the abstract context to this configuration circuitry type.

        Args:
            ctx (`Context`): An abstract context, or a context previously materialized to another configuration
                circuitry type.
            inplace (:obj:`bool`): If set, the context is modified in-place. Otherwise (by default), ``ctx`` is
                deep-copied before processed

        Keyword Args:
            **kwargs: Additional keyword parameters specific to the programming circuitry type.

        Returns:
            `Context`:
        """
        if not inplace:
            ctx = deepcopy(ctx)
        ctx._prog_entry = cls
        ctx.summary.prog_type = cls.__module__ + '.' + cls.__name__
        return ctx
