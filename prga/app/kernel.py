# -*- encoding: ascii -*-

from .util import AppUtils
from ..netlist import Module, ModuleUtils
from ..util import Object, Enum
from ..exception import PRGAAPIError

__all__ = ['KernelBuilder']

# ----------------------------------------------------------------------------
# -- Accelerator Kernel Builder ----------------------------------------------
# ----------------------------------------------------------------------------
class KernelBuilder(Object):
    """Builder for the kernel module of an accelerator.

    Args:
        context (`AppContext`): The context of the builder
        module (`Module`): The module to be built
    """

    __slots__ = ["_context", "_module"]
    def __init__(self, context, module):
        self._context = context
        self._module = module

    @property
    def module(self):
        """`Module`: The module being built."""
        return self._module

    @classmethod
    def new(cls, name, verilog_src, **kwargs):
        """Create a new kernel module.

        Args:
            name (:obj:`str`): Name of the kernel module
            verilog_src (:obj:`str`): Source file of the kernel

        Keyword Args:
            **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of this object
                and accessible as dynamic attributes

        Returns:
            module (`Module`):
        """

        return Module(name,
                verilog_src = verilog_src,
                portgroups = {},
                **kwargs)

    def create_port(self, name, width, direction, *, is_clock = False, **kwargs):
        """Create a port in the kernel module being built.

        Args:
            name (:obj:`str`): Name of the port
            width (:obj:`int`): Number of bits in the port
            direction (`PortDirection` or :obj:`str`): Direction of the port, valid arguments are "input" and "output"

        Keyword Args:
            is_clock (:obj:`bool`): Mark this port as a clock
            **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of the created port
                and accessible as dynamic attributes

        Returns:
            `Port`: The created port
        """
        return ModuleUtils.create_port(self._module, name, width, direction, is_clock = is_clock, **kwargs)

    def create_portgroup(self, type_, id_ = None, **kwargs):
        """Create a port group.

        Args:
            type_ (:obj:`str`): Supported types are 'syscon', 'axi4r' and 'axi4w'
            id_ (:obj:`str`): ID of this port group

        Keyword Args:
            **kwargs: Arguments for creating the port group
        """

        if type_ == "syscon":

            if id_ in self._module.portgroups.setdefault("syscon", {}):
                raise PRGAAPIError("Port group (syscon) with ID ({}) already exists".format(repr(id_)))

            self._module.portgroups["syscon"][id_] = AppUtils.create_syscon_ports(self._module, **kwargs)

        elif type_ == "axi4r":

            if id_ in self._module.portgroups.setdefault("axi4r", {}):
                raise PRGAAPIError("Port group (axi4r) with ID ({}) already exists".format(repr(id_)))

            if (addr_width := kwargs.pop("addr_width", None)) is None:
                raise PRGAAPIError("Missing required argument for port group (axi4r): addr_width")
            elif (data_bytes_log2 := kwargs.pop("data_bytes_log2", None)) is None:
                raise PRGAAPIError("Missing required argument for port group (axi4r): data_bytes_log2")

            self._module.portgroups["axi4r"][id_] = AppUtils.create_axi4r_ports(self._module,
                    addr_width, data_bytes_log2, **kwargs)

        elif type_ == "axi4w":

            if id_ in self._module.portgroups.setdefault("axi4w", {}):
                raise PRGAAPIError("Port group (axi4w) with ID ({}) already exists".format(repr(id_)))

            if (addr_width := kwargs.pop("addr_width", None)) is None:
                raise PRGAAPIError("Missing required argument for port group (axi4w): addr_width")
            elif (data_bytes_log2 := kwargs.pop("data_bytes_log2", None)) is None:
                raise PRGAAPIError("Missing required argument for port group (axi4w): data_bytes_log2")

            self._module.portgroups["axi4w"][id_] = AppUtils.create_axi4w_ports(self._module,
                    addr_width, data_bytes_log2, **kwargs)

        elif type_ == "yami":

            if id_ in self._module.portgroups.setdefault("yami", {}):
                raise PRGAAPIError("Port group (yami) with ID ({}) already exists".format(repr(id_)))

            if (intf := kwargs.pop("intf", None)) is None:
                raise PRGAAPIError("Missing required argument for port group (yami): intf")

            self._module.portgroups["yami"][id_] = AppUtils.create_yami_ports(self._module,
                    intf, **kwargs)

        else:
            raise NotImplementedError("Unsupported type: {}".format(type_))
