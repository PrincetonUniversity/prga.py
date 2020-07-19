# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .common import InterfaceClass
from ..core.common import ModuleView, ModuleClass, IOType
from ..netlist.module.module import Module
from ..netlist.module.util import ModuleUtils
from ..netlist.net.common import PortDirection
from ..netlist.net.util import NetUtils
from ..exception import PRGAAPIError, PRGAInternalError
from ..tools.ioplan.ioplan import IOConstraints, IOPlanner
from ..util import uno

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
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "clk": ModuleUtils.create_port(module, prefix + "clk", 1, o, is_clock = True),
                prefix + "rst_n": ModuleUtils.create_port(module, prefix + "rst_n", 1, o)}

    @classmethod
    def _create_intf_reg(cls, module, slave = False, prefix = ""):
        """Create register-based interface. By default this creates the master interface that sends register access
        requests and receives responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "req_rdy": ModuleUtils.create_port(module, prefix + "req_rdy", 1, i),
                prefix + "req_val": ModuleUtils.create_port(module, prefix + "req_val", 1, o),
                prefix + "req_addr": ModuleUtils.create_port(module, prefix + "req_addr", 12, o),
                prefix + "req_strb": ModuleUtils.create_port(module, prefix + "req_strb", 8, o),
                prefix + "req_data": ModuleUtils.create_port(module, prefix + "req_data", 64, o),
                prefix + "resp_rdy": ModuleUtils.create_port(module, prefix + "resp_rdy", 1, o),
                prefix + "resp_val": ModuleUtils.create_port(module, prefix + "resp_val", 1, i),
                prefix + "resp_err": ModuleUtils.create_port(module, prefix + "resp_err", 1, i),
                prefix + "resp_data": ModuleUtils.create_port(module, prefix + "resp_data", 64, i),
                }

    @classmethod
    def _create_intf_ureg(cls, module, slave = False, prefix = ""):
        """Create user-defined register-based interface. By default this creates the master interface that sends
        register access requests and receives responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "req_rdy": ModuleUtils.create_port(module, prefix + "req_rdy", 1, i),
                prefix + "req_val": ModuleUtils.create_port(module, prefix + "req_val", 1, o),
                prefix + "req_addr": ModuleUtils.create_port(module, prefix + "req_addr", 12, o),
                prefix + "req_strb": ModuleUtils.create_port(module, prefix + "req_strb", 8, o),
                prefix + "req_data": ModuleUtils.create_port(module, prefix + "req_data", 64, o),
                prefix + "resp_rdy": ModuleUtils.create_port(module, prefix + "resp_rdy", 1, o),
                prefix + "resp_val": ModuleUtils.create_port(module, prefix + "resp_val", 1, i),
                prefix + "resp_ecc": ModuleUtils.create_port(module, prefix + "resp_ecc", 1, i),
                prefix + "resp_data": ModuleUtils.create_port(module, prefix + "resp_data", 64, i),
                }

    @classmethod
    def _create_intf_cfg(cls, module, slave = False, prefix = ""):
        """Create generic configuration interface. By default this creates the master interface that outputs
        configuration data.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "rst_n": ModuleUtils.create_port(module, prefix + "rst_n", 1, o),
                prefix + "status": ModuleUtils.create_port(module, prefix + "status", 1, i),
                prefix + "req_rdy": ModuleUtils.create_port(module, prefix + "req_rdy", 1, i),
                prefix + "req_val": ModuleUtils.create_port(module, prefix + "req_val", 1, o),
                prefix + "req_addr": ModuleUtils.create_port(module, prefix + "req_addr", 12, o),
                prefix + "req_strb": ModuleUtils.create_port(module, prefix + "req_strb", 8, o),
                prefix + "req_data": ModuleUtils.create_port(module, prefix + "req_data", 64, o),
                prefix + "resp_rdy": ModuleUtils.create_port(module, prefix + "resp_rdy", 1, o),
                prefix + "resp_val": ModuleUtils.create_port(module, prefix + "resp_val", 1, i),
                prefix + "resp_err": ModuleUtils.create_port(module, prefix + "resp_err", 1, i),
                prefix + "resp_data": ModuleUtils.create_port(module, prefix + "resp_data", 64, i),
                }

    @classmethod
    def _create_intf_sax(cls, module, slave = False, prefix = ""):
        """Create System-Application Crossbar interface. By default this creates the master interface that sends SAX
        packets and receives ASX packets.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "sax_rdy": ModuleUtils.create_port(module, prefix + "sax_rdy", 1, i),
                prefix + "sax_val": ModuleUtils.create_port(module, prefix + "sax_val", 1, o),
                prefix + "sax_data": ModuleUtils.create_port(module, prefix + "sax_data", 144, o),
                prefix + "asx_rdy": ModuleUtils.create_port(module, prefix + "asx_rdy", 1, o),
                prefix + "asx_val": ModuleUtils.create_port(module, prefix + "asx_val", 1, i),
                prefix + "asx_data": ModuleUtils.create_port(module, prefix + "asx_data", 128, i),
                }

    @classmethod
    def _create_intf_ccm(cls, module, slave = False, prefix = ""):
        """Create generic cache-coherent memory interface. By default this creates the master interface that sends
        requests and recieve responses.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, slave interface is added to ``module``
            prefix (:obj:`str`): Prefix of the port names
        """
        i, o = ((PortDirection.output, PortDirection.input_) if slave else
                (PortDirection.input_, PortDirection.output))
        return {prefix + "req_rdy": ModuleUtils.create_port(module, prefix + "req_rdy", 1, i),
                prefix + "req_val": ModuleUtils.create_port(module, prefix + "req_val", 1, o),
                prefix + "req_type": ModuleUtils.create_port(module, prefix + "req_type", 2, o),
                prefix + "req_addr": ModuleUtils.create_port(module, prefix + "req_addr", 40, o),
                prefix + "req_data": ModuleUtils.create_port(module, prefix + "req_data", 64, o),
                prefix + "req_size": ModuleUtils.create_port(module, prefix + "req_size", 3, o),
                prefix + "req_ecc": ModuleUtils.create_port(module, prefix + "req_ecc", 1, o),
                prefix + "resp_rdy": ModuleUtils.create_port(module, prefix + "resp_rdy", 1, o),
                prefix + "resp_val": ModuleUtils.create_port(module, prefix + "resp_val", 1, i),
                prefix + "resp_type": ModuleUtils.create_port(module, prefix + "resp_type", 2, i),
                prefix + "resp_addr": ModuleUtils.create_port(module, prefix + "resp_addr", 7, i),
                prefix + "resp_data": ModuleUtils.create_port(module, prefix + "resp_data", 128, i),
                }

    @classmethod
    def _register_lib(cls, context):
        """Register integration-related modules in to the module database.

        Args:
            context (`Context`):
        """
        # 1. add prga_system header
        context._add_verilog_header("prga_system.vh", "include/prga_system.tmpl.vh")

        # 2. register modules
        # 2.1 modules that we don't need to know about their ports
        for d in ("prga_ctrl", "prga_ecc_parity", "prga_mprot", "prga_sax", "prga_uprot"):
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
                context.database[ModuleView.logical, "prga_fifo"], "i_tokenq")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_ctrl"],
                context.database[ModuleView.logical, "prga_fifo"], "i_ctrldataq")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_mprot"],
                context.database[ModuleView.logical, "prga_ecc_parity"], "i_ecc_checker")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_sax"],
                context.database[ModuleView.logical, "prga_async_fifo"], "i_sax_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_sax"],
                context.database[ModuleView.logical, "prga_async_fifo"], "i_asx_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_uprot"],
                context.database[ModuleView.logical, "prga_ecc_parity"], "i_ecc_checker")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_fifo"], "axi_waddr_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_fifo"], "axi_wdata_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_fifo"], "axi_raddr_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_tokenfifo"], "axi_wresp_fifo")
        ModuleUtils.instantiate(context.database[ModuleView.logical, "prga_fe_axi4lite"],
                context.database[ModuleView.logical, "prga_fifo"], "axi_rresp_fifo")

        # 2.2 modules that we do need to know about their ports
        sysintf = context._database[ModuleView.logical, "prga_sysintf"] = Module("prga_sysintf",
                view = ModuleView.logical,
                module_class = ModuleClass.aux,
                verilog_template = "prga_sysintf.tmpl.v")
        cls._create_intf_syscon(sysintf, True)
        cls._create_intf_syscon(sysintf, False, "a")
        cls._create_intf_reg(sysintf, True, "reg_")
        cls._create_intf_ureg(sysintf, False, "ureg_")
        cls._create_intf_cfg(sysintf, False, "cfg_")
        cls._create_intf_sax(sysintf, True)
        cls._create_intf_ccm(sysintf, True, "ccm_")
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_ctrl"], "i_ctrl")
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_sax"], "i_sax")
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_uprot"], "i_uprot")
        ModuleUtils.instantiate(sysintf, context.database[ModuleView.logical, "prga_mprot"], "i_mprot")

    @classmethod
    def ioplan_syscon(cls, context, 
            start_pos = None, subtile = None, counterclockwise = None, planner = None):
        """Constrain IOs for cache-coherent memory interface.

        Args:
            context (`Context`):

        Keyword Args:
            start_pos (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Starting position for IO scanning
            subtile (:obj:`int`): Starting subtile for IO scanning
            counterclockwise (:obj:`bool`): If set to True, scan IO in counter-clockwise direction
            planner (`IOPlanner`): The IO planner used for planning IO. If not specified, a new IO planner is used

        Returns:
            :obj:`Mapping` [:obj:`str`, `IOConstraints` ]): Mapping from port names to IOs
        """

        # get the summary
        if (interfaces := getattr(context.summary, "intf", None)) is None:
            interfaces = context.summary.intf = {}

        # get or create constraints entry
        interface = interfaces.setdefault(InterfaceClass.syscon, {})
        if (constraints := interface.get("constraints", None)) is not None:
            return constraints
        else:
            constraints = interface["constraints"] = {}

        # create IOPlanner
        if planner is None:
            planner = IOPlanner(context, uno(start_pos, (0, 0)), uno(subtile, 0), uno(counterclockwise, False))
        else:
            planner.reset_scanning(start_pos, subtile, counterclockwise)

        # find and constrain clock
        for g in itervalues(context.globals_):
            if g.is_clock:
                ios = constraints["clk"] = IOConstraints(IOType.ipin)
                planner.use(IOType.ipin, g.bound_to_position, g.bound_to_subtile)
                ios[0] = g.bound_to_position, g.bound_to_subtile
        if "clk" not in constraints:
            raise PRGAAPIError("No clock found in the fabric")

        # constrain reset
        ios = constraints["rst_n"] = IOConstraints(IOType.ipin)
        ios[0] = planner.pop(IOType.ipin)
        return constraints

    @classmethod
    def ioplan_ccm(cls, context, *,
            start_pos = None, subtile = None, counterclockwise = None, planner = None):
        """Constrain IOs for cache-coherent memory interface.

        Args:
            context (`Context`):

        Keyword Args:
            start_pos (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Starting position for IO scanning
            subtile (:obj:`int`): Starting subtile for IO scanning
            counterclockwise (:obj:`bool`): If set to True, scan IO in counter-clockwise direction
            planner (`IOPlanner`): The IO planner used for planning IO. If not specified, a new IO planner is used

        Returns:
            :obj:`Mapping` [:obj:`str`, `IOConstraints` ]): Mapping from port names to IOs
        """

        # get or create constraints entry
        if (interfaces := getattr(context.summary, "intf", None)) is None:
            interfaces = context.summary.intf = {}
        interface = interfaces.setdefault(InterfaceClass.ccm, {})
        if (constraints := interface.get("constraints", None)) is not None:
            return constraints
        else:
            constraints = interface["constraints"] = {}

        # create IOPlanner
        if planner is None:
            planner = IOPlanner(context, uno(start_pos, (0, 0)), uno(subtile, 0), uno(counterclockwise, False))
        else:
            planner.reset_scanning(start_pos, subtile, counterclockwise)

        # constrain clock/reset
        cls.ioplan_syscon(context, planner = planner)

        # generate constraints
        for channel in (
                # Request
                {   "ccm_req_rdy":      (IOType.ipin, 1),
                    "ccm_req_val":      (IOType.opin, 1),
                    "ccm_req_type":     (IOType.opin, 2),
                    "ccm_req_size":     (IOType.opin, 3),
                    "ccm_req_ecc":      (IOType.opin, 1), },
                {   "ccm_req_addr":     (IOType.opin, 40), },
                {   "ccm_req_data":     (IOType.opin, 64), },
                # Response
                {   "ccm_resp_rdy":     (IOType.opin, 1),
                    "ccm_resp_val":     (IOType.ipin, 1),
                    "ccm_resp_type":    (IOType.ipin, 2),
                    "ccm_resp_addr":    (IOType.ipin, 7), },
                {   "ccm_resp_data":    (IOType.ipin, 128), },
                ):
            first = True
            for p, (t, w) in iteritems(channel):
                ios = constraints[p] = IOConstraints(t, 0, w)
                for i in range(w):
                    ios[i] = planner.pop(t, force_change_tile = first)
                    first = False
        return constraints

    @classmethod
    def ioplan_ureg(cls, context, data_bytes = 8, addr_width = 12, *,
            start_pos = None, subtile = None, counterclockwise = None, planner = None):
        """Constrain IOs for register-based interface.

        Args:
            context (`Context`):
            data_bytes (:obj:`int`): Number of bytes of the data bus. Supported values are: 1, 2, 4, 8
            addr_width (:obj:`int`): Width of the address bus. Supported values are: \(0, 12]

        Keyword Args:
            start_pos (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Starting position for IO scanning
            subtile (:obj:`int`): Starting subtile for IO scanning
            counterclockwise (:obj:`bool`): If set to True, scan IO in counter-clockwise direction
            planner (`IOPlanner`): The IO planner used for planning IO. If not specified, a new IO planner is used

        Returns:
            :obj:`Mapping` [:obj:`str`, `IOConstraints` ]): Mapping from port names to IOs
        """

        # validate arguments
        if data_bytes not in (1, 2, 4, 8):
            raise PRGAAPIError("Invalid data_bytes: {}".format(data_bytes))
        elif not 0 < addr_width <= 12:
            raise PRGAAPIError("Invalid addr_width: {}".format(data_bytes))

        # get or create constraints entry
        if (interfaces := getattr(context.summary, "intf", None)) is None:
            interfaces = context.summary.intf = {}
        interface = interfaces.setdefault(InterfaceClass.ureg, {})
        if (interface.setdefault("data_bytes", data_bytes) != data_bytes or
                interface.setdefault("addr_width", addr_width) != addr_width):
            raise PRGAAPIError("Existing register-based interface is configured (data_bytes: {}, addr_width: {})"
                    .format(data_bytes, addr_width))
        if (constraints := interface.get("constraints", None)) is not None:
            return constraints
        else:
            constraints = interface["constraints"] = {}

        # create IOPlanner
        if planner is None:
            planner = IOPlanner(context, uno(start_pos, (0, 0)), uno(subtile, 0), uno(counterclockwise, False))
        else:
            planner.reset_scanning(start_pos, subtile, counterclockwise)

        # constrain clock/reset
        cls.ioplan_syscon(context, planner = planner)

        # other ports
        for channel in (
                # Request
                {   "ureg_req_rdy":     (IOType.opin, 1),
                    "ureg_req_val":     (IOType.ipin, 1),
                    "ureg_req_strb":    (IOType.ipin, data_bytes), },
                {   "ureg_req_addr":    (IOType.ipin, addr_width), },
                {   "ureg_req_data":    (IOType.ipin, data_bytes * 8), },
                # Response
                {   "ureg_resp_rdy":    (IOType.ipin, 1),
                    "ureg_resp_val":    (IOType.opin, 1),
                    "ureg_resp_ecc":    (IOType.opin, 1), },
                {   "ureg_resp_data":   (IOType.opin, data_bytes * 8), },
                ):
            first = True
            for p, (t, w) in iteritems(channel):
                ios = constraints[p] = IOConstraints(t, 0, w)
                for i in range(w):
                    ios[i] = planner.pop(t, force_change_tile = first)
                    first = False
        return constraints

    @classmethod
    def ioplan_axi4lite(cls, context, data_bytes = 8, addr_width = 12, *,
            start_pos = None, subtile = None, counterclockwise = None, planner = None):
        """Constrain IOs for AXI4Lite interface.

        Args:
            context (`Context`):
            data_bytes (:obj:`int`): Number of bytes of the AXI4Lite interface. Supported values are: 1, 2, 4, 8
            addr_width (:obj:`int`): Width of the address buses of the AXI4Lite interface. Supported values are: \(0,
                12]

        Keyword Args:
            start_pos (:obj:`tuple` [:obj:`int`, :obj:`int` ]): Starting position for IO scanning
            subtile (:obj:`int`): Starting subtile for IO scanning
            counterclockwise (:obj:`bool`): If set to True, scan IO in counter-clockwise direction
            planner (`IOPlanner`): The IO planner used for planning IO. If not specified, a new IO planner is used

        Returns:
            :obj:`Mapping` [:obj:`str`, `IOConstraints` ]): Mapping from port names to IOs
        """

        # validate arguments
        if data_bytes not in (1, 2, 4, 8):
            raise PRGAAPIError("Invalid data_bytes: {}".format(data_bytes))
        elif not 0 < addr_width <= 12:
            raise PRGAAPIError("Invalid addr_width: {}".format(data_bytes))

        # get or create constraints entry
        if (interfaces := getattr(context.summary, "intf", None)) is None:
            interfaces = context.summary.intf = {}
        interface = interfaces.setdefault(InterfaceClass.axi4lite, {})
        if (interface.setdefault("data_bytes", data_bytes) != data_bytes or
                interface.setdefault("addr_width", addr_width) != addr_width):
            raise PRGAAPIError("Existing AXI4Lite interface is configured (data_bytes: {}, addr_width: {})"
                    .format(data_bytes, addr_width))
        if (constraints := interface.get("constraints", None)) is not None:
            return constraints
        else:
            constraints = interface["constraints"] = {}

        # create IOPlanner
        if planner is None:
            planner = IOPlanner(context, uno(start_pos, (0, 0)), uno(subtile, 0), uno(counterclockwise, False))
        else:
            planner.reset_scanning(start_pos, subtile, counterclockwise)

        # constrain clock/reset
        cls.ioplan_syscon(context, planner = planner)

        # other ports
        ti, to = IOType.ipin, IOType.opin
        for channel in (
                {"AWREADY": (to, 1), "AWVALID": (ti, 1), "AWPROT": (ti, 3), "AWADDR": (ti, addr_width), },
                {"WREADY": (to, 1), "WVALID": (ti, 1), "WSTRB": (ti, data_bytes), "WDATA": (ti, data_bytes * 8), },
                {"BVALID": (to, 1), "BRESP": (to, 2), "BREADY": (ti, 1), },
                {"ARREADY": (to, 1), "ARVALID": (ti, 1), "ARPROT": (ti, 3), "ARADDR": (ti, addr_width), },
                {"RVALID": (to, 1), "RRESP": (to, 2), "RDATA": (to, data_bytes * 8), "RREADY": (ti, 1), },
                ):
            first = True
            for p, (t, w) in iteritems(channel):
                ios = constraints[p] = IOConstraints(t, 0, w)
                for i in range(w):
                    ios[i] = planner.pop(t, force_change_tile = first)
                    first = False
        return constraints

    @classmethod
    def build_system(cls, context, interfaces = (InterfaceClass.ccm, InterfaceClass.ureg), *, name = "prga_system"):
        """Create the system top wrapping the reconfigurable fabric.

        Args:
            context (`Context`):
            interfaces (:obj:`Sequence` [`InterfaceClass` ]): Interfaces added

        Keyword Args:
            name (:obj:`str`): Name of the system top module
        """

        system = context.system_top = Module(name, view = ModuleView.logical, module_class = ModuleClass.aux)
        if set(iter(interfaces)) != {InterfaceClass.ccm, InterfaceClass.ureg}:
            raise NotImplementedError("The only implemented interface is (ccm, ureg) at the moment")

        # create ports
        cls._create_intf_syscon(system, True)
        cls._create_intf_reg(system, True, "reg_")
        cls._create_intf_sax(system, True)

        # create instances
        fabric = ModuleUtils.instantiate(system, context.database[ModuleView.logical, context.top.key], "i_fabric")
        sysintf = ModuleUtils.instantiate(system, context.database[ModuleView.logical, "prga_sysintf"], "i_sysintf")

        # get or create IO constraints
        planner = IOPlanner(context)
        constraints = dict(
                **cls.ioplan_syscon(context, planner = planner),
                **cls.ioplan_ureg(context, planner = planner),
                **cls.ioplan_ccm(context, planner = planner))

        # connect stuff
        for port_name, port in iteritems(system.ports):
            if port.direction.is_input:
                NetUtils.connect(port, sysintf.pins[port_name])
            else:
                NetUtils.connect(sysintf.pins[port_name], port)
        NetUtils.connect(sysintf.pins["aclk"], fabric.pins[(IOType.ipin, ) + constraints["clk"][0]])
        NetUtils.connect(sysintf.pins["arst_n"], fabric.pins[(IOType.ipin, ) + constraints["rst_n"][0]])
        for name, ios in iteritems(constraints):
            if name in ("clk", "rst_n"):
                continue
            elif ios.type_.is_ipin:
                for i, key in enumerate(ios, ios.low):
                    NetUtils.connect(sysintf.pins[name][i], fabric.pins[(IOType.ipin, ) + key])
            else:
                for i, key in enumerate(ios, ios.low):
                    NetUtils.connect(fabric.pins[(IOType.opin, ) + key], sysintf.pins[name][i])