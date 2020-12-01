# -*- encoding: ascii -*-

from ..core.common import Position
from ..netlist.net.common import PortDirection
from ..exception import PRGAAPIError
from ..util import Object, uno

from io import StringIO
import re, argparse

__all__ = ['create_argparser', 'docstring_from_argparser',
        'DesignIntf']

def create_argparser(module, *args, **kwargs):
    """Create an argument parser.

    Args:
        module (:obj:`str`): Name of the Python module

    Returns:
        :obj:`argparse.ArgumentParser`:

    Recommended usage: ``parser = create_argparser(__name__, **kwargs)``
    """
    if "__main__" in module:
        return argparse.ArgumentParser(*args, **kwargs)
    else:
        return argparse.ArgumentParser(prog="python -m " + module, *args, **kwargs)

def docstring_from_argparser(parser):
    """Compile the docstring for an executable Python module from the argument parser.
    
    Args:
        parser (:obj:`argparse.ArgumentParser`):

    Returns:
        :obj:`str`:

    Recommended usage: ``__doc__ = docstring_from_argparser(parser)``
    """
    usage = StringIO()
    parser.print_usage(usage)
    return "This is an executable module:\n\n" + usage.getvalue()

class DesignIntf(Object):
    """Interface of the target design to be mapped onto the FPGA.

    Args:
        name (:obj:`str`): Name of the design
    """

    class Port(Object):
        """Port of the targe design to be mapped onto the FPGA.

        Args:
            name (:obj:`str`): Name of the port
            direction (`PortDirection`): Direction of the port
            range_ (:obj:`slice`): Range specifier of the port
        """

        __slots__ = ["name", "direction", "range_", "ioconstraints"]

        def __init__(self, name, direction, range_ = None):
            self.name = name
            self.direction = direction
            self.range_ = range_
            if range_ is None:
                self.ioconstraints = None
            else:
                self.ioconstraints = [None for _ in range(self.width)]

        @property
        def width(self):
            """:obj:`int`: Width of this port."""
            if self.range_ is None:
                return 1
            elif self.range_.step == 1:
                return self.range_.stop - self.range_.start
            else:
                return self.range_.start - self.range_.stop

        def iter_indices(self):
            """Iterate through the indices of this port.

            Yields:
                :obj:`int` or ``None``:
            """
            if self.range_ is None:
                yield None
            else:
                for i in range(self.range_.start, self.range_.stop, self.range_.step):
                    yield i

        def iter_io_constraints(self):
            """Iterate through the indices and IO constraints of this port.

            Yields:
                :obj:`int` or ``None`: Index
                :obj:`tuple` [`Position`, :obj:`int`] or ``None``: Position and subtile ID of the IOB assigned for
                    the bit in the port
            """
            if self.range_ is None:
                yield None, self.ioconstraints
            else:
                for i in range(self.range_.start, self.range_.stop, self.range_.step):
                    yield i, self.ioconstraints[i]

        def get_io_constraint(self, index = None):
            """Get the IO constraint assigned to this port, or a bit in this port.

            Args:
                index (:obj:`int`): Index of a bit in this port. Not applicable if this port is single-bit; Required
                    if this port is multi-bit.

            Returns:
                `Position`, :obj:`int`: Position and subtile ID of the assigned IOB

            Notes:
                ``index`` respects the range specifier, i.e. if ``range_`` is ``7:4``, ``index = 4`` returns the last
                IO constraint.
            """
            if self.range_ is None:
                if index is None:
                    return self.ioconstraints
                else:
                    raise PRGAAPIError("Design port {} is single-bit".format(self.name))
            elif self.range_.step == 1:
                if self.range_.start <= index < self.range_.stop:
                    return self.ioconstraints[index - self.range_.start]
                else:
                    raise PRGAAPIError("Index ({}) out of bound ({}:{})"
                            .format(index, self.range_.start, self.range_.stop - 1))
            else:
                assert self.range_.step == -1
                if self.range_.start >= index > self.range_.stop:
                    return self.ioconstraints[self.range_.start - index]
                else:
                    raise PRGAAPIError("Index ({}) out of bound ({}:{})"
                            .format(index, self.range_.start, self.range_.stop + 1))

        def set_io_constraint(self, position, subtile = 0, index = None):
            """Set IO constraint to this port or a bit in this port.

            Args:
                position (:obj:`tuple` [:obj:`int`, :obj:`int`]): Position of the IOB
                subtile (:obj:`int`): Subtile ID of the IOB
                index (:obj:`int`): Index of a bit in this port. Not applicable if this port is single-bit; Required
                    if this port is multi-bit.
            Notes:
                ``index`` respects the range specifier, i.e. if ``range_`` is ``7:4``, ``index = 4`` returns the last
                IO constraint.
            """
            if self.range_ is None:
                if index is None:
                    self.ioconstraints = Position(*position), subtile
                else:
                    raise PRGAAPIError("Design port {} is single-bit".format(self.name))
            elif self.range_.step == 1:
                if self.range_.start <= index < self.range_.stop:
                    self.ioconstraints[index - self.range_.start] = Position(*position), subtile
                else:
                    raise PRGAAPIError("Index ({}) out of bound ({}:{})"
                            .format(index, self.range_.start, self.range_.stop - 1))
            else:
                assert self.range_.step == -1
                if self.range_.start >= index > self.range_.stop:
                    self.ioconstraints[self.range_.start - index] = Position(*position), subtile
                else:
                    raise PRGAAPIError("Index ({}) out of bound ({}:{})"
                            .format(index, self.range_.start, self.range_.stop + 1))

    __slots__ = ["name", "ports", "__dict__"]
    _port_reprog = re.compile("^(?P<bus>.*)\[(?P<index>\d+)\]$")

    def __init__(self, name):
        self.name = name
        self.ports = {}

    def add_port(self, name, direction, range_ = None):
        """Add a port to this interface.

        Args:
            name (:obj:`str`): Name of the port
            direction (`PortDirection`): Direction of the port
            range_ (:obj:`int`): [Overloaded] Width of the port. When using a single :obj:`int`, the port is assumed
                to be equivalent to Verilog ``{input|output} [0:{range_ - 1}] {name}``.
            range_ (:obj:`slice`): [Overloaded] Range specifier of the port. ``step`` must be ``None``, ``1`` or
                ``-1``. When using a :obj:`slice` object, the port is equivalent to Verilog ``{input|output}
                [{range_.start}:{range_.stop - range_.step}] {name}``. Note the extra ``step`` caused by the
                difference between Python and Verilog range specification conventions \(i.e. ``7:4`` in Verilog is
                equivalent to ``7:3:-1`` in Python, and ``2:4`` in Verilog is equivalent to ``2:5`` in Python\).
            range_ (``None``): [Overloaded] When using ``None``, this port is treated as single-bit, i.e. equivalent
                to Verilog ``{input|output} {name}``.

        Returns:
            `DesignIntf.Port`: The created port
        """
        if name in self.ports:
            raise PRGAAPIError("Duplicate port name: {}".format(name))

        if range_ is None:
            port = self.ports[name] = self.Port(name, direction, range_)
            return port

        elif isinstance(range_, int):
            if range_ > 0:
                port = self.ports[name] = self.Port(name, direction, slice(0, range_, 1))
                return port

        elif isinstance(range_, slice):
            if range_.stop > range_.start and range_.step in (None, 1):
                port = self.ports[name] = self.Port(name, direction,
                        slice(range_.start, range_.stop, 1))
                return port

            elif range_.stop < range_.start and range_.step in (None, -1):
                port = self.ports[name] = self.Port(name, direction,
                        slice(range_.start, range_.stop, -1))
                return port

        raise PRGAAPIError("Unsupported range specifier: {}".format(range_))

    @classmethod
    def parse_eblif(cls, f):
        """Parse a synthesized eblif file for the target design interface.

        Args:
            f (:obj:`str` or a file-like object): File name, or a file-like object
        """
        if isinstance(f, str):
            f = open(f, "r")
        design = cls(None)

        for line in f:
            tokens = line.split()
            if not tokens:
                continue

            elif tokens[0] == ".model":
                if design.name is None:
                    design.name = tokens[1]
                else:
                    raise PRGAAPIError("Multiple models found in EBLIF.\n"
                            "\tPossible reason: synthesis ran without `flatten`")

            elif tokens[0] in (".inputs",  ".outputs"):
                bus, range_ = None, None
                direction = PortDirection.input_ if tokens[0] == ".inputs" else PortDirection.output

                for bit in tokens[1:]:
                    cur_bus, idx = bit, None
                    if (matched := cls._port_reprog.match(bit)):
                        cur_bus, s_idx = matched.group("bus", "index")
                        idx = int(s_idx)

                    if cur_bus == bus:
                        if idx is None:
                            raise PRGAAPIError("Non-continuous range specifier found: {}".format(bit))
                        elif idx == range_.stop + 1 and range_.stop >= range_.start:
                            range_ = slice(range_.start, idx, 1)
                        elif idx == range_.stop - 1 and range_.stop <= range_.start:
                            range_ = slice(range_.start, idx, -1)
                        else:
                            raise PRGAAPIError("Non-continuous range specifier found: {}".format(bit))
                        continue

                    if bus is not None:
                        if range_ is not None:
                            if range_.step in (None, 1):
                                design.ports[bus] = cls.Port(bus, direction,
                                        slice(range_.start, range_.stop + 1, 1))
                            else:
                                design.ports[bus] = cls.Port(bus, direction,
                                        slice(range_.start, range_.stop - 1, -1))
                        else:
                            design.ports[bus] = cls.Port(bus, direction, range_)

                    if cur_bus in design.ports:
                        raise PRGAAPIError("Duplicate port name: {}".format(cur_bus))
                    elif idx is None:
                        bus, range_ = cur_bus, None
                    else:
                        bus, range_ = cur_bus, slice(idx, idx)

                if bus is not None:
                    if range_ is not None:
                        if range_.step in (None, 1):
                            design.ports[bus] = cls.Port(bus, direction,
                                    slice(range_.start, range_.stop + 1, 1))
                        else:
                            design.ports[bus] = cls.Port(bus, direction,
                                    slice(range_.start, range_.stop - 1, -1))
                    else:
                        design.ports[bus] = cls.Port(bus, direction, range_)

        return design
