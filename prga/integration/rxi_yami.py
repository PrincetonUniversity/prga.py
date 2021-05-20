# -*- encoding: ascii -*-

from .common import SystemIntf, FabricIntf
from ..core.common import ModuleView, ModuleClass, IOType
from ..netlist import Module, PortDirection, ModuleUtils, NetUtils
from ..tools.util import AppIntf
from ..tools.ioplan import IOPlanner

import logging
_logger = logging.getLogger(__name__)

__all__ = []

# ----------------------------------------------------------------------------
# -- Integration module for RXI/YAMI interfaces ------------------------------
# ----------------------------------------------------------------------------
class IntegrationRXIYAMI(object):
    """Wrapper class for utility functions that helps integrating the fabric into a hybrid system. This class handles
    RXI/YAMI specifically."""

    @classmethod
    def _create_ports_syscon(cls, module, *, slave = False, prefix = ""):
        _so, _mo = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        _mcp = ModuleUtils.create_port
        ports = [
                _mcp(module, prefix + "clk",   1, _mo, is_clock = True),
                _mcp(module, prefix + "rst_n", 1, _mo),
                ]

        return {port.name[len(prefix):]: port for port in ports}

    @classmethod
    def _create_ports_rxi(cls, module, *, slave = False, prefix = "",
            addr_width = 12, data_bytes_log2 = 2, fabric = False, prog = False):

        _so, _mo = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        _mcp = ModuleUtils.create_port
        ports = [
                _mcp(module, prefix + "req_rdy",   1,                    _so),
                _mcp(module, prefix + "req_vld",   1,                    _mo),
                _mcp(module, prefix + "req_addr",  addr_width,           _mo),
                _mcp(module, prefix + "req_strb",  1 << data_bytes_log2, _mo),
                _mcp(module, prefix + "req_data",  8 << data_bytes_log2, _mo),
                _mcp(module, prefix + "resp_rdy",  1,                    _mo),
                _mcp(module, prefix + "resp_vld",  1,                    _so),
                _mcp(module, prefix + "resp_data", 8 << data_bytes_log2, _so),
                ]

        if prog:
            # programming interface
            ports.extend([
                _mcp(module, prefix + "done",          1, _so),
                _mcp(module, prefix + "resp_err",      1, _so),
                ])

            if fabric:
                ports.extend([
                    _mcp(module, prefix + "rst",        1, _so),
                    ])

        elif fabric:
            # fabric interface, not system interface
            ports.extend([
                _mcp(module, prefix + "resp_sync",     1, _so),
                _mcp(module, prefix + "resp_syncaddr", 5, _so),
                _mcp(module, prefix + "resp_parity",   1, _so),
                ])

        return {port.name[len(prefix):]: port for port in ports}

    @classmethod
    def _create_ports_yami(cls, module, intf, *, slave = False, prefix = "", fabric = False):
        _so, _mo = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        _mcp = ModuleUtils.create_port
        ports = [
                _mcp(module, prefix + "fmc_rdy",  1,                             _mo),
                _mcp(module, prefix + "fmc_vld",  1,                             _so),
                _mcp(module, prefix + "fmc_type", 5,                             _so),
                _mcp(module, prefix + "fmc_size", 3,                             _so),
                _mcp(module, prefix + "fmc_addr", intf.fmc_addr_width,           _so),
                _mcp(module, prefix + "fmc_data", 8 << intf.fmc_data_bytes_log2, _so),
                _mcp(module, prefix + "mfc_rdy",  1,                             _so),
                _mcp(module, prefix + "mfc_vld",  1,                             _mo),
                _mcp(module, prefix + "mfc_type", 4,                             _mo),
                _mcp(module, prefix + "mfc_addr", intf.mfc_addr_width,           _mo),
                _mcp(module, prefix + "mfc_data", 8 << intf.mfc_data_bytes_log2, _mo),
                ]

        if fabric:
            # fabric interface, add parity check
            ports.append(_mcp(module, prefix + "fmc_parity",    1, _so))

        return {port.name[len(prefix):]: port for port in ports}

    @classmethod
    def _register_cells(cls, context, rxi, yami):
        """Register integration-related modules in to the module database.

        Args:
            context (`Context`):
            rxi (`SystemIntf`):
            yami (`SystemIntf`):
        """
        # 1. add RXI/YAMI headers
        context.add_verilog_header("prga_rxi.vh", "rxi/include/prga_rxi.tmpl.vh", intf = rxi)
        context.add_verilog_header("prga_yami.vh", "yami/include/prga_yami.tmpl.vh", intf = yami)

        # 2. register modules that we don't need to know the ports
        deps = {
                "prga_rxi_fe_iq":   ("prga_fifo", "prga_arb_robinfair"),
                "prga_rxi_fe_phsr": ("prga_byteaddressable_reg", "prga_arb_robinfair"),
                "prga_rxi_fe":      ("prga_clkdiv", "prga_sync_basic", "prga_byteaddressable_reg", "prga_rxi_fe_iq",
                    "prga_fifo", "prga_tokenfifo", "prga_rxi_fe_phsr"),
                "prga_rxi_be":      ("prga_fifo", ),
                }

        for d, subs in deps.items():
            m = context._add_module(Module(d,
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "rxi/impl/{}.v".format(d),
                verilog_dep_headers = ("prga_rxi.vh", )))
            for sub in subs:
                ModuleUtils.instantiate(m, context.database[ModuleView.design, sub], sub)

        context._add_module(Module("prga_rxi_axi4lite_transducer",
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.aux,
            verilog_template = "rxi/axi4lite/prga_rxi_axi4lite_transducer.v",
            verilog_dep_headers = ("prga_rxi.vh", "prga_axi4.vh")))

        for d in ("prga_yami_be", "prga_yami_fe"):
            context._add_module(Module(d,
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "yami/impl/{}.v".format(d),
                verilog_dep_headers = ("prga_utils.vh", "prga_yami.vh")))

        context._add_module(Module("prga_yami_tri_transducer",
            is_cell = True,
            view = ModuleView.design,
            module_class = ModuleClass.aux,
            verilog_template = "yami/piton/prga_yami_tri_transducer.v",
            verilog_dep_headers = ("prga_yami.vh", )))

        # 3. register modules that we need to know about the ports
        if True:
            # prga RXI interface
            m = context._add_module(Module("prga_rxi",
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "rxi/impl/prga_rxi.v",
                verilog_dep_headers = ("prga_rxi.vh", )))
            cls._create_ports_syscon(m, slave = True)
            cls._create_ports_syscon(m, prefix = "a")
            cls._create_ports_rxi(m, slave = True, prefix = "s_",
                    addr_width = rxi.addr_width, data_bytes_log2 = rxi.data_bytes_log2)
            cls._create_ports_rxi(m, prefix = "prog_", prog = True,
                    addr_width = 4, data_bytes_log2 = rxi.data_bytes_log2)
            ModuleUtils.create_port(m, "prog_rst_n",        1,            "output")
            ModuleUtils.create_port(m, "yami_err_i",        rxi.num_yami, "input")
            ModuleUtils.create_port(m, "yami_deactivate_o", 1,            "output")
            ModuleUtils.create_port(m, "yami_activate_o",   rxi.num_yami, "output")
            ModuleUtils.create_port(m, "app_rst_n",         1,            "output")
            cls._create_ports_rxi(m, prefix = "m_", fabric = True,
                    addr_width = rxi.addr_width, data_bytes_log2 = rxi.data_bytes_log2)

        if True:
            # prga YAMI interface
            m = context._add_module(Module("prga_yami",
                is_cell = True,
                view = ModuleView.design,
                module_class = ModuleClass.aux,
                verilog_template = "yami/impl/prga_yami.v",
                verilog_dep_headers = ("prga_yami.vh", )))
            cls._create_ports_syscon(m, slave = True)
            cls._create_ports_syscon(m, slave = True, prefix = "a")
            ModuleUtils.create_port(m, "err_o",         1, "output")
            ModuleUtils.create_port(m, "deactivate_i",  1, "input")
            ModuleUtils.create_port(m, "activate_i",    1, "input")
            cls._create_ports_rxi(m, slave = True, prefix = "creg_",
                    addr_width = 8, data_bytes_log2 = yami.fmc_data_bytes_log2)
            cls._create_ports_yami(m, yami, slave = True, prefix = "s")
            cls._create_ports_yami(m, yami, fabric = True, prefix = "a")

    @classmethod
    def build_system(cls, context, *,

            # RXI configuration
            rxi_addr_width = 12,
            rxi_data_bytes_log2 = 2,

            # YAMI configuration
            num_yami = 1,
            yami_fmc_addr_width = 40,
            yami_fmc_data_bytes_log2 = 3,
            yami_mfc_addr_width = 16,   
            yami_mfc_data_bytes_log2 = 4,
            yami_cacheline_bytes_log2 = 4,

            # other configuration
            name = "prga_system",
            fabric_wrapper = None):

        """Create the system top wrapping the reconfigurable fabric, implementing RXI/YAMI interface.

        Args:
            context (`Context`):

        Keyword Args:
            rxi_addr_width (:obj:`int`):
            rxi_data_bytes_log2 (:obj:`int`): 2 for 4B, 3 for 8B
            num_yami (:obj:`int`): Number of YAMI interfaces
            yami_fmc_addr_width (:obj:`int`):
            yami_fmc_data_bytes_log2 (:obj:`int`):
            yami_mfc_addr_width (:obj:`int`):
            yami_mfc_data_bytes_log2 (:obj:`int`):
            yami_cacheline_bytes_log2 (:obj:`int`):
            name (:obj:`str`): Name of the system top module
            fabric_wrapper (:obj:`str` or :obj:`bool`): If set to a :obj:`str`, or set to ``True`` \(in which
                case it is converted to ``{name}_core``\), an extra layer of wrapper is created around the fabric
                and instantiated in the top-level module
        """

        rxi = SystemIntf.rxi(None, rxi_addr_width, rxi_data_bytes_log2, num_yami)
        yami = SystemIntf.yami(None, yami_fmc_addr_width, yami_fmc_data_bytes_log2,
                yami_mfc_addr_width, yami_mfc_data_bytes_log2, yami_cacheline_bytes_log2)

        cls._register_cells(context, rxi, yami)

        system_intfs = set(
                [SystemIntf.syscon, rxi] +
                [
                    SystemIntf.yami(
                        "i{}".format(i),
                        yami_fmc_addr_width,
                        yami_fmc_data_bytes_log2,
                        yami_mfc_addr_width,
                        yami_mfc_data_bytes_log2,
                        yami_cacheline_bytes_log2)
                    for i in range(num_yami)
                    ])
        fabric_intfs = set(
                [
                    FabricIntf.syscon,
                    FabricIntf.rxi(
                        None,
                        rxi_addr_width,
                        rxi_data_bytes_log2,
                        num_yami),
                    ] +
                [
                    FabricIntf.yami(
                        "i{}".format(i),
                        yami_fmc_addr_width,
                        yami_fmc_data_bytes_log2,
                        yami_mfc_addr_width,
                        yami_mfc_data_bytes_log2,
                        yami_cacheline_bytes_log2)
                    for i in range(num_yami)
                    ])

        if fabric_wrapper is True:
            fabric_wrapper = name + "_core"

        # record interfaces, and map fabric I/Os
        if (integration := getattr(context.summary, "integration", None)) is None:
            integration = context.summary.integration = {}
        integration["fabric_intfs"] = fabric_intfs
        app = integration["app_intf"] = AppIntf("design")

        # fill the application interface object
        if True:
            # add syscon first
            clk     = app.add_port("clk", PortDirection.input_)
            rst_n   = app.add_port("rst_n", PortDirection.input_)

            # needs special handling of clock
            for g in context.globals_.values():
                if g.is_clock:
                    clk.set_io_constraint(g.bound_to_position, g.bound_to_subtile)
                    break
            if clk.get_io_constraint() is None:
                raise PRGAInternalError("No clock found in the fabric")

            # add RXI ports
            app.add_port("rxi_req_rdy",         "output", 1)
            app.add_port("rxi_req_vld",         "input",  1)
            app.add_port("rxi_req_addr",        "input",  rxi_addr_width)
            app.add_port("rxi_req_strb",        "input",  1 << rxi_data_bytes_log2)
            app.add_port("rxi_req_data",        "input",  8 << rxi_data_bytes_log2)
            app.add_port("rxi_resp_rdy",        "input",  1)
            app.add_port("rxi_resp_vld",        "output", 1)
            app.add_port("rxi_resp_sync",       "output", 1)
            app.add_port("rxi_resp_syncaddr",   "output", 5)    # 32 HSRs
            app.add_port("rxi_resp_data",       "output", 8 << rxi_data_bytes_log2)
            app.add_port("rxi_resp_parity",     "output", 1)

            # add YAMI ports
            for i in range(num_yami):
                app.add_port("yami_i{}_fmc_rdy".format(i),      "input",  1)
                app.add_port("yami_i{}_fmc_vld".format(i),      "output", 1)
                app.add_port("yami_i{}_fmc_type".format(i),     "output", 5)
                app.add_port("yami_i{}_fmc_size".format(i),     "output", 3)
                app.add_port("yami_i{}_fmc_addr".format(i),     "output", yami_fmc_addr_width)
                app.add_port("yami_i{}_fmc_data".format(i),     "output", 8 << yami_fmc_data_bytes_log2)
                app.add_port("yami_i{}_fmc_parity".format(i),   "output", 1)
                app.add_port("yami_i{}_mfc_rdy".format(i),      "output", 1)
                app.add_port("yami_i{}_mfc_vld".format(i),      "input",  1)
                app.add_port("yami_i{}_mfc_type".format(i),     "input",  4)
                app.add_port("yami_i{}_mfc_addr".format(i),     "input",  yami_mfc_addr_width)
                app.add_port("yami_i{}_mfc_data".format(i),     "input",  8 << yami_mfc_data_bytes_log2)

        # plan IO
        IOPlanner.autoplan(context, app)

        # create the system
        system = context.system_top = context._add_module(Module(name,
            view = ModuleView.design,
            module_class = ModuleClass.aux))

        # instantiate fabric
        nets = None
        if fabric_wrapper:
            # build fabric wrapper
            core = context._add_module(Module(fabric_wrapper,
                view = ModuleView.design, module_class = ModuleClass.aux))

            # create ports in fabric wrapper
            cls._create_ports_syscon(core, slave = True, prefix = "app_")
            cls._create_ports_rxi(core, slave = True, prefix = "rxi_", fabric = True,
                    addr_width = rxi_addr_width, data_bytes_log2 = rxi_data_bytes_log2)
            for i in range(num_yami):
                cls._create_ports_yami(core, yami, slave = True, prefix = "yami_i{}_".format(i), fabric = True)

            # instantiate fabric within fabric wrapper
            fabric = ModuleUtils.instantiate(core,
                    context.database[ModuleView.design, context.top.key], "i_fabric")

            # connect fabric pins to core ports
            for name, port in app.ports.items():
                if name == "clk":
                    NetUtils.connect(core.ports["app_clk"],   fabric.pins[(IOType.ipin, ) + port.get_io_constraint()])
                elif name == "rst_n":
                    NetUtils.connect(core.ports["app_rst_n"], fabric.pins[(IOType.ipin, ) + port.get_io_constraint()])
                elif port.direction.is_input:
                    for i, (idx, io) in enumerate(port.iter_io_constraints()):
                        if idx is None:
                            NetUtils.connect(core.ports[name],    fabric.pins[(IOType.ipin, ) + io])
                        else:
                            NetUtils.connect(core.ports[name][i], fabric.pins[(IOType.ipin, ) + io])
                else:
                    for i, (idx, io) in enumerate(port.iter_io_constraints()):
                        if idx is None:
                            NetUtils.connect(fabric.pins[(IOType.opin, ) + io], core.ports[name])
                        else:
                            NetUtils.connect(fabric.pins[(IOType.opin, ) + io], core.ports[name][i])

            # instantiate fabric wrapper in system
            core = ModuleUtils.instantiate(system, core, "i_core")
            nets = core.pins

        else:
            # instantiate fabric in system
            fabric = ModuleUtils.instantiate(system,
                    context.database[ModuleView.design, context.top.key], "i_fabric")

            # collect fabric pins
            nets = {}
            for name, port in app.ports.items():
                if name == "clk":
                    nets["app_clk"]     = fabric.pins[(IOType.ipin, ) + port.get_io_constraint()]
                elif name == "rst_n":
                    nets["app_rst_n"]   = fabric.pins[(IOType.ipin, ) + port.get_io_constraint()]
                else:
                    bits = []
                    for i, (idx, io) in enumerate(port.iter_io_constraints()):
                        if idx is None:
                            bits.append(fabric.pins[(port.direction.case(IOType.ipin, IOType.opin), ) + io])
                    nets[name] = NetUtils.concat(bits)

        # create ports in system, instantiate correspoding controller, and connect them
        # add syscon
        syscon_ports = cls._create_ports_syscon(system, slave = True)

        # add RXI instance/ports/connections
        rxi_ports = cls._create_ports_rxi(system, slave = True, prefix = "rxi_",
                addr_width = rxi_addr_width, data_bytes_log2 = rxi_data_bytes_log2)
        rxi_ctrl = ModuleUtils.instantiate(system, context.database[ModuleView.design, "prga_rxi"], "i_rxi")

        NetUtils.connect(syscon_ports["clk"],   rxi_ctrl.pins["clk"])
        NetUtils.connect(syscon_ports["rst_n"], rxi_ctrl.pins["rst_n"])

        for name, port in rxi_ports.items():
            if port.direction.is_input:
                NetUtils.connect(port, rxi_ctrl.pins["s_" + name])
            else:
                NetUtils.connect(rxi_ctrl.pins["s_" + name], port)

        NetUtils.connect(rxi_ctrl.pins["aclk"],      nets["app_clk"])
        NetUtils.connect(rxi_ctrl.pins["app_rst_n"], nets["app_rst_n"])

        for name, pin in rxi_ctrl.pins.items():
            if name.startswith("m_"):
                if pin.model.direction.is_input:
                    NetUtils.connect(nets["rxi_" + name[2:]], pin)
                else:
                    NetUtils.connect(pin, nets["rxi_" + name[2:]])

        # add YAMI instances/ports/connections
        for i in range(num_yami):
            yami_creg_ports = cls._create_ports_rxi(system, slave = True, prefix = "yami_i{}_creg_".format(i),
                    addr_width = 8, data_bytes_log2 = yami_fmc_data_bytes_log2)
            yami_ports = cls._create_ports_yami(system, yami, slave = True, prefix = "yami_i{}_".format(i))
            yami_ctrl = ModuleUtils.instantiate(system, context.database[ModuleView.design, "prga_yami"],
                    "i_yami_i{}".format(i))

            NetUtils.connect(syscon_ports["clk"],                   yami_ctrl.pins["clk"])
            NetUtils.connect(syscon_ports["rst_n"],                 yami_ctrl.pins["rst_n"])
            NetUtils.connect(rxi_ctrl.pins["aclk"],                 yami_ctrl.pins["aclk"])
            NetUtils.connect(rxi_ctrl.pins["arst_n"],               yami_ctrl.pins["arst_n"])
            NetUtils.connect(yami_ctrl.pins["err_o"],               rxi_ctrl.pins["yami_err_i"][i])
            NetUtils.connect(rxi_ctrl.pins["yami_deactivate_o"],    yami_ctrl.pins["deactivate_i"])
            NetUtils.connect(rxi_ctrl.pins["yami_activate_o"][i],   yami_ctrl.pins["activate_i"])

            for name, port in yami_creg_ports.items():
                if port.direction.is_input:
                    NetUtils.connect(port, yami_ctrl.pins["creg_" + name])
                else:
                    NetUtils.connect(yami_ctrl.pins["creg_" + name], port)

            for name, port in yami_ports.items():
                if port.direction.is_input:
                    NetUtils.connect(port, yami_ctrl.pins["s" + name])
                else:
                    NetUtils.connect(yami_ctrl.pins["s" + name], port)

            for name, pin in yami_ctrl.pins.items():
                if name.startswith("amfc") or name.startswith("afmc"):
                    if pin.model.direction.is_input:
                        NetUtils.connect(nets["yami_i{}_".format(i) + name[1:]], pin)
                    else:
                        NetUtils.connect(pin, nets["yami_i{}_".format(i) + name[1:]])