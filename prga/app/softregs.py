# -*- encoding: ascii -*-

from ..netlist import PortDirection, Module, ModuleUtils
from ..util import Object, Enum
from ..exception import PRGATypeError

from collections import namedtuple

__all__ = ['SoftRegType', 'SoftReg', 'SoftRegIntf']

# ----------------------------------------------------------------------------
# -- Soft Register Type ------------------------------------------------------
# ----------------------------------------------------------------------------
class SoftRegType(Enum):
    """Soft register types."""

    const       = 0     #: read-only registers with constant value
    readonly    = 1     #: read-only registers inside the kernel
    readwrite   = 2     #: read-write registers which hold the value once written
    pulse       = 3     #: read-write registers which auto-resets after one cycle (read always return rstval)
    echo        = 4     #: read-write registers which auto-sync with the echo from the kernel after one cycle

# ----------------------------------------------------------------------------
# -- Soft Register Definition ------------------------------------------------
# ----------------------------------------------------------------------------
class SoftReg(Object):
    """Soft register definition.

    Args:
        name (:obj:`str`): Name of the register
        type_ (`SoftRegType`): Type of the register
        addr (:obj:`int`): Base address of the register in bytes
        width (:obj:`int`): Number of bits of this register
        bytewidth (:obj:`int`): Number of bytes that this register takes in the address space. Always a power of 2
        rstval (:obj:`int`): Reset value
    """

    __slots__ = ["_name", "_type", "_addr", "_width", "_bytewidth", "_rstval"]
    def __init__(self, name, type_, addr, width, bytewidth, rstval):
        self._name = name
        self._type = type_
        self._addr = addr
        self._width = width
        self._bytewidth = bytewidth
        self._rstval = rstval

    @property
    def name(self):
        """:obj:`str`: Name of the register."""
        return self._name

    @property
    def type_(self):
        """`SoftRegType`: Type of the register."""
        return self._type

    @property
    def addr(self):
        """:obj:`int`: Base address of the register in bytes."""
        return self._addr

    @property
    def width(self):
        """:obj:`int`: Number of bits of this register."""
        return self._width

    @property
    def bytewidth(self):
        """:obj:`int`: Number of bytes that this register takes in the address space. Always a power of 2."""
        return self._bytewidth

    @property
    def rstval(self):
        """:obj:`int`: Reset value."""
        return self._rstval

