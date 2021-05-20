# -*- encoding: ascii -*-

from .common import SystemIntf, FabricIntf, FabricIntfECCType
from ..core.common import ModuleView, ModuleClass, IOType
from ..netlist import Module, PortDirection, ModuleUtils, NetUtils
from ..tools.util import AppIntf
from ..tools.ioplan import IOPlanner
from ..exception import PRGAAPIError, PRGAInternalError

import logging
_logger = logging.getLogger(__name__)

__all__ = ["Integration"]

# ----------------------------------------------------------------------------
# -- Wrapping the FPGA fabric for Hybrid Integration -------------------------
# ----------------------------------------------------------------------------
class Integration(object):
    """Wrapper class for utility functions that helps integrating the fabric into a hybrid system."""

    @classmethod
    def _create_intf_ports_syscon(cls, module, slave = False, prefix = ""):
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
    def _create_intf_ports_prog_piton(cls, module, slave = False, prefix = ""):
        """Create register-based programming interface compatible with OpenPiton. By default this creates the master
        interface that outputs programming data.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, create slave interface \(accepts programming data\) instead of master
                interface
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "status":      ModuleUtils.create_port(module, prefix + "status",      2,  i),
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
    def _create_intf_ports_reg(cls, module, slave = False, prefix = "", *,
            ecc = FabricIntfECCType.none, addr_width = 12, data_bytes = 8, strb = False):
        """Create register-based interface. By default this creates the master interface that sends register access
        requests and receives responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names

        Keyword Args:
            ecc (`FabricIntfECCType` or :obj:`str`): ECC algorithm. If set to any value other than
                `FabricIntfECCType.none`, an ECC port is added on the response channel
            addr_width (:obj:`int`): Number of bits in the address bus
            data_bytes (:obj:`int`): Number of bytes in the data bus
            strb (:obj:`bool`): If set, byte write strobes are used instead of a full-word write-enable signal
        """
        ecc = FabricIntfECCType.construct(ecc)
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        d = {}

        d[prefix + "req_rdy"]       = ModuleUtils.create_port(module, prefix + "req_rdy", 1, i)
        d[prefix + "req_val"]       = ModuleUtils.create_port(module, prefix + "req_val", 1, o)
        d[prefix + "req_addr"]      = ModuleUtils.create_port(module, prefix + "req_addr", addr_width, o)
        if strb:
            d[prefix + "req_strb"]  = ModuleUtils.create_port(module, prefix + "req_strb", data_bytes, o)
        else:
            d[prefix + "req_wr"]    = ModuleUtils.create_port(module, prefix + "req_wr", 1, o)
        d[prefix + "req_data"]      = ModuleUtils.create_port(module, prefix + "req_data", data_bytes * 8, o)

        d[prefix + "resp_rdy"]      = ModuleUtils.create_port(module, prefix + "resp_rdy", 1, o)
        d[prefix + "resp_val"]      = ModuleUtils.create_port(module, prefix + "resp_val", 1, i)
        d[prefix + "resp_data"]     = ModuleUtils.create_port(module, prefix + "resp_data", data_bytes * 8, i)

        if ecc.ecc_bits > 0:
            d[prefix + "resp_ecc"]  = ModuleUtils.create_port(module, prefix + "resp_ecc", ecc.ecc_bits, i)

        return d

    @classmethod
    def _create_intf_ports_memory_piton(cls, module, slave = False, prefix = "", *,
            ecc = FabricIntfECCType.none):
        """Create cache-coherent memory interface compatible with OpenPiton. By default this creates the master
        interface that sends requests and recieve responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names

        Keyword Args:
            ecc (`FabricIntfECCType` or :obj:`str`): ECC algorithm. If set to any value other than
                `FabricIntfECCType.none`, an ECC port is added on the response channel
        """
        ecc = FabricIntfECCType.construct(ecc)
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

        if ecc.ecc_bits > 0:
            d[prefix + "req_ecc"]	    = ModuleUtils.create_port(module, prefix + "req_ecc", ecc.ecc_bits, o)

        return d

    @classmethod
    def _create_intf_ports_memory_piton_axi4r(cls, module, slave = False, prefix = "", *,
            ecc = FabricIntfECCType.parity_even, unused = False, upper = False):
        """Create cache-coherent memory load interface in AXI4 protocol. By default this creates the master interface
        that sends AR channel requests and receive R channel responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names

        Keyword Args:
            ecc (`FabricIntfECCType`): ECC check type
            unused (:obj:`bool`): If set, unused but required AXI4 ports are also added, including ``arprot``,
                ``arqos``, and ``arregion``.
            upper (:obj:`bool`): If set, AXI4 port names are upper case
        """
        ecc = FabricIntfECCType.construct(ecc)
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        d = {}
        def u(x):
            return x.upper() if upper else x

        # AR channel
        d[prefix + u("arready")]        = ModuleUtils.create_port(module, prefix + u("arready"), 1, i)
        d[prefix + u("arvalid")]        = ModuleUtils.create_port(module, prefix + u("arvalid"), 1, o)
        d[prefix + u("arid")]           = ModuleUtils.create_port(module, prefix + u("arid"), 1, o)
        d[prefix + u("araddr")]         = ModuleUtils.create_port(module, prefix + u("araddr"), 40, o)
        d[prefix + u("arlen")]          = ModuleUtils.create_port(module, prefix + u("arlen"), 8, o)
        d[prefix + u("arsize")]         = ModuleUtils.create_port(module, prefix + u("arsize"), 3, o)
        d[prefix + u("arburst")]        = ModuleUtils.create_port(module, prefix + u("arburst"), 2, o)
        d[prefix + u("arlock")]         = ModuleUtils.create_port(module, prefix + u("arlock"), 1, o)
        d[prefix + u("arcache")]        = ModuleUtils.create_port(module, prefix + u("arcache"), 4, o)
        d[prefix + u("aruser")]     = ModuleUtils.create_port(module, prefix + u("aruser"), 64 + 4 + ecc.ecc_bits, o)

        if unused:
            d[prefix + u("arprot")]     = ModuleUtils.create_port(module, prefix + u("arprot"), 3, o)
            d[prefix + u("arqos")]      = ModuleUtils.create_port(module, prefix + u("arqos"), 4, o)
            d[prefix + u("arregion")]   = ModuleUtils.create_port(module, prefix + u("arregion"), 4, o)

        # R channel
        d[prefix + u("rready")]         = ModuleUtils.create_port(module, prefix + u("rready"), 1, o)
        d[prefix + u("rvalid")]         = ModuleUtils.create_port(module, prefix + u("rvalid"), 1, i)
        d[prefix + u("rresp")]          = ModuleUtils.create_port(module, prefix + u("rresp"), 2, i)
        d[prefix + u("rid")]            = ModuleUtils.create_port(module, prefix + u("rid"), 1, i)
        d[prefix + u("rdata")]          = ModuleUtils.create_port(module, prefix + u("rdata"), 64, i)
        d[prefix + u("rlast")]          = ModuleUtils.create_port(module, prefix + u("rlast"), 1, i)

        return d

    @classmethod
    def _create_intf_ports_memory_piton_axi4w(cls, module, slave = False, prefix = "", *,
            ecc = FabricIntfECCType.parity_even, unused = False, upper = False):
        """Create cache-coherent memory store interface in AXI4 protocol. By default this creates the master interface
        that sends AW/W channel requests and receive B channel responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names

        Keyword Args:
            ecc (`FabricIntfECCType`): ECC check type
            unused (:obj:`bool`): if set, unused but required AXI4 ports are also added, including ``awprot``,
                ``awqos``, ``awlock``, and ``awregion``.
            upper (:obj:`bool`): If set, AXI4 port names are upper case
        """
        ecc = FabricIntfECCType.construct(ecc)
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        d = {}
        def u(x):
            return x.upper() if upper else x

        # AW channel
        d[prefix + u("awready")]        = ModuleUtils.create_port(module, prefix + u("awready"), 1, i)
        d[prefix + u("awvalid")]        = ModuleUtils.create_port(module, prefix + u("awvalid"), 1, o)
        d[prefix + u("awid")]           = ModuleUtils.create_port(module, prefix + u("awid"), 1, o)
        d[prefix + u("awaddr")]         = ModuleUtils.create_port(module, prefix + u("awaddr"), 40, o)
        d[prefix + u("awlen")]          = ModuleUtils.create_port(module, prefix + u("awlen"), 8, o)
        d[prefix + u("awsize")]         = ModuleUtils.create_port(module, prefix + u("awsize"), 3, o)
        d[prefix + u("awburst")]        = ModuleUtils.create_port(module, prefix + u("awburst"), 2, o)
        d[prefix + u("awcache")]        = ModuleUtils.create_port(module, prefix + u("awcache"), 4, o)

        if ecc.ecc_bits > 0:
            d[prefix + u("awuser")]     = ModuleUtils.create_port(module, prefix + u("awuser"), ecc.ecc_bits, o)

        if unused:
            d[prefix + u("awlock")]     = ModuleUtils.create_port(module, prefix + u("awlock"), 1, o)
            d[prefix + u("awprot")]     = ModuleUtils.create_port(module, prefix + u("awprot"), 3, o)
            d[prefix + u("awqos")]      = ModuleUtils.create_port(module, prefix + u("awqos"), 4, o)
            d[prefix + u("awregion")]   = ModuleUtils.create_port(module, prefix + u("awregion"), 4, o)

        # W channel
        d[prefix + u("wready")]         = ModuleUtils.create_port(module, prefix + u("wready"), 1, i)
        d[prefix + u("wvalid")]         = ModuleUtils.create_port(module, prefix + u("wvalid"), 1, o)
        d[prefix + u("wdata")]          = ModuleUtils.create_port(module, prefix + u("wdata"), 64, o)
        d[prefix + u("wstrb")]          = ModuleUtils.create_port(module, prefix + u("wstrb"), 8, o)
        d[prefix + u("wlast")]          = ModuleUtils.create_port(module, prefix + u("wlast"), 1, o)

        if ecc.ecc_bits > 0:
            d[prefix + u("wuser")]      = ModuleUtils.create_port(module, prefix + u("wuser"), ecc.ecc_bits, o)

        # B channel
        d[prefix + u("bready")]         = ModuleUtils.create_port(module, prefix + u("bready"), 1, o)
        d[prefix + u("bvalid")]         = ModuleUtils.create_port(module, prefix + u("bvalid"), 1, i)
        d[prefix + u("bresp")]          = ModuleUtils.create_port(module, prefix + u("bresp"), 2, i)
        d[prefix + u("bid")]            = ModuleUtils.create_port(module, prefix + u("bid"), 1, i)

        return d

    @classmethod
    def _register_cells(cls, context):
        """Register integration-related modules in to the module database.

        Args:
            context (`Context`):
        """
        # 1. add prga_system header
        context.add_verilog_header("prga_system.vh", "piton_v0/include/prga_system.tmpl.vh")
        context.add_verilog_header("prga_system_axi4.vh", "piton_v0/include/prga_system_axi4.tmpl.vh",
                "prga_system.vh", "prga_axi4.vh")

        # 2. register modules
        # 2.1 modules that we don't need to know about their ports
        for d in ("prga_ctrl", "prga_ecc_parity", "prga_mprot",
                "prga_sax", "prga_uprot", "prga_ccm_transducer"):
            context._database[ModuleView.design, d] = Module(d,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "piton_v0/{}.tmpl.v".format(d),
                    verilog_dep_headers = ("prga_system.vh", ))
        for d in ("prga_l15_transducer", ):
            context._database[ModuleView.design, d] = Module(d,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "piton_v0/{}.v".format(d),
                    verilog_dep_headers = ("prga_system.vh", ))
        for d in ("prga_fe_axi4lite", ):
            context._database[ModuleView.design, d] = Module(d,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "axi4lite/{}.tmpl.v".format(d),
                    verilog_dep_headers = ("prga_system.vh", ))
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_ctrl"],
                context.database[ModuleView.design, "prga_clkdiv"], "i_clkdiv")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_ctrl"],
                context.database[ModuleView.design, "prga_byteaddressable_reg"], "i_bitstream_id")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_ctrl"],
                context.database[ModuleView.design, "prga_byteaddressable_reg"], "i_eflags")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_ctrl"],
                context.database[ModuleView.design, "prga_byteaddressable_reg"], "i_app_features")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_ctrl"],
                context.database[ModuleView.design, "prga_fifo"], "i_tokenq")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_ctrl"],
                context.database[ModuleView.design, "prga_fifo"], "i_ctrldataq")

        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_mprot"],
                context.database[ModuleView.design, "prga_ecc_parity"], "i_ecc_checker")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_mprot"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_buf")

        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_sax"],
                context.database[ModuleView.design, "prga_async_fifo"], "i_sax_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_sax"],
                context.database[ModuleView.design, "prga_async_fifo"], "i_asx_fifo")

        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_uprot"],
                context.database[ModuleView.design, "prga_ecc_parity"], "i_ecc_checker")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_uprot"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_buf")

        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fe_axi4lite"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_awaddr")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fe_axi4lite"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_wdata")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fe_axi4lite"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_araddr")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fe_axi4lite"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_bresp")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fe_axi4lite"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_rresp")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fe_axi4lite"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_creq")
        ModuleUtils.instantiate(context.database[ModuleView.design, "prga_fe_axi4lite"],
                context.database[ModuleView.design, "prga_valrdy_buf"], "i_cresp")

        # 2.2 modules that we do need to know about their ports
        syscomplex = context._database[ModuleView.design, "prga_syscomplex"] = Module("prga_syscomplex",
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "piton_v0/prga_syscomplex.tmpl.v",
                verilog_dep_headers = ("prga_system.vh", ))
        cls._create_intf_ports_syscon           (syscomplex, True)          # programming clock and reset
        cls._create_intf_ports_syscon           (syscomplex, False, "a")    # application clock and reset
        cls._create_intf_ports_reg              (syscomplex, True, "reg_",
                addr_width = 12, data_bytes = 8, strb = True)
        cls._create_intf_ports_memory_piton     (syscomplex, False, "ccm_")
        cls._create_intf_ports_prog_piton       (syscomplex, False, "prog_")
        cls._create_intf_ports_reg              (syscomplex, False, "ureg_",
                ecc = "parity_even", addr_width = 12, data_bytes = 8, strb = True)
        cls._create_intf_ports_memory_piton     (syscomplex, True, "uccm_", ecc = "parity_even")
        ModuleUtils.create_port(syscomplex, "urst_n",     1, PortDirection.output)
        ModuleUtils.create_port(syscomplex, "prog_rst_n", 1, PortDirection.output)
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_ctrl"], "i_ctrl")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_ccm_transducer"], "i_transducer")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_sax"], "i_sax")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_uprot"], "i_uprot")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_mprot"], "i_mprot")

        # 3. AXI4 interface
        mprot = context._database[ModuleView.design, "prga_mprot.axi4"] = Module("prga_mprot",
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "piton_v0/axi4/prga_mprot.tmpl.v",
                key = "prga_mprot.axi4",
                verilog_dep_headers = ("prga_system_axi4.vh", ))
        ModuleUtils.instantiate(mprot, context.database[ModuleView.design, "prga_ecc_parity"], "i_ecc_checker")
        ModuleUtils.instantiate(mprot, context.database[ModuleView.design, "prga_valrdy_buf"], "i_buf")

        syscomplex = context._database[ModuleView.design, "prga_syscomplex.axi4"] = Module("prga_syscomplex",
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "piton_v0/axi4/prga_syscomplex.tmpl.v",
                key = "prga_syscomplex.axi4",
                verilog_dep_headers = ("prga_system_axi4.vh", ))
        cls._create_intf_ports_syscon               (syscomplex, True)          # programming clock and reset
        cls._create_intf_ports_syscon               (syscomplex, False, "a")    # application clock and reset
        cls._create_intf_ports_reg              (syscomplex, True, "reg_",
                addr_width = 12, data_bytes = 8, strb = True)
        cls._create_intf_ports_memory_piton         (syscomplex, False, "ccm_")
        cls._create_intf_ports_prog_piton           (syscomplex, False, "prog_")
        cls._create_intf_ports_reg              (syscomplex, False, "ureg_",
                ecc = "parity_even", addr_width = 12, data_bytes = 8, strb = True)
        cls._create_intf_ports_memory_piton_axi4r   (syscomplex, True)
        cls._create_intf_ports_memory_piton_axi4w   (syscomplex, True)
        ModuleUtils.create_port(syscomplex, "urst_n",     1, PortDirection.output)
        ModuleUtils.create_port(syscomplex, "prog_rst_n", 1, PortDirection.output)
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_ctrl"], "i_ctrl")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_ccm_transducer"], "i_transducer")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_sax"], "i_sax")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_uprot"], "i_uprot")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_mprot.axi4"], "i_mprot")

    @classmethod
    def _create_app_intf(cls, context, interfaces):
        """Create an `AppIntf` object with the specified fabric ``interfaces``.

        Args:
            context (`Context`):
            interfaces (:obj:`Container` [`FabricIntf` ]): `FabricIntf.syscon` is always added

        Returns:
            `AppIntf`:
        """
        d = AppIntf("design")

        # 0. separate syscon and other interfaces from ``interfaces``
        syscon, others = [], []
        for intf in interfaces:
            if intf.is_syscon:
                syscon.append(intf)
            else:
                others.append(intf)

        if len(syscon) > 1:
            raise PRGAInternalError("Currently only one clk/rst_n per fabric is supported")
        elif len(syscon) == 1:
            syscon = "" if syscon[0].id_ is None else (syscon[0].id_ + "_")
        else:
            syscon = ""

        # 1. add InterfaceClass.syscon first
        if True:
            # create the ports
            clk = d.add_port(syscon + "clk", PortDirection.input_)
            rst_n = d.add_port(syscon + "rst_n", PortDirection.input_)

            # needs special handling of clock
            for g in context.globals_.values():
                if g.is_clock:
                    clk.set_io_constraint(g.bound_to_position, g.bound_to_subtile)
                    break
            if clk.get_io_constraint() is None:
                raise PRGAInternalError("No clock found in the fabric")

        # 2. process other interfaces
        for interface in others:
            pf = "" if interface.id_ is None else (interface.id_ + "_")

            if interface.is_softreg:
                d.add_port(pf + "req_rdy",          PortDirection.output)
                d.add_port(pf + "req_val",          PortDirection.input_)
                d.add_port(pf + "req_addr",         PortDirection.input_,   interface.addr_width)
                d.add_port(pf + "req_data",         PortDirection.input_,   2 ** (interface.data_bytes_log2 + 3))
                d.add_port(pf + "resp_val",         PortDirection.output)
                d.add_port(pf + "resp_rdy",         PortDirection.input_)
                d.add_port(pf + "resp_data",        PortDirection.output,   2 ** (interface.data_bytes_log2 + 3))

                if interface.strb:
                    d.add_port(pf + "req_strb",     PortDirection.input_,   2 ** interface.data_bytes_log2)
                else:
                    d.add_port(pf + "req_wr",       PortDirection.input_,   1)

                if interface.ecc_type.ecc_bits > 0:
                    d.add_port(pf + "resp_ecc",     PortDirection.output,   interface.ecc_type.ecc_bits)

            elif interface.is_memory_piton:
                d.add_port(pf + "req_rdy",          PortDirection.input_)
                d.add_port(pf + "req_val",          PortDirection.output)
                d.add_port(pf + "req_type",         PortDirection.output,   3)
                d.add_port(pf + "req_addr",         PortDirection.output,   40)
                d.add_port(pf + "req_data",         PortDirection.output,   64)
                d.add_port(pf + "req_size",         PortDirection.output,   3)
                d.add_port(pf + "req_threadid",     PortDirection.output,   1)
                d.add_port(pf + "req_amo_opcode",   PortDirection.output,   4)

                if interface.ecc_type.ecc_bits > 0:
                    d.add_port(pf + "req_ecc",      PortDirection.output,   interface.ecc_type.ecc_bits)

                d.add_port(pf + "resp_rdy",         PortDirection.output)
                d.add_port(pf + "resp_val",         PortDirection.input_)
                d.add_port(pf + "resp_type",        PortDirection.input_,   3)
                d.add_port(pf + "resp_threadid",    PortDirection.input_,   1)
                d.add_port(pf + "resp_addr",        PortDirection.input_,   slice(10, 3, -1))
                d.add_port(pf + "resp_data",        PortDirection.input_,   128)

            elif interface.is_memory_piton_axi4w:
                # AW channel
                d.add_port(pf + "awready",	        PortDirection.input_,	1)
                d.add_port(pf + "awvalid",	        PortDirection.output,	1)
                d.add_port(pf + "awid",	            PortDirection.output,	1)
                d.add_port(pf + "awaddr",	        PortDirection.output,	40)
                d.add_port(pf + "awlen",	        PortDirection.output,	8)
                d.add_port(pf + "awsize",	        PortDirection.output,	3)
                d.add_port(pf + "awburst",	        PortDirection.output,	2)
                d.add_port(pf + "awcache",	        PortDirection.output,	4)
                d.add_port(pf + "awlock",	        PortDirection.output,	1)
                d.add_port(pf + "awprot",	        PortDirection.output,	3)
                d.add_port(pf + "awqos",	        PortDirection.output,	4)
                d.add_port(pf + "awregion",	        PortDirection.output,	4)

                if interface.ecc_type.ecc_bits > 0:
                    d.add_port(pf + "awuser",	    PortDirection.output,	interface.ecc_type.ecc_bits)

                # W channel 
                d.add_port(pf + "wready",	        PortDirection.input_,	1)
                d.add_port(pf + "wvalid",	        PortDirection.output,	1)
                d.add_port(pf + "wdata",	        PortDirection.output,	64)
                d.add_port(pf + "wstrb",	        PortDirection.output,	8)
                d.add_port(pf + "wlast",	        PortDirection.output,	1)

                if interface.ecc_type.ecc_bits > 0:
                    d.add_port(pf + "wuser",	    PortDirection.output,	interface.ecc_type.ecc_bits)

                # B channel 
                d.add_port(pf + "bready",	        PortDirection.output,	1)
                d.add_port(pf + "bvalid",	        PortDirection.input_,	1)
                d.add_port(pf + "bresp",	        PortDirection.input_,	2)
                d.add_port(pf + "bid",	            PortDirection.input_,	1)

            elif interface.is_memory_piton_axi4r:
                # AR channel
                d.add_port(pf + "arready",	        PortDirection.input_,	1)
                d.add_port(pf + "arvalid",	        PortDirection.output,	1)
                d.add_port(pf + "arid",	            PortDirection.output,	1)
                d.add_port(pf + "araddr",	        PortDirection.output,	40)
                d.add_port(pf + "arlen",	        PortDirection.output,	8)
                d.add_port(pf + "arsize",	        PortDirection.output,	3)
                d.add_port(pf + "arburst",	        PortDirection.output,	2)
                d.add_port(pf + "arlock",	        PortDirection.output,	1)
                d.add_port(pf + "arcache",	        PortDirection.output,	4)
                d.add_port(pf + "aruser",	        PortDirection.output,	64 + 4 + interface.ecc_type.ecc_bits)
                d.add_port(pf + "arprot",	        PortDirection.output,	3)
                d.add_port(pf + "arqos",	        PortDirection.output,	4)
                d.add_port(pf + "arregion",	        PortDirection.output,	4)

                # R channel
                d.add_port(pf + "rready",	        PortDirection.output,	1)
                d.add_port(pf + "rvalid",	        PortDirection.input_,	1)
                d.add_port(pf + "rresp",	        PortDirection.input_,	2)
                d.add_port(pf + "rid",	            PortDirection.input_,	1)
                d.add_port(pf + "rdata",	        PortDirection.input_,	64)
                d.add_port(pf + "rlast",	        PortDirection.input_,	1)

            else:
                raise PRGAInternalError("Unsupported interface class: {}".format(interface))

        # 3. return design interface object
        return d

    @classmethod
    def _validate_system_intfs(cls, intfs):
        """Validate system interface collection.

        Args:
            intfs (:obj:`Container` [`SystemIntf` ]):
        """

        known_intfs = set( ("syscon", "reg_piton", "memory_piton") )

        # categorization
        classes = {}
        for intf in intfs:
            classes.setdefault(intf.name, set()).add(intf)

        # validate
        if (len(classes["syscon"]) == 1
                and len(classes["reg_piton"]) == 1
                and len(classes["memory_piton"]) == 1
                and sum(len(x) for k, x in classes.items()
                    if k not in known_intfs) == 0):
            return

        raise NotImplementedError("Unsupported system interface: {}".format(intfs))

    @classmethod
    def _validate_fabric_intfs(cls, intfs):
        """Validate fabric interface collection.

        Args:
            intfs (:obj:`Container` [`SystemIntf` ]):
        """

        known_intfs = set( ("syscon", "softreg", "memory_piton", "memory_piton_axi4r", "memory_piton_axi4w") )

        # categorization
        classes = {}
        for intf in intfs:
            classes.setdefault(intf.name, set()).add(intf)

        # validate
        if (len(classes["syscon"]) <= 1
                and len(classes["softreg"]) == 1
                and (len(classes["memory_piton"]) == 1 or
                    (len(classes["memory_piton_axi4r"]) == 1 and len(classes["memory_piton_axi4w"]) == 1))
                and sum(len(x) for k, x in classes.items()
                    if k not in known_intfs) == 0):
            return

        raise NotImplementedError("Unsupported fabric interface: {}".format(intfs))

    @classmethod
    def build_system_piton_vanilla(cls, context, fabric_axi4 = True, *,
            name = "prga_system", fabric_wrapper = None):
        """Create the system top wrapping the reconfigurable fabric. This method is implemented specifically for
        OpenPiton vanilla integration.

        Args:
            context (`Context`):
            fabric_axi4 (:obj:`bool`): If set, use AXI4-based fabric interface

        Keyword Args:
            name (:obj:`str`): Name of the system top module
            fabric_wrapper (:obj:`str` or :obj:`bool`): If set to a :obj:`str`, or set to ``True`` \(in which
                case it is converted to ``{name}_core``\), an extra layer of wrapper is created around the fabric
                and instantiated in the top-level module
        """
        cls._register_cells(context)

        system_intfs = set([SystemIntf.syscon,
            SystemIntf.reg_piton("reg"),
            SystemIntf.memory_piton("ccm"),
            ])

        fabric_intfs = None
        if fabric_axi4:
            fabric_intfs = set([FabricIntf.syscon("app"),
                FabricIntf.softreg("ureg", strb = True),
                FabricIntf.memory_piton_axi4r(),
                FabricIntf.memory_piton_axi4w(),
                ])
        else:
            fabric_intfs = set([FabricIntf.syscon("app"),
                FabricIntf.softreg("ureg", strb = True),
                FabricIntf.memory_piton("uccm"),
                ])
        
        if fabric_wrapper is True:
            fabric_wrapper = name + "_core"

        # record fabric interface, and create the application interface
        if (integration := getattr(context.summary, "integration", None)) is None:
            integration = context.summary.integration = {}
        integration["fabric_intfs"] = fabric_intfs
        app_intf = integration["app_intf"] = cls._create_app_intf(context, fabric_intfs)
        IOPlanner.autoplan(context, app_intf)

        # create system
        system = context.system_top = Module(name, view = ModuleView.design, module_class = ModuleClass.aux)
        cls._create_intf_ports_syscon       (system, True)
        cls._create_intf_ports_reg          (system, True, "reg_", addr_width = 12, data_bytes = 8, strb = True)
        cls._create_intf_ports_memory_piton (system, False, "ccm_")

        # instantiate syscomplex in system
        syscomplex = ModuleUtils.instantiate(system,
                context.database[ModuleView.design, "prga_syscomplex.axi4" if fabric_axi4 else "prga_syscomplex"],
                "i_syscomplex")

        # connect system ports to syscomplex
        for port_name, port in system.ports.items():
            if port.direction.is_input:
                NetUtils.connect(port, syscomplex.pins[port_name])
            else:
                NetUtils.connect(syscomplex.pins[port_name], port)

        # instantiate fabric
        nets = None
        if fabric_wrapper:
            # build fabric wrapper
            core = context._database[ModuleView.design, fabric_wrapper] = Module(fabric_wrapper,
                    view = ModuleView.design, module_class = ModuleClass.aux)

            # create ports in fabric wrapper
            cls._create_intf_ports_syscon(core, True, "app_")
            cls._create_intf_ports_reg(core, True, "ureg_",
                    ecc = "parity_even", addr_width = 12, data_bytes = 8, strb = True)

            if fabric_axi4:
                cls._create_intf_ports_memory_piton_axi4r(core, False, unused = True)
                cls._create_intf_ports_memory_piton_axi4w(core, False, unused = True)
            else:
                cls._create_intf_ports_memory_piton(core, False, "uccm_", ecc = "parity_even")

            # instantiate fabric within fabric wrapper
            fabric = ModuleUtils.instantiate(core,
                    context.database[ModuleView.design, context.top.key], "i_fabric")
            nets = core.ports

            # instantiate fabric wrapper in system
            core = ModuleUtils.instantiate(system, core, "i_core")

            # connect syscomplex with fabric wrapper
            for pin_name, pin in core.pins.items():
                if pin_name == "app_clk":
                    NetUtils.connect(syscomplex.pins["aclk"], pin)
                elif pin_name == "app_rst_n":
                    NetUtils.connect(syscomplex.pins["urst_n"], pin)
                elif syscomplex_pin := syscomplex.pins.get(pin_name):
                    if pin.model.direction.is_input:
                        NetUtils.connect(syscomplex_pin, pin)
                    else:
                        NetUtils.connect(pin, syscomplex_pin)
                else:
                    _logger.warning("Unconnected fabric port: {}".format(pin_name)) 

        else:
            # instantiate fabric within system
            fabric = ModuleUtils.instantiate(system,
                    context.database[ModuleView.design, context.top.key], "i_fabric")
            nets = syscomplex.pins

        # connect fabric
        for name, port in app_intf.ports.items():
            if name == "clk":
                NetUtils.connect(nets["app_clk"],   fabric.pins[(IOType.ipin, ) + port.get_io_constraint()])
            elif name == "rst_n":
                NetUtils.connect(nets["app_rst_n"], fabric.pins[(IOType.ipin, ) + port.get_io_constraint()])
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

    @classmethod
    def build_system(cls, context,
            system_intfs = (SystemIntf.syscon,
                SystemIntf.reg_piton("reg"),
                SystemIntf.memory_piton("ccm"),
                ),
            fabric_intfs = (FabricIntf.syscon("app"),
                FabricIntf.softreg("ureg"),
                FabricIntf.memory_piton_axi4r,
                FabricIntf.memory_piton_axi4w,
                ),
            *,
            name = "prga_system",
            fabric_wrapper = None):
        """Create the system top wrapping the reconfigurable fabric.

        Args:
            context (`Context`):
            system_intfs (:obj:`Container` [`SystemIntf` ]): System interfaces
            fabric_intfs (:obj:`Container` [`FabricIntf` ]): Fabric (application-available) interfaces

        Keyword Args:
            name (:obj:`str`): Name of the system top module
            fabric_wrapper (:obj:`str` or :obj:`bool`): If set to a :obj:`str`, or set to ``True`` \(in which
                case it is converted to ``{name}_core``\), an extra layer of wrapper is created around the fabric
                and instantiated in the top-level module
        """
        # TODO
        raise NotImplementedError

        system_intfs = set(iter(system_intfs))
        fabric_intfs = set(iter(fabric_intfs))

        cls._validate_system_intfs(system_intfs)
        cls._validate_fabric_intfs(fabric_intfs)

        if fabric_wrapper is True:
            fabric_wrapper = name + "_core"

        # record fabric interface, and create the application interface
        if (integration := getattr(context.summary, "integration", None)) is None:
            integration = context.summary.integration = {}
        integration["fabric_intfs"] = fabric_intfs
        app_intf = integration["app_intf"] = cls._create_app_intf(context, fabric_intfs)
        IOPlanner.autoplan(context, app_intf)

        # create system
        system = context.system_top = Module(name, view = ModuleView.design, module_class = ModuleClass.aux)

        # create ports for the top-level module
        for interface in system_intfs:
            prefix = "" if interface.id_ is None else (interface.id_ + "_")
            if interface.is_syscon:
                cls._create_intf_ports_syscon(system, True, prefix)
            elif interface.is_reg_piton:
                cls._create_intf_ports_reg(system, True, prefix,
                        addr_width = interface.addr_width,
                        data_bytes = 2 ** interface.data_bytes_log2,
                        strb = True)
            elif interface.is_memory_piton:
                cls._create_intf_ports_memory_piton(system, False, prefix)
            else:
                raise PRGAAPIError("Unsupported system interface: {}".format(interface))

        # instantiate syscomplex in system
        syscomplex = None
        for interface in fabric_intfs:
            if interface.is_ccm_piton:
                assert syscomplex is None
                syscomplex = ModuleUtils.instantiate(system,
                        context.database[ModuleView.design, "prga_syscomplex"],
                        "i_syscomplex")
            elif interface.is_ccm_piton_axi4:
                assert syscomplex is None
                syscomplex = ModuleUtils.instantiate(system,
                        context.database[ModuleView.design, "prga_syscomplex.axi4"],
                        "i_syscomplex")
        assert syscomplex is not None

        # connect system ports to syscomplex
        for port_name, port in system.ports.items():
            if port.direction.is_input:
                NetUtils.connect(port, syscomplex.pins[port_name])
            else:
                NetUtils.connect(syscomplex.pins[port_name], port)

        # instantiate fabric
        nets = None
        if fabric_wrapper:
            # build fabric wrapper
            core = context._database[ModuleView.design, fabric_wrapper] = Module(fabric_wrapper,
                    view = ModuleView.design, module_class = ModuleClass.aux)

            # create ports in fabric wrapper
            for i in fabric_intfs:
                if i.is_syscon:
                    cls._create_intf_ports_syscon(core, True, "" if i.id_ is None else (i.id_ + "_"))
                elif i.is_softreg_simple:
                    if not i.ecc_type.is_parity_even:
                        raise NotImplementedError("Unsupported softreg ECC settings ({}) for {}"
                                .format(i.ecc_type.name, i))
                    cls._create_intf_ports_reg(core, True, "" if i.id_ is None else (i.id_ + "_"),
                            i.addr_width, 2 ** i.data_bytes_log2, i.ecc_type.is_parity_even)
                elif i.is_ccm_piton:
                    cls._create_intf_ports_memory_piton(core, False,
                            "" if i.id_ is None else (i.id_ + "_"), ecc = True)
                elif i.is_ccm_piton_axi4:
                    cls._create_intf_ports_memory_piton_axi4(core, False,
                            "" if i.id_ is None else (i.id_ + "_"), unused = True)
                else:
                    assert False

            # instantiate fabric within fabric wrapper
            fabric = ModuleUtils.instantiate(core,
                    context.database[ModuleView.design, context.top.key], "i_fabric")
            nets = core.ports

            # instantiate fabric wrapper in system
            core = ModuleUtils.instantiate(system, core, "i_core")

            # connect syscomplex with fabric wrapper
            for pin_name, pin in core.pins.items():
                if pin_name == "app_clk":
                    NetUtils.connect(syscomplex.pins["aclk"], pin)
                elif pin_name == "app_rst_n":
                    NetUtils.connect(syscomplex.pins["urst_n"], pin)
                elif syscomplex_pin := syscomplex.pins.get(pin_name):
                    if pin.model.direction.is_input:
                        NetUtils.connect(syscomplex_pin, pin)
                    else:
                        NetUtils.connect(pin, syscomplex_pin)
                else:
                    _logger.warning("Unconnected design port: {}".format(pin_name)) 

        else:
            # instantiate fabric within system
            fabric = ModuleUtils.instantiate(system,
                    context.database[ModuleView.design, context.top.key], "i_fabric")
            nets = syscomplex.pins

        # connect fabric
        for name, port in intf.ports.items():
            if name == "clk":
                NetUtils.connect(nets["app_clk"],   fabric.pins[(IOType.ipin, ) + port.get_io_constraint()])
            elif name == "rst_n":
                NetUtils.connect(nets["app_rst_n"], fabric.pins[(IOType.ipin, ) + port.get_io_constraint()])
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
