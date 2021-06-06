# -*- encoding: ascii -*-

from .util import AppUtils
from ..netlist import Module, ModuleUtils
from ..util import Object, Enum
from ..exception import PRGATypeError, PRGAAPIError

from collections import namedtuple
import os, logging

_logger = logging.getLogger(__name__)

__all__ = ['SoftRegSpace']

# ----------------------------------------------------------------------------
# -- Soft Register Type ------------------------------------------------------
# ----------------------------------------------------------------------------
class SoftRegType(Enum):
    """Soft register types."""

    reserved    = -1    #: not usable

    const       = 0     #: read-only registers with constant value
    kernel      = 1     #: read-only registers inside the kernel
    rdempty     = 2     #: read-only registers inside the kernel with FIFO-like hand-shake
    rdempty_la  = 3     #: read-only registers inside the kernel with lookahead FIFO-like hand-shake
    # bar         = 4   #: burnt-after-read (deprecated)
    # cbl         = 5   #: call-by-load. assert output until ack'ed (deprecated)
    cbl_2stage  = 6     #: call-by-load. 2-stage ack (output ack, then done signal)

    basic       = 100   #: read-write registers that hold the value once written
    pulse       = 101   #: read-write registers that auto-reset after one cycle (read always return rstval)
    pulse_ack   = 102   #: read-write registers that block until kernel acks and auto-reset (read always return rstval)
    decoupled   = 103   #: write to kernel and read from kernel
    # busywait    = 104 #: read-write registers. write is blocked until busy is deasserted. read returns busy value
                        # (deprecated)

    wrfull      = 200   #: write-only registers inside the kernel with FIFO-like hand-shake. read returns full bit

    hsr_ififo       = 300   #: hardware-sync'ed input FIFO
    hsr_ofifo       = 301   #: hardware-sync'ed output FIFO
    hsr_tfifo       = 302   #: hardware-sync'ed output token FIFO
    # hsr_plain       = 303   #: hardware-sync'ed plain registers

    hsr_kernel      = 320   #: hardware-sync'ed kernel register         (use one plain HSR)
    hsr_basic       = 321   #: hardware-sync'ed basic register          (use one plain HSR)

# ----------------------------------------------------------------------------
# -- Soft Register Definition ------------------------------------------------
# ----------------------------------------------------------------------------
class SoftReg(namedtuple('SoftReg', 'name type_ addr width bytewidth rstval')):
    """Soft register definition.

    Args:
        name (:obj:`str`): Name of the register
        type_ (`SoftRegType` or :obj:`str`): Type of the register
        addr (:obj:`int`): Base address of the register in bytes
        width (:obj:`int`): Number of bits of this register
        bytewidth (:obj:`int`): Number of bytes that this register takes in the address space. Always a power of 2
        rstval (:obj:`int`): Reset value
    """

    pass

