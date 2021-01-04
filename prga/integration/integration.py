# -*- encoding: ascii -*-

from .common import InterfaceClass
from ..core.common import ModuleView, ModuleClass, IOType
from ..netlist import Module, PortDirection, ModuleUtils, NetUtils
from ..tools.util import DesignIntf
from ..tools.ioplan import IOPlanner
from ..exception import PRGAAPIError, PRGAInternalError

__all__ = ["Integration"]

# ----------------------------------------------------------------------------
# -- Wrapping the FPGA fabric for Hybrid Integration -------------------------
# ----------------------------------------------------------------------------
class Integration(object):
    """Wrapper class for utility functions that helps integrating the fabric into a hybrid system."""

    @classmethod
    def _create_intf_syscon(cls, module, slave = False, prefix = ""):
        """Create system control signals (``clk`` and ``rst_n``).

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, create slave interface \(``clk`` and ``rst_n`` as input\) instead of master
                interface 
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "clk": ModuleUtils.create_port(module, prefix + "clk", 1, o, is_clock = True),
                prefix + "rst_n": ModuleUtils.create_port(module, prefix + "rst_n", 1, o)}

    @classmethod
    def _create_intf_simpleprog(cls, module, slave = False, prefix = ""):
        """Create generic programming interface. By default this creates the master interface that outputs
        programming data.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, create slave interface \(accepts programming data\) instead of master
                interface
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "rst_n":       ModuleUtils.create_port(module, prefix + "rst_n",       1,  o),
                prefix + "status":      ModuleUtils.create_port(module, prefix + "status",      2,  i),
                prefix + "req_rdy":     ModuleUtils.create_port(module, prefix + "req_rdy",     1,  i),
                prefix + "req_val":     ModuleUtils.create_port(module, prefix + "req_val",     1,  o),
                prefix + "req_addr":    ModuleUtils.create_port(module, prefix + "req_addr",    12, o),
                prefix + "req_strb":    ModuleUtils.create_port(module, prefix + "req_strb",    8,  o),
                prefix + "req_data":    ModuleUtils.create_port(module, prefix + "req_data",    64, o),
                prefix + "resp_rdy":    ModuleUtils.create_port(module, prefix + "resp_rdy",    1,  o),
                prefix + "resp_val":    ModuleUtils.create_port(module, prefix + "resp_val",    1,  i),
                prefix + "resp_err":    ModuleUtils.create_port(module, prefix + "resp_err",    1,  i),
                prefix + "resp_data":   ModuleUtils.create_port(module, prefix + "resp_data",   64, i),
                }

    @classmethod
    def _create_intf_reg(cls, module, slave = False, prefix = "", ecc = False):
        """Create register-based interface. By default this creates the master interface that sends register access
        requests and receives responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
            ecc (:obj:`bool`): If set, ecc port is added at the response side
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        d = {}
        d[prefix + "req_rdy"]       = ModuleUtils.create_port(module, prefix + "req_rdy", 1, i)
        d[prefix + "req_val"]       = ModuleUtils.create_port(module, prefix + "req_val", 1, o)
        d[prefix + "req_addr"]      = ModuleUtils.create_port(module, prefix + "req_addr", 12, o)
        d[prefix + "req_strb"]      = ModuleUtils.create_port(module, prefix + "req_strb", 8, o)
        d[prefix + "req_data"]      = ModuleUtils.create_port(module, prefix + "req_data", 64, o)
        d[prefix + "resp_rdy"]      = ModuleUtils.create_port(module, prefix + "resp_rdy", 1, o)
        d[prefix + "resp_val"]      = ModuleUtils.create_port(module, prefix + "resp_val", 1, i)
        d[prefix + "resp_data"]     = ModuleUtils.create_port(module, prefix + "resp_data", 64, i)
        if ecc:
            d[prefix + "resp_ecc"]  = ModuleUtils.create_port(module, prefix + "resp_ecc", 1, i)
        return d

    @classmethod
    def _create_intf_ccm(cls, module, slave = False, prefix = "", ecc = False):
        """Create generic cache-coherent memory interface. By default this creates the master interface that sends
        requests and recieve responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
            ecc (:obj:`bool`): If set, ecc port is added at the request side
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        d = {}
        d[prefix + "req_rdy"]	        = ModuleUtils.create_port(module, prefix + "req_rdy", 1, i)
        d[prefix + "req_val"]	        = ModuleUtils.create_port(module, prefix + "req_val", 1, o)
        d[prefix + "req_type"]	        = ModuleUtils.create_port(module, prefix + "req_type", 3, o)
        d[prefix + "req_addr"]	        = ModuleUtils.create_port(module, prefix + "req_addr", 40, o)
        d[prefix + "req_data"]	        = ModuleUtils.create_port(module, prefix + "req_data", 64, o)
        d[prefix + "req_size"]	        = ModuleUtils.create_port(module, prefix + "req_size", 3, o)
        d[prefix + "req_threadid"]      = ModuleUtils.create_port(module, prefix + "req_threadid", 1, o)
        d[prefix + "req_amo_opcode"]    = ModuleUtils.create_port(module, prefix + "req_amo_opcode", 4, o)
        d[prefix + "resp_rdy"]	        = ModuleUtils.create_port(module, prefix + "resp_rdy", 1, o)
        d[prefix + "resp_val"]	        = ModuleUtils.create_port(module, prefix + "resp_val", 1, i)
        d[prefix + "resp_type"]	        = ModuleUtils.create_port(module, prefix + "resp_type", 3, i)
        d[prefix + "resp_addr"]	        = ModuleUtils.create_port(module, prefix + "resp_addr", 7, i)
        d[prefix + "resp_data"]	        = ModuleUtils.create_port(module, prefix + "resp_data", 128, i)
        d[prefix + "resp_threadid"]     = ModuleUtils.create_port(module, prefix + "resp_threadid", 1, i)
        if ecc:
            d[prefix + "req_ecc"]	    = ModuleUtils.create_port(module, prefix + "req_ecc", 1, o)
        return d

    @classmethod
    def _register_cells(cls, context):
        """Register integration-related modules in to the module database.

        Args:
            context (`Context`):
        """
        # 1. add prga_system header
        context._add_verilog_header("prga_system.vh", "include/prga_system.tmpl.vh")

        # 2. register modules
        # 2.1 modules that we don't need to know about their ports
        for d in ("prga_ctrl", "prga_ecc_parity", "prga_mprot", "prga_sax", "prga_uprot", "prga_ccm_transducer"):
            context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "{}.tmpl.v".format(d))
        for d in ("prga_l15_transducer", ):
            context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "piton/{}.v".format(d))
        for d in ("prga_fe_axi4lite", ):
            context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "axi4lite/{}.tmpl.v".format(d))
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_ctrl"],
                context.database[ModuleView.logical, "prga_clkdiv"], "i_clkdiv")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_ctrl"],
                context.database[ModuleView.logical, "prga_byteaddressable_reg"], "i_bitstream_id")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_ctrl"],
                context.database[ModuleView.logical, "prga_byteaddressable_reg"], "i_eflags")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_ctrl"],
                context.database[ModuleView.logical, "prga_byteaddressable_reg"], "i_app_features")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_ctrl"],
                context.database[ModuleView.logical, "prga_fifo"], "i_tokenq")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_ctrl"],
                context.database[ModuleView.logical, "prga_fifo"], "i_ctrldataq")

        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_mprot"],
                context.database[ModuleView.logical, "prga_ecc_parity"], "i_ecc_checker")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_mprot"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_buf")

        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_sax"],
                context.database[ModuleView.logical, "prga_async_fifo"], "i_sax_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_sax"],
                context.database[ModuleView.logical, "prga_async_fifo"], "i_asx_fifo")

        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_uprot"],
                context.database[ModuleView.logical, "prga_ecc_parity"], "i_ecc_checker")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_uprot"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_buf")

        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_awaddr")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_wdata")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_araddr")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_bresp")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_rresp")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_creq")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_valrdy_buf"], "i_cresp")

        # 2.2 modules that we do need to know about their ports
        sysintf = context._database[ModuleView.logical, "prga_sysintf"] = Module("prga_sysintf",
                view = ModuleView.logical,
                module_class = ModuleClass.aux,
                verilog_template = "prga_sysintf.tmpl.v")
        cls._create_intf_syscon     (sysintf, True)          # programming clock and reset
        cls._create_intf_syscon     (sysintf, False, "a")    # application clock and reset
        cls._create_intf_reg        (sysintf, True, "reg_")
        cls._create_intf_ccm        (sysintf, False, "ccm_")
        cls._create_intf_simpleprog (sysintf, False, "prog_")
        cls._create_intf_reg        (sysintf, False, "ureg_", True)
        cls._create_intf_ccm        (sysintf, True, "uccm_", True)
        ModuleUtils.create_port(sysintf, "urst_n", 1, PortDirection.output)
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_ctrl"], "i_ctrl")
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_ccm_transducer"], "i_transducer")
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_sax"], "i_sax")
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_uprot"], "i_uprot")
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_mprot"], "i_mprot")


    @classmethod
    def _create_design_intf(cls, context, interfaces):
        """Create a `DesignIntf` object with the specified ``interfaces``.

        Args:
            context (`Context`):
            interfaces (:obj:`Container` [`InterfaceClass` ]): `InterfaceClass.syscon` is always added

        Returns:
            `DesignIntf`:
        """
        d = DesignIntf("design")

        # 1. add InterfaceClass.syscon first
        if True:
            # create the ports
            clk = d.add_port("clk", PortDirection.input_)
            rst_n = d.add_port("rst_n", PortDirection.input_)

            # needs special handling of clock
            for g in context.globals_.values():
                if g.is_clock:
                    clk.set_io_constraint(g.bound_to_position, g.bound_to_subtile)
                    break
            if clk.get_io_constraint() is None:
                raise PRGAAPIError("No clock found in the fabric")

        # 2. process other interfaces
        for interface in (set(iter(interfaces)) - {InterfaceClass.syscon}):
            if interface.is_reg_simple:
                d.add_port("ureg_req_rdy",          PortDirection.output)
                d.add_port("ureg_req_val",          PortDirection.input_)
                d.add_port("ureg_req_addr",         PortDirection.input_,   12)
                d.add_port("ureg_req_strb",         PortDirection.input_,   8)
                d.add_port("ureg_req_data",         PortDirection.input_,   64)
                d.add_port("ureg_resp_val",         PortDirection.output)
                d.add_port("ureg_resp_rdy",         PortDirection.input_)
                d.add_port("ureg_resp_data",        PortDirection.output,   64)
                d.add_port("ureg_resp_ecc",         PortDirection.output,   1)
            elif interface.is_ccm_simple:
                d.add_port("uccm_req_rdy",          PortDirection.input_)
                d.add_port("uccm_req_val",          PortDirection.output)
                d.add_port("uccm_req_type",         PortDirection.output,   3)
                d.add_port("uccm_req_addr",         PortDirection.output,   40)
                d.add_port("uccm_req_data",         PortDirection.output,   64)
                d.add_port("uccm_req_size",         PortDirection.output,   3)
                d.add_port("uccm_req_threadid",     PortDirection.output,   1)
                d.add_port("uccm_req_amo_opcode",   PortDirection.output,   4)
                d.add_port("uccm_req_ecc",          PortDirection.output,   1)
                d.add_port("uccm_resp_rdy",         PortDirection.output)
                d.add_port("uccm_resp_val",         PortDirection.input_)
                d.add_port("uccm_resp_type",        PortDirection.input_,   3)
                d.add_port("uccm_resp_threadid",    PortDirection.input_,   1)
                d.add_port("uccm_resp_addr",        PortDirection.input_,   slice(10, 3, -1))
                d.add_port("uccm_resp_data",        PortDirection.input_,   128)
            else:
                raise PRGAAPIError("Unsupported interface class: {:r}".format(interface))

        # 3. return design interface object
        return d

    @classmethod
    def build_system(cls, context, interfaces = (InterfaceClass.ccm_simple, InterfaceClass.reg_simple), *,
            name = "prga_system", core = None):
        """Create the system top wrapping the reconfigurable fabric.

        Args:
            context (`Context`):
            interfaces (:obj:`Container` [`InterfaceClass` ]): Interfaces added

        Keyword Args:
            name (:obj:`str`): Name of the system top module
            core (:obj:`str` or :obj:`bool`): If set to a :obj:`str`, or set to ``True`` \(in which case it is
                converted to ``{name}_core``\), an extra layer of wrapper is created around the fabric and
                instantiated in the top-level module
        """
        if set(iter(interfaces)) != {InterfaceClass.ccm_simple, InterfaceClass.reg_simple}:
            raise NotImplementedError("The only implemented interface is (ccm_simple, reg_simple) at the moment")

        if core is True:
            core = name + "_core"

        # get or create design interface
        if (intf := getattr(context.summary, "intf", None)) is None:
            intf = context.summary.intf = cls._create_design_intf(context, interfaces)
        IOPlanner.autoplan(context, intf)

        # create system
        system = context.system_top = Module(name, view = ModuleView.logical, module_class = ModuleClass.aux)

        # create ports
        cls._create_intf_syscon(system, True)
        cls._create_intf_reg(system, True, "reg_")
        cls._create_intf_ccm(system, False, "ccm_")

        # instantiate sysintf in system
        sysintf = ModuleUtils.instantiate(system, context.database[ModuleView.logical, "prga_sysintf"], "i_sysintf")

        # connect system ports to sysintf
        for port_name, port in system.ports.items():
            if port.direction.is_input:
                NetUtils.connect(port, sysintf.pins[port_name])
            else:
                NetUtils.connect(sysintf.pins[port_name], port)

        # instantiate fabric
        nets = None
        if core:
            # build system core (fabric wrapper)
            core = context._database[ModuleView.logical, core] = Module(core,
                    view = ModuleView.logical, module_class = ModuleClass.aux)

            # create ports in core
            cls._create_intf_syscon(core, True, "u")
            cls._create_intf_reg(core, True, "ureg_", ecc = True)
            cls._create_intf_ccm(core, False, "uccm_", ecc = True)

            # instantiate fabric within core
            fabric = ModuleUtils.instantiate(core,
                    context.database[ModuleView.logical, context.top.key], "i_fabric")
            nets = core.ports

            # instantiate core in system
            core = ModuleUtils.instantiate(system, core, "i_core")

            # connect sysintf with core
            for pin_name, pin in core.pins.items():
                if pin_name == "uclk":
                    NetUtils.connect(sysintf.pins["aclk"], pin)
                elif pin_name == "urst_n":
                    NetUtils.connect(sysintf.pins["urst_n"], pin)
                elif pin.model.direction.is_input:
                    NetUtils.connect(sysintf.pins[pin_name], pin)
                else:
                    NetUtils.connect(pin, sysintf.pins[pin_name])

        else:
            # instantiate fabric within system
            fabric = ModuleUtils.instantiate(system,
                    context.database[ModuleView.logical, context.top.key], "i_fabric")
            nets = sysintf.pins

        # connect fabric
        for name, port in intf.ports.items():
            if name == "clk":
                NetUtils.connect(nets["uclk"],      fabric.pins[(IOType.ipin, ) + port.get_io_constraint()])
            elif name == "rst_n":
                NetUtils.connect(nets["urst_n"],    fabric.pins[(IOType.ipin, ) + port.get_io_constraint()])
            elif port.direction.is_input:
                for i, (idx, io) in enumerate(port.iter_io_constraints()):
                    if idx is None:
                        NetUtils.connect(nets[name],    fabric.pins[(IOType.ipin, ) + io])
                    else:
                        NetUtils.connect(nets[name][i], fabric.pins[(IOType.ipin, ) + io])
            else:
                for i, (idx, io) in enumerate(port.iter_io_constraints()):
                    if idx is None:
                        NetUtils.connect(fabric.pins[(IOType.opin, ) + io], nets[name])
                    else:
                        NetUtils.connect(fabric.pins[(IOType.opin, ) + io], nets[name][i])