# ----------------------------------------------------------------------------
# -- Soft Register Interface -------------------------------------------------
# ----------------------------------------------------------------------------
class SoftRegIntf(Object):
    """Soft register interface.

    Args:
        addr_width (:obj:`int`): Number of bits in the address. This sets the maximum address space
        align (:obj:`int`): Byte alignment. Must be power of 2. This also sets the maximum width of all soft registers
    """

    __slots__ = ['addr_width', 'align', 'addrspace', 'regs']
    def __init__(self, addr_width = 11, align = 8):
        if addr_width <= 0:
            raise PRGATypeError('addr_width', 'positive integer')

        if align <= 0 or (align & (align - 1) != 0):
            raise PRGATypeError('align', 'positive integer and power of 2')

        self.addr_width = addr_width
        self.align = align
        self.addrspace = []
        self.regs = {}

    def _add_softreg(self, type_, name, addr, width, rstval = 0):
        """Add one soft register to the interface.

        Args:
            type_ (`SoftRegType`): Type of the soft register
            name (:obj:`str`): Name of the soft register
            addr (:obj:`int`): Base address of the register in bytes. Automatically allocated if left unspecified
            width (:obj:`int`): Number of the bits of the register. Default to 8bits x alignment
            rstval (:obj:`int`): Reset value of the register

        Returns:
            `SoftReg`: The created soft register
        """

        # check soft register name
        if name in self.regs:
            raise PRGAAPIError("Duplicated soft register named '{}'".format(name))

        # get soft register bit width
        if width is None:
            width = self.align * 8
        elif width <= 0 or width > self.align * 8:
            raise PRGATypeError('width', '0 < `width` <= align x8')

        # calculate soft register byte width (in the address space)
        bytewidth = self.align
        while bytewidth:
            if (bytewidth // 2) * 8 < width:
                break
            bytewidth //= 2

        # get soft register address
        if addr is None:
            addr = ((len(self.addrspace) // bytewidth) + (1 if len(self.addrspace) % bytewidth > 0 else 0)) * bytewidth
        elif addr < 0:
            raise PRGATypeError('addr', 'non-negative integer')
        elif addr % bytewidth != 0:
            raise PRGATypeError('addr', 'non-negative integer and multiple of {} (due to alignment)'
                    .format(bytewidth))
        else:
            for i in range(bytewidth):
                if (addr + i) < len(self.addrspace) and (conflict := self.addrspace[addr + i]) is not None:
                    raise PRGAAPIError("Address space conflict. Soft register '{}' already using address 0x{:x}"
                            .format(conflict.name, addr + i))

        # increase address space if necessary
        if addr + bytewidth >= len(self.addrspace):
            if addr + bytewidth >= 2 ** self.addr_width:
                raise PRGAAPIError("Address 0x{:x} - 0x{:x} exceeds address space [0:{}]"
                        .format(addr, addr + bytewidth, 2 ** self.addr_width))
            self.addrspace.extend( [None] * (addr + bytewidth - len(self.addrspace)) )

        # add this register to the address space and the register map
        reg = self.regs[name] = SoftReg(name, type_, addr, width, bytewidth, rstval)
        for i in range(bytewidth):
            self.addrspace[addr + i] = reg

    def add_const_softreg(self, name, value = 0, *, addr = None, width = None):
        """Add a `SoftRegType.const` register.

        Args:
            name (:obj:`str`): Name of the register
            value (:obj:`int`): Value of the register

        Keyword Args:
            addr (:obj:`int`): Base address of the register in bytes. Automatically allocated if left unspecified
            width (:obj:`int`): Number of the bits of the register. Default to 8bits x alignment

        Returns:
            `SoftReg`: The created soft register
        """
        return self._add_softreg(SoftRegType.const, name, addr, width, value)

    def add_readonly_softreg(self, name, *, addr = None, width = None):
        """Add a `SoftRegType.readonly` register.

        Args:
            name (:obj:`str`): Name of the register

        Keyword Args:
            addr (:obj:`int`): Base address of the register in bytes. Automatically allocated if left unspecified
            width (:obj:`int`): Number of the bits of the register. Default to 8bits x alignment

        Returns:
            `SoftReg`: The created soft register
        """
        return self._add_softreg(SoftRegType.readonly, name, addr, width)

    def add_readwrite_softreg(self, name, *, addr = None, width = None, rstval = 0):
        """Add a `SoftRegType.readwrite` register.

        Args:
            name (:obj:`str`): Name of the register

        Keyword Args:
            addr (:obj:`int`): Base address of the register in bytes. Automatically allocated if left unspecified
            width (:obj:`int`): Number of the bits of the register. Default to 8bits x alignment
            rstval (:obj:`int`): Reset value of the register

        Returns:
            `SoftReg`: The created soft register
        """
        return self._add_softreg(SoftRegType.readwrite, name, addr, width, rstval)

    def add_pulse_softreg(self, name, rstval = 0, *, addr = None, width = None):
        """Add a `SoftRegType.pulse` register.

        Args:
            name (:obj:`str`): Name of the register
            rstval (:obj:`int`): Reset value of the register

        Keyword Args:
            addr (:obj:`int`): Base address of the register in bytes. Automatically allocated if left unspecified
            width (:obj:`int`): Number of the bits of the register. Default to 8bits x alignment

        Returns:
            `SoftReg`: The created soft register
        """
        return self._add_softreg(SoftRegType.pulse, name, addr, width, rstval)

    def add_echo_softreg(self, name, *, addr = None, width = None, rstval = 0):
        """Add a `SoftRegType.echo` register.

        Args:
            name (:obj:`str`): Name of the register

        Keyword Args:
            addr (:obj:`int`): Base address of the register in bytes. Automatically allocated if left unspecified
            width (:obj:`int`): Number of the bits of the register. Default to 8bits x alignment
            rstval (:obj:`int`): Reset value of the register

        Returns:
            `SoftReg`: The created soft register
        """
        return self._add_softreg(SoftRegType.echo, name, addr, width, rstval)

    def create_module(self):
        """Create a `Module` object implementing this soft register interface.

        Returns:
            `Module`:
        """

        # create the module
        m = Module("prga_app_softregs", softregs = self)

        # create ports
        # - basic ports
        ModuleUtils.create_port(m, "clk",               1,                  PortDirection.input_, is_clock = True)
        ModuleUtils.create_port(m, "rst_n",             1,                  PortDirection.input_)
        ModuleUtils.create_port(m, "softreg_req_rdy",   1,                  PortDirection.output)
        ModuleUtils.create_port(m, "softreg_req_val",   1,                  PortDirection.input_)
        ModuleUtils.create_port(m, "softreg_req_addr",  self.addr_width,    PortDirection.input_)
        ModuleUtils.create_port(m, "softreg_req_strb",  self.align,         PortDirection.input_)
        ModuleUtils.create_port(m, "softreg_req_data",  self.align * 8,     PortDirection.input_)
        ModuleUtils.create_port(m, "softreg_resp_rdy",  1,                  PortDirection.input_)
        ModuleUtils.create_port(m, "softreg_resp_val",  1,                  PortDirection.output)
        ModuleUtils.create_port(m, "softreg_resp_data", self.align * 8,     PortDirection.output)

        # create register variable ports
        for name, r in self.regs.items():
            if r.type_ in (SoftRegType.readonly, SoftRegType.echo):
                ModuleUtils.create_port(m, "var_{}_i".format(name), r.width, PortDirection.input_)
            if r.type_ in (SoftRegType.const, SoftRegType.readwrite, SoftRegType.pulse, SoftRegType.echo):
                ModuleUtils.create_port(m, "var_{}_o".format(name), r.width, PortDirection.output)

        # TODO: instantiate `prga_valrdy_buf`
        #       need to decide how to organize modules

        # return the module
        return m