# ----------------------------------------------------------------------------
# -- Soft Register Space -----------------------------------------------------
# ----------------------------------------------------------------------------
class SoftRegSpace(Object):
    """Soft register space.

    Args:
        intf (`FabricIntf`): Fabric interface that the space is implemented for
    """

    __slots__ = ['intf', 'regs', 'addrspace']

    _valid_types = {
            "softreg": set([
                SoftRegType.const,
                SoftRegType.kernel,
                SoftRegType.rdempty,
                SoftRegType.rdempty_la,
                SoftRegType.cbl_2stage,
                SoftRegType.basic,
                SoftRegType.pulse,
                SoftRegType.pulse_ack,
                SoftRegType.decoupled,
                SoftRegType.wrfull,
                ]),

            "rxi": set([
                SoftRegType.const,
                SoftRegType.kernel,
                SoftRegType.rdempty,
                SoftRegType.rdempty_la,
                SoftRegType.cbl_2stage,
                SoftRegType.basic,
                SoftRegType.pulse,
                SoftRegType.pulse_ack,
                SoftRegType.decoupled,
                SoftRegType.wrfull,
                SoftRegType.hsr_ififo,
                SoftRegType.hsr_ofifo,
                SoftRegType.hsr_tfifo,
                # SoftRegType.hsr_plain,
                SoftRegType.hsr_kernel,
                SoftRegType.hsr_basic,
                ]),
            }

    def __init__(self, intf):
        self.intf = intf
        self.regs = {}
        self.addrspace = []

        if self.intf.is_softreg:
            pass

        elif self.intf.is_rxi:
            bw = 1 << self.intf.data_bytes_log2

            # control registers
            self.addrspace  = [SoftReg('*reserved*', SoftRegType.reserved, i, 8 * bw, bw, 0) for i in range(32)]

            # HSR: input fifo, output data fifo, output token fifo
            self.addrspace += [None for i in range(12)] 

            # HSR: output token fifo (alternative non-blocking loads)
            self.addrspace += [SoftReg('*reserved*', SoftRegType.reserved, i, 8 * bw, bw, 0) for i in range(44, 48)] 

            # HSR: plain
            self.addrspace += [None for i in range(16)] 

        else:
            raise NotImplementedError("Unsupported interface type: {}".format(repr(self.intf)))

    @classmethod
    def _register_cells(cls, context):

        for type_ in (
                SoftRegType.const,
                SoftRegType.kernel,
                SoftRegType.rdempty,
                SoftRegType.rdempty_la,
                SoftRegType.cbl_2stage,
                SoftRegType.basic,
                SoftRegType.pulse,
                SoftRegType.pulse_ack,
                SoftRegType.decoupled,
                SoftRegType.wrfull,
                ):

            name = "prga_app_softreg_" + type_.name
            context.add_module(Module(name,
                verilog_template = "softregs/" + name + ".v",
                verilog_dep_headers = ("prga_app_softregs.vh", )))

        for type_ in (
                SoftRegType.hsr_ififo,
                SoftRegType.hsr_ofifo,
                SoftRegType.hsr_tfifo,
                SoftRegType.hsr_kernel,
                SoftRegType.hsr_basic,
                ):

            name = "prga_app_softreg_" + type_.name
            context.add_module(Module(name,
                verilog_template = "rxi/" + name + ".v",
                verilog_dep_headers = ("prga_app_softregs.vh", )))

    def _allocate_rxi(self, type_):
        valid_range = type_.case(
                hsr_ififo   = (32, 36),
                hsr_ofifo   = (36, 40),
                hsr_tfifo   = (40, 44),
                # hsr_plain   = (48, 64),
                hsr_kernel  = (48, 64),
                hsr_basic   = (48, 64),
                default     = None,
                )

        if valid_range is not None:
            for i in range(*valid_range):
                if self.addrspace[i] is None:
                    return i
            return None

        else:
            addr = len(self.addrspace)
            if addr >= 1 << (self.intf.addr_width - self.intf.data_bytes_log2):
                return None
            else:
                return addr

    def _filter_registers(self, include_types = None, exclude_types = None):
        """Filter registers (for Jinja2 rendering).

        Args:
            include_types (:obj:`Container` [`SoftRegType` or :obj:`str` ]):
            exclude_types (:obj:`Container` [`SoftRegType` or :obj:`str` ]):

        Returns:
            `Container` [`SoftReg`]:
        """
        if include_types is not None:
            include_types = set( SoftRegType.construct( t ) for t in include_types )

        if exclude_types is not None:
            exclude_types = set( SoftRegType.construct( t ) for t in exclude_types )

        l = []
        for r in self.regs.values():
            if include_types is not None and r.type_ not in include_types:
                continue
            elif exclude_types is not None and r.type_ in exclude_types:
                continue
            l.append( r )
        return l

    def create_softreg(self, type_, name, rstval = 0, *,
            addr = None, width = None, dont_promote = False):
        """Create one soft register in the group.

        Args:
            type_ (`SoftRegType` or :obj:`str`): Type of the soft register
            name (:obj:`str`): Name of the soft register
            rstval (:obj:`int`): Reset value of the register

        Keyword Args:
            addr (:obj:`int`): Base address of the register. Automatically allocated if left unspecified
            width (:obj:`int`): Number of the bits of the register. Default to 8bits x alignment
            dont_promote (:obj:`bool`): If set, soft registers will not be promoted to their hardware-sync'ed
                counterparts

        Returns:
            `SoftReg`: The created soft register
        """

        # check soft register name
        if name in self.regs:
            raise PRGAAPIError("Duplicated soft register named '{}'".format(name))

        # get soft register bit width
        if width is None:
            width = 8 << self.intf.data_bytes_log2
        elif width <= 0 or width > (8 << self.intf.data_bytes_log2):
            raise PRGATypeError('width', '0 < `width` <= align({}) x8'.format(1 << self.intf.data_bytes_log2))

        # calculate soft register byte width (in the address space)
        bytewidth = 1 << self.intf.data_bytes_log2
        while bytewidth:
            nextbytewidth = bytewidth // 2
            if nextbytewidth * 8 < width:
                break
            bytewidth = nextbytewidth

        # validate register type
        type_ = SoftRegType.construct(type_)
        if (valid_types := self._valid_types.get(self.intf.type_)) is None:
            raise NotImplementedError("Unsupported interface type: {}".format(repr(self.intf)))
        elif type_ not in valid_types:
            raise PRGAAPIError("softreg interface ({}) does not support register type: {}"
                    .format(repr(self.intf), repr(type_)))

        # address space usage
        space = bytewidth
        if self.intf.is_softreg:
            pass
        elif self.intf.is_rxi:
            space = 1
        else:
            raise NotImplementedError("Unsupported interface type: {}".format(repr(self.intf)))

        # get soft register address (allocate)
        if addr is None:
            if self.intf.is_softreg:
                addr = ((len(self.addrspace) // bytewidth) + (1 if len(self.addrspace) % bytewidth > 0 else 0)) * bytewidth

            elif self.intf.is_rxi:

                for _ in range(1):
                    # try promoting the register type
                    if not dont_promote:
                        promoted_type = type_.case(
                                kernel = SoftRegType.hsr_kernel,
                                basic = SoftRegType.hsr_basic,
                                wrfull = SoftRegType.hsr_ififo,
                                default = None)

                        if promoted_type is not None:
                            addr = self._allocate_rxi(promoted_type)

                            if addr is not None:
                                _logger.info("Soft register '{}' promoted from type '{}' to '{}'"
                                        .format(name, type_.name, promoted_type.name))
                                type_ = promoted_type
                                break

                    # use user-specified type
                    if (addr := self._allocate_rxi(type_)) is None:
                        raise PRGAAPIError("Ran out of soft register space of type: {}"
                                .format(repr(type_)))

            else:
                raise NotImplementedError("Unsupported interface type: {}".format(repr(self.intf)))

        # validate user-specified address
        elif addr < 0:
            raise PRGATypeError('addr', 'non-negative integer')

        else:
            if self.intf.is_softreg:
                if addr % bytewidth != 0:
                    raise PRGATypeError('addr', 'non-negative integer and multiple of {} (due to alignment)'
                            .format(bytewidth))

            elif self.intf.is_rxi:
                valid_range = type_.case(
                        hsr_ififo   = (32, 36),
                        hsr_ofifo   = (36, 40),
                        hsr_tfifo   = (40, 44),
                        # hsr_plain   = (48, 64),
                        hsr_kernel  = (48, 64),
                        hsr_basic   = (48, 64),
                        default     = None,
                        )

                if valid_range is not None and not valid_range[0] <= addr < valid_range[1]:
                    raise PRGAAPIError("HSR: {} must be allocated at address [{}, {})"
                            .format(repr(type_), hsr_range[0], hsr_range[1]))

            # check conflict
            for i in range(space):
                if (addr + i) < len(self.addrspace) and (conflict := self.addrspace[addr + i]) is not None:
                    raise PRGAAPIError("Address space conflict. Soft register '{}' already using address 0x{:x}"
                            .format(conflict.name, addr + i))

        # increase address space if necessary
        if addr + space >= len(self.addrspace):
            if self.intf.is_softreg:
                if addr + bytewidth > 2 ** self.intf.addr_width:
                    raise PRGAAPIError("{}B at address 0x{:x} exceeds register address space"
                            .format(bytewidth, addr))
            elif self.intf.is_rxi:
                if addr >= 2 ** (self.intf.addr_width - self.intf.data_bytes_log2):
                    raise PRGAAPIError("Address 0x{:x} exceeds register address space"
                            .format(addr))
            else:
                raise NotImplementedError("Unsupported interface type: {}".format(repr(self.intf)))

            self.addrspace.extend( [None] * (addr + space - len(self.addrspace)) )

        # create register and add to address space
        reg = self.regs[name] = SoftReg(name, type_, addr, width, bytewidth, rstval)
        for i in range(space):
            self.addrspace[addr + i] = reg

        return reg

    def create_module(self, context):
        """Create a `Module` object implementing this soft register interface.

        Args:
            context (`AppContext`):

        Returns:
            `Module`:
        """

        # add header
        context.add_verilog_header("prga_app_softregs.vh",
                "softregs/include/prga_app_softregs.tmpl.vh",
                softregs = self)

        # choose verilog template
        verilog_template = None
        if self.intf.is_softreg:
            verilog_template = "softregs/prga_app_softregs." + ("strb." if self.intf.strb else "") + "tmpl.v"
        elif self.intf.is_rxi:
            verilog_template = "rxi/prga_app_softregs.tmpl.v"
        else:
            raise NotImplementedError("Unsupported interface type: {}".format(repr(self.intf)))

        # create module
        m = context.add_module(Module("prga_app_softregs",
                softregs = self,
                portgroups = {},
                verilog_template = verilog_template,
                verilog_dep_headers = ("prga_app_softregs.vh", )))

        # create ports
        if self.intf.is_softreg:
            raise NotImplementedError("(Temporarily) Unsupported interface type: {}".format(repr(self.intf)))

            ModuleUtils.create_port(m, "clk",               1,                    "input" , is_clock = True)
            ModuleUtils.create_port(m, "rst_n",             1,                    "input")
            ModuleUtils.create_port(m, "softreg_req_rdy",   1,                    "output")
            ModuleUtils.create_port(m, "softreg_req_val",   1,                    "input")
            ModuleUtils.create_port(m, "softreg_req_addr",  self.intf.addr_width, "input")
            if self.intf.strb:
                ModuleUtils.create_port(m, "softreg_req_strb",  1 << self.intf.data_bytes_log2, "input")
            else:
                ModuleUtils.create_port(m, "softreg_req_wr",    1,                          "input")
            ModuleUtils.create_port(m, "softreg_req_data",  8 << self.intf.data_bytes_log2, "input")
            ModuleUtils.create_port(m, "softreg_resp_rdy",  1,                              "input")
            ModuleUtils.create_port(m, "softreg_resp_val",  1,                              "output")
            ModuleUtils.create_port(m, "softreg_resp_data", 8 << self.intf.data_bytes_log2, "output")

        elif self.intf.is_rxi:

            m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)
            m.portgroups.setdefault("rxi", {})[None] = AppUtils.create_rxi_ports(m, self.intf,
                    slave = True, prefix = "rxi_", omit_ports = ("resp_parity", ))

        else:
            raise NotImplementedError("Unsupported interface type: {}".format(repr(self.intf)))

        # create register variable ports
        for name, r in self.regs.items():

            if r.type_.is_const:
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")

            elif r.type_.is_kernel:
                ModuleUtils.create_port(m, "var_{}_i".format(name),     r.width, "input")

            elif r.type_.is_rdempty:
                ModuleUtils.create_port(m, "var_{}_empty".format(name), 1,       "input")
                ModuleUtils.create_port(m, "var_{}_i".format(name),     r.width, "input")
                ModuleUtils.create_port(m, "var_{}_rd".format(name),    1,       "output")

            elif r.type_.is_rdempty_la:
                ModuleUtils.create_port(m, "var_{}_empty".format(name), 1,       "input")
                ModuleUtils.create_port(m, "var_{}_i".format(name),     r.width, "input")
                ModuleUtils.create_port(m, "var_{}_rd".format(name),    1,       "output")

            elif r.type_.is_cbl_2stage:
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")
                ModuleUtils.create_port(m, "var_{}_ack".format(name),   1,       "input")
                ModuleUtils.create_port(m, "var_{}_done".format(name),  1,       "input")

            elif r.type_.is_basic:
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")

            elif r.type_.is_pulse:
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")

            elif r.type_.is_pulse_ack:
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")
                ModuleUtils.create_port(m, "var_{}_ack".format(name),   1,       "input")

            elif r.type_.is_decoupled:
                ModuleUtils.create_port(m, "var_{}_i".format(name),     r.width, "input")
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")

            elif r.type_.is_wrfull:
                ModuleUtils.create_port(m, "var_{}_full".format(name),  1,       "input")
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")
                ModuleUtils.create_port(m, "var_{}_wr".format(name),    1,       "output")

            elif r.type_.is_hsr_ififo:
                ModuleUtils.create_port(m, "var_{}_full".format(name),  1,       "input")
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")
                ModuleUtils.create_port(m, "var_{}_wr".format(name),    1,       "output")

            elif r.type_.is_hsr_ofifo:
                ModuleUtils.create_port(m, "var_{}_full".format(name),  1,       "output")
                ModuleUtils.create_port(m, "var_{}_i".format(name),     r.width, "input")
                ModuleUtils.create_port(m, "var_{}_wr".format(name),    1,       "input")

            elif r.type_.is_hsr_tfifo:
                ModuleUtils.create_port(m, "var_{}_full".format(name),  1,       "output")
                ModuleUtils.create_port(m, "var_{}_wr".format(name),    1,       "input")

            elif r.type_.is_hsr_kernel:
                ModuleUtils.create_port(m, "var_{}_i".format(name),     r.width, "input")

            elif r.type_.is_hsr_basic:
                ModuleUtils.create_port(m, "var_{}_o".format(name),     r.width, "output")

            else:
                raise PRGAAPIError("Unsupported soft register type: {}".format(repr(r.type_)))

            if (sub := "prga_app_softreg_" + r.type_.name) not in m.instances:
                ModuleUtils.instantiate(m, context.modules[sub], sub)

        # return the module
        return m

    def log_summary(self, lvl = logging.INFO):
        """Print a summary to log."""

        _logger.log(lvl, "*****************************")
        _logger.log(lvl, "** Summary: Soft Registers **")
        _logger.log(lvl, "*****************************")
        for r in sorted(self.regs.values(), key = lambda r: r.addr):
            _logger.log(lvl, " - name: {}".format(r.name))
            _logger.log(lvl, "   type: {}".format(r.type_.name))
            _logger.log(lvl, "   addr: 0x{:04x}".format(r.addr))
            _logger.log(lvl, "   width: {}".format(r.width))
            _logger.log(lvl, "   bytewidth: {}".format(r.bytewidth))
