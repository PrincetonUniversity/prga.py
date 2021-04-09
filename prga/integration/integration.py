# -*- encoding: ascii -*-

from .common import InterfaceClass
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
    def _create_intf_ccm_axi4(cls, module, slave = False, prefix = "", unused = False):
        """Create cache-coherent memory interface in AXI4 protocol. By default this creates the master interface that
        sends AW/AR/W requests and receive B/R responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
            unused (:obj:`bool`): If set, unused but required AXI4 ports are also added, including ``AWPROT``,
                ``AWQOS``, ``AWLOCK``, ``AWREGION``, ``ARPROT``, ``ARQOS``, ``ARREGION``.
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        d = {}

        # AW channel
        d[prefix + "awready"]       = ModuleUtils.create_port(module, prefix + "awready", 1, i)
        d[prefix + "awvalid"]       = ModuleUtils.create_port(module, prefix + "awvalid", 1, o)
        d[prefix + "awid"]          = ModuleUtils.create_port(module, prefix + "awid", 1, o)
        d[prefix + "awaddr"]        = ModuleUtils.create_port(module, prefix + "awaddr", 40, o)
        d[prefix + "awlen"]         = ModuleUtils.create_port(module, prefix + "awlen", 8, o)
        d[prefix + "awsize"]        = ModuleUtils.create_port(module, prefix + "awsize", 3, o)
        d[prefix + "awburst"]       = ModuleUtils.create_port(module, prefix + "awburst", 2, o)
        d[prefix + "awcache"]       = ModuleUtils.create_port(module, prefix + "awcache", 4, o)
        d[prefix + "awuser"]        = ModuleUtils.create_port(module, prefix + "awuser", 1, o)
        if unused:
            d[prefix + "awlock"]    = ModuleUtils.create_port(module, prefix + "awlock", 1, o)
            d[prefix + "awprot"]    = ModuleUtils.create_port(module, prefix + "awprot", 3, o)
            d[prefix + "awqos"]     = ModuleUtils.create_port(module, prefix + "awqos", 4, o)
            d[prefix + "awregion"]  = ModuleUtils.create_port(module, prefix + "awregion", 4, o)

        # W channel
        d[prefix + "wready"]        = ModuleUtils.create_port(module, prefix + "wready", 1, i)
        d[prefix + "wvalid"]        = ModuleUtils.create_port(module, prefix + "wvalid", 1, o)
        d[prefix + "wdata"]         = ModuleUtils.create_port(module, prefix + "wdata", 64, o)
        d[prefix + "wstrb"]         = ModuleUtils.create_port(module, prefix + "wstrb", 8, o)
        d[prefix + "wlast"]         = ModuleUtils.create_port(module, prefix + "wlast", 1, o)
        d[prefix + "wuser"]         = ModuleUtils.create_port(module, prefix + "wuser", 1, o)

        # B channel
        d[prefix + "bready"]        = ModuleUtils.create_port(module, prefix + "bready", 1, o)
        d[prefix + "bvalid"]        = ModuleUtils.create_port(module, prefix + "bvalid", 1, i)
        d[prefix + "bresp"]         = ModuleUtils.create_port(module, prefix + "bresp", 2, i)
        d[prefix + "bid"]           = ModuleUtils.create_port(module, prefix + "bid", 1, i)

        # AR channel
        d[prefix + "arready"]       = ModuleUtils.create_port(module, prefix + "arready", 1, i)
        d[prefix + "arvalid"]       = ModuleUtils.create_port(module, prefix + "arvalid", 1, o)
        d[prefix + "arid"]          = ModuleUtils.create_port(module, prefix + "arid", 1, o)
        d[prefix + "araddr"]        = ModuleUtils.create_port(module, prefix + "araddr", 40, o)
        d[prefix + "arlen"]         = ModuleUtils.create_port(module, prefix + "arlen", 8, o)
        d[prefix + "arsize"]        = ModuleUtils.create_port(module, prefix + "arsize", 3, o)
        d[prefix + "arburst"]       = ModuleUtils.create_port(module, prefix + "arburst", 2, o)
        d[prefix + "arlock"]        = ModuleUtils.create_port(module, prefix + "arlock", 1, o)
        d[prefix + "arcache"]       = ModuleUtils.create_port(module, prefix + "arcache", 4, o)
        d[prefix + "aruser"]        = ModuleUtils.create_port(module, prefix + "aruser", 64 + 4 + 1, o)
        if unused:
            d[prefix + "arprot"]    = ModuleUtils.create_port(module, prefix + "arprot", 3, o)
            d[prefix + "arqos"]     = ModuleUtils.create_port(module, prefix + "arqos", 4, o)
            d[prefix + "arregion"]  = ModuleUtils.create_port(module, prefix + "arregion", 4, o)

        # R channel
        d[prefix + "rready"]        = ModuleUtils.create_port(module, prefix + "rready", 1, o)
        d[prefix + "rvalid"]        = ModuleUtils.create_port(module, prefix + "rvalid", 1, i)
        d[prefix + "rresp"]         = ModuleUtils.create_port(module, prefix + "rresp", 2, i)
        d[prefix + "rid"]           = ModuleUtils.create_port(module, prefix + "rid", 1, i)
        d[prefix + "rdata"]         = ModuleUtils.create_port(module, prefix + "rdata", 64, i)
        d[prefix + "rlast"]         = ModuleUtils.create_port(module, prefix + "rlast", 1, i)

        return d

    @classmethod
    def _register_cells(cls, context):
        """Register integration-related modules in to the module database.

        Args:
            context (`Context`):
        """
        # 1. add prga_system header
        context._add_verilog_header("prga_system.vh", "include/prga_system.tmpl.vh")
        context._add_verilog_header("prga_axi4.vh", "include/prga_axi4.tmpl.vh")

        # 2. register modules
        # 2.1 modules that we don't need to know about their ports
        for d in ("prga_ctrl", "prga_ecc_parity", "prga_mprot",
                "prga_sax", "prga_uprot", "prga_ccm_transducer"):
            context._database[ModuleView.design, d] = Module(d,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "{}.tmpl.v".format(d))
        for d in ("prga_l15_transducer", ):
            context._database[ModuleView.design, d] = Module(d,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "piton/{}.v".format(d))
        for d in ("prga_fe_axi4lite", ):
            context._database[ModuleView.design, d] = Module(d,
                    view = ModuleView.design,
                    module_class = ModuleClass.aux,
                    verilog_template = "axi4lite/{}.tmpl.v".format(d))
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
                verilog_template = "prga_syscomplex.tmpl.v")
        cls._create_intf_syscon     (syscomplex, True)          # programming clock and reset
        cls._create_intf_syscon     (syscomplex, False, "a")    # application clock and reset
        cls._create_intf_reg        (syscomplex, True, "reg_")
        cls._create_intf_ccm        (syscomplex, False, "ccm_")
        cls._create_intf_simpleprog (syscomplex, False, "prog_")
        cls._create_intf_reg        (syscomplex, False, "ureg_", True)
        cls._create_intf_ccm        (syscomplex, True, "uccm_", True)
        ModuleUtils.create_port(syscomplex, "urst_n", 1, PortDirection.output)
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_ctrl"], "i_ctrl")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_ccm_transducer"], "i_transducer")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_sax"], "i_sax")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_uprot"], "i_uprot")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_mprot"], "i_mprot")

        # 3. AXI4 interface
        mprot = context._database[ModuleView.design, "prga_mprot.axi4"] = Module("prga_mprot",
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "ccm_axi4/prga_mprot.tmpl.v",
                key = "prga_mprot.axi4")
        ModuleUtils.instantiate(mprot, context.database[ModuleView.design, "prga_ecc_parity"], "i_ecc_checker")
        ModuleUtils.instantiate(mprot, context.database[ModuleView.design, "prga_valrdy_buf"], "i_buf")

        syscomplex = context._database[ModuleView.design, "prga_syscomplex.axi4"] = Module("prga_syscomplex",
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "ccm_axi4/prga_syscomplex.tmpl.v",
                key = "prga_syscomplex.axi4")
        cls._create_intf_syscon     (syscomplex, True)          # programming clock and reset
        cls._create_intf_syscon     (syscomplex, False, "a")    # application clock and reset
        cls._create_intf_reg        (syscomplex, True, "reg_")
        cls._create_intf_ccm        (syscomplex, False, "ccm_")
        cls._create_intf_simpleprog (syscomplex, False, "prog_")
        cls._create_intf_reg        (syscomplex, False, "ureg_", True)
        cls._create_intf_ccm_axi4   (syscomplex, True)
        ModuleUtils.create_port(syscomplex, "urst_n", 1, PortDirection.output)
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_ctrl"], "i_ctrl")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_ccm_transducer"], "i_transducer")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_sax"], "i_sax")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_uprot"], "i_uprot")
        ModuleUtils.instantiate(syscomplex, context.database[ModuleView.design, "prga_mprot.axi4"], "i_mprot")

    @classmethod
    def _create_design_intf(cls, context, interfaces):
        """Create a `AppIntf` object with the specified ``interfaces``.

        Args:
            context (`Context`):
            interfaces (:obj:`Container` [`InterfaceClass` ]): `InterfaceClass.syscon` is always added

        Returns:
            `AppIntf`:
        """
        d = AppIntf("design")

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
            elif interface.is_ccm_axi4:
                # AW channel
                d.add_port("awready",	            PortDirection.input_,	1)
                d.add_port("awvalid",	            PortDirection.output,	1)
                d.add_port("awid",	                PortDirection.output,	1)
                d.add_port("awaddr",	            PortDirection.output,	40)
                d.add_port("awlen",	                PortDirection.output,	8)
                d.add_port("awsize",	            PortDirection.output,	3)
                d.add_port("awburst",	            PortDirection.output,	2)
                d.add_port("awcache",	            PortDirection.output,	4)
                d.add_port("awuser",	            PortDirection.output,	1)
                d.add_port("awlock",	            PortDirection.output,	1)
                d.add_port("awprot",	            PortDirection.output,	3)
                d.add_port("awqos",	                PortDirection.output,	4)
                d.add_port("awregion",	            PortDirection.output,	4)

                # W channel
                d.add_port("wready",	            PortDirection.input_,	1)
                d.add_port("wvalid",	            PortDirection.output,	1)
                d.add_port("wdata",	                PortDirection.output,	64)
                d.add_port("wstrb",	                PortDirection.output,	8)
                d.add_port("wlast",	                PortDirection.output,	1)
                d.add_port("wuser",	                PortDirection.output,	1)

                # B channel
                d.add_port("bready",	            PortDirection.output,	1)
                d.add_port("bvalid",	            PortDirection.input_,	1)
                d.add_port("bresp",	                PortDirection.input_,	2)
                d.add_port("bid",	                PortDirection.input_,	1)

                # AR channel
                d.add_port("arready",	            PortDirection.input_,	1)
                d.add_port("arvalid",	            PortDirection.output,	1)
                d.add_port("arid",	                PortDirection.output,	1)
                d.add_port("araddr",	            PortDirection.output,	40)
                d.add_port("arlen",	                PortDirection.output,	8)
                d.add_port("arsize",	            PortDirection.output,	3)
                d.add_port("arburst",	            PortDirection.output,	2)
                d.add_port("arlock",	            PortDirection.output,	1)
                d.add_port("arcache",	            PortDirection.output,	4)
                d.add_port("aruser",	            PortDirection.output,	64 + 4 + 1)
                d.add_port("arprot",	            PortDirection.output,	3)
                d.add_port("arqos",	                PortDirection.output,	4)
                d.add_port("arregion",	            PortDirection.output,	4)

                # R channel
                d.add_port("rready",	            PortDirection.output,	1)
                d.add_port("rvalid",	            PortDirection.input_,	1)
                d.add_port("rresp",	                PortDirection.input_,	2)
                d.add_port("rid",	                PortDirection.input_,	1)
                d.add_port("rdata",	                PortDirection.input_,	64)
                d.add_port("rlast",	                PortDirection.input_,	1)

            else:
                raise PRGAAPIError("Unsupported interface class: {:r}".format(interface))

        # 3. return design interface object
        return d

    @classmethod
    def build_system(cls, context, interfaces = (InterfaceClass.ccm_simple, InterfaceClass.reg_simple), *,
            name = "prga_system", fabric_wrapper = None):
        """Create the system top wrapping the reconfigurable fabric.

        Args:
            context (`Context`):
            interfaces (:obj:`Container` [`InterfaceClass` ]): Interfaces added

        Keyword Args:
            name (:obj:`str`): Name of the system top module
            fabric_wrapper (:obj:`str` or :obj:`bool`): If set to a :obj:`str`, or set to ``True`` \(in which
                case it is converted to ``{name}_core``\), an extra layer of wrapper is created around the fabric
                and instantiated in the top-level module
        """
        interfaces = set(iter(interfaces))
        if interfaces not in (
                {InterfaceClass.ccm_simple, InterfaceClass.reg_simple},
                {InterfaceClass.ccm_axi4, InterfaceClass.reg_simple},
                ):
            raise NotImplementedError("Unsupported interface combinations: {:r}".format(interfaces))

        if fabric_wrapper is True:
            fabric_wrapper = name + "_core"

        # get or create design interface
        if (intf := getattr(context.summary, "intf", None)) is None:
            intf = context.summary.intf = cls._create_design_intf(context, interfaces)
        IOPlanner.autoplan(context, intf)

        # create system
        system = context.system_top = Module(name, view = ModuleView.design, module_class = ModuleClass.aux)

        # create ports
        cls._create_intf_syscon(system, True)
        cls._create_intf_reg(system, True, "reg_")
        cls._create_intf_ccm(system, False, "ccm_")

        # instantiate syscomplex in system
        syscomplex = None
        if InterfaceClass.ccm_simple in interfaces:
            syscomplex = ModuleUtils.instantiate(system,
                    context.database[ModuleView.design, "prga_syscomplex"],
                    "i_syscomplex")
        elif InterfaceClass.ccm_axi4 in interfaces:
            syscomplex = ModuleUtils.instantiate(system,
                    context.database[ModuleView.design, "prga_syscomplex.axi4"],
                    "i_syscomplex")
        else:
            assert False

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
            cls._create_intf_syscon(core, True, "u")
            for i in interfaces:
                if i.is_reg_simple:
                    cls._create_intf_reg(core, True, "ureg_", ecc = True)
                elif i.is_ccm_simple:
                    cls._create_intf_ccm(core, False, "uccm_", ecc = True)
                elif i.is_ccm_axi4:
                    cls._create_intf_ccm_axi4(core, unused = True)

            # instantiate fabric within fabric wrapper
            fabric = ModuleUtils.instantiate(core,
                    context.database[ModuleView.design, context.top.key], "i_fabric")
            nets = core.ports

            # instantiate fabric wrapper in system
            core = ModuleUtils.instantiate(system, core, "i_core")

            # connect syscomplex with fabric wrapper
            for pin_name, pin in core.pins.items():
                if pin_name == "uclk":
                    NetUtils.connect(syscomplex.pins["aclk"], pin)
                elif pin_name == "urst_n":
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
