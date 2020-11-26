# -*- encoding: ascii -*-

from ..netlist import ModuleUtils, NetUtils, PortDirection
from ..core.common import ModuleClass, ModuleView, NetClass
from ..renderer import FileRenderer
from ..util import Object, uno
from ..exception import PRGAInternalError

from abc import abstractmethod

__all__ = []

# ----------------------------------------------------------------------------
# -- Programming Circuitry Main Entry ----------------------------------------
# ----------------------------------------------------------------------------
class AbstractProgCircuitryEntry(Object):
    """Abstract base class for programming circuitry entry point."""

    @classmethod
    @abstractmethod
    def new_context(cls):
        """Create a new context.

        Returns:
            `Context`:
        """
        raise NotImplementedError

    @classmethod
    def new_renderer(cls, additional_template_search_paths = tuple()):
        """Create a new file renderer.

        Args:
            additional_template_search_paths (:obj:`Sequence` [:obj:`str` ]): Additional paths where the renderer
                should search for template files

        Returns:
            `FileRenderer`:
        """
        return FileRenderer(*additional_template_search_paths)

    @classmethod
    def buffer_prog_ctrl(cls, context, logical_module = None, _cache = None):
        """Buffer and balance basic programming ctrl signals: ``prog_clk``, ``prog_rst`` and ``prog_done``.

        Args:
            context (`Context`):
            logical_module (`Module`): This method inserts the programming ctrl signals recursively into sub-modules
                of ``logical_module``. It starts with ``context.top`` by default.
            _cache (:obj:`MutableMapping` [:obj:`Hashable`, :obj:`int`]): Mapping from module keys to levels of
                buffering inside the corresponding modules

        Returns:
            :obj:`int`: Levels of buffering of ``prog_rst`` and ``prog_done``
        """
        _cache = uno(_cache, {})

        # short alias
        m = uno(logical_module, context.database[ModuleView.logical, context.top.key])

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
        
        # depending on logical module class, [recursively] buffer signals
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
                buf_rst = ModuleUtils.instantiate(m, context.database[ModuleView.logical, "prga_simple_buf"],
                        "i_buf_prog_rst_l{}".format(l))
                signals.setdefault("prog_rst_l0", buf_rst.pins["Q"]) 
                buf_done = ModuleUtils.instantiate(m, context.database[ModuleView.logical, "prga_simple_bufr"],
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
