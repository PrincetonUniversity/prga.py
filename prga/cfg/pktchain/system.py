# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .protocol import PktchainProtocol
from .lib import Pktchain
from ...core.common import Orientation, IOType, ModuleView
from ...netlist.net.common import PortDirection
from ...netlist.net.util import NetUtils
from ...netlist.module.module import Module
from ...netlist.module.util import ModuleUtils
from ...exception import PRGAAPIError
from ...util import uno

import logging
_logger = logging.getLogger(__name__)

from copy import deepcopy

__all__ = ["PktchainSystem"]

# ----------------------------------------------------------------------------
# -- Wrapping the FPGA fabric for Hybrid Integration -------------------------
# ----------------------------------------------------------------------------
class PktchainSystem(object):
    """Wrapper class for utility functions for wrapping the FPGA fabric for hybrid system integration."""

    @classmethod
    def _pop_available_io(cls, available, io_type, prev, scan_direction, fabric, force_change_tile = False):
        (x, y), subblock = prev
        if not force_change_tile:
            subblock += 1
        else:
            subblock = 0
            if scan_direction.is_north:
                y += 1
            elif scan_direction.is_south:
                y -= 1
            elif scan_direction.is_east:
                x += 1
            else:
                x -= 1
        while 0 <= x < fabric.width and 0 <= y < fabric.height:
            io = (x, y), subblock
            if io in available[io_type]:
                available[io_type].remove( io )
                available[io_type.opposite].discard( io )
                return io
            subblock = 0
            if scan_direction.is_north:
                y += 1
            elif scan_direction.is_south:
                y -= 1
            elif scan_direction.is_east:
                x += 1
            else:
                x -= 1
        raise PRGAAPIError("Ran out of IOs")

    @classmethod
    def iobind_user_axilite(cls, context, start_pos = None, scan_direction = Orientation.north, start_subbblock = 0,
            *, addr_width = None, data_bytes = None, leftovers = False):
        """Bind AXI4Lite user interface pins to the fabric.

        Args:
            context (`Context`):
            start_pos (:obj:`tuple` [:obj:`int`, :obj:`int`]): Starting position
            scan_direction (`Orientation`): Search for IO blocks in the given orientation
            start_subbblock (:obj:`int`): Starting subblock

        Keyword Args:
            addr_width (:obj:`int`): Address port width
            data_bytes (:obj:`int`): Number of bytes in data ports
            leftovers (:obj:`bool`): If set, unassigned GPIOs are returned as well

        Returns:
            :obj:`Mapping` [:obj:`str`, :obj:`Sequence` [:obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int`]]]: Mapping
            from AXI4-Lite standard port names to list of positions for each pin of that port.
        """
        addr_width = uno(addr_width, PktchainProtocol.AXILiteController.ADDR_WIDTH)
        data_bytes = uno(data_bytes, 2 ** (PktchainProtocol.AXILiteController.DATA_WIDTH_LOG2 - 3))
        assignments = {}
        # 1. get all IOs
        available = {IOType.ipin: set(), IOType.opin: set()}
        for iotype, (x, y), subblock in context.summary.ios:
            available[iotype].add( ((x, y), subblock) )
        # 2. bind clk
        for g in itervalues(context.globals):
            if g.is_clock:
                assignments["ACLK"] = [(IOType.ipin, g.bound_to_position, g.bound_to_subblock, )]
                available[IOType.ipin].discard( (g.bound_to_position, g.bound_to_subblock) )
                available[IOType.opin].discard( (g.bound_to_position, g.bound_to_subblock) )
                if start_pos is None:
                    _, start_pos, start_subbblock = assignments["ACLK"][0]
                break
        if "ACLK" not in assignments:
            raise PRGAAPIError("No clock found in the fabric")
        # 3. bind reset signal
        io = start_pos, start_subbblock
        if io not in available[IOType.ipin]:
            io = cls._pop_available_io(available, IOType.ipin, io, scan_direction, context.top)
        assignments["ARESETn"] = [(IOType.ipin, ) + io]
        # 3. bind other ports
        # shortcut
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
                for i in range(w):
                    io = cls._pop_available_io(available, t, io, scan_direction, context.top, first)
                    _logger.debug("Assigning {}[{}] to ({}, {}, {})".format(p, i, *io[0], io[1]))
                    first = False
                    assignments.setdefault(p, []).append( (t, ) + io )
        if leftovers:
            l = []
            for t, s in iteritems(available):
                for io in s:
                    l.append( (t, ) + io )
            return assignments, l
        else:
            return assignments

    @classmethod
    def build_system_axilite(cls, context, expose_gpio = False,
            *, name = "system", io_start_pos = None, io_start_subblock = 0, io_scan_direction = Orientation.north):
        """Create the system top wrapping the reconfigurable fabric. Assign and connect user pins.

        Args:
            context (`Context`):
            expose_gpio (:obj:`bool`): If set to True, pins of the fabric that are not used in the user AXI4-Lite
                interface are exposed at the top level

        Keyword Args:
            name (:obj:`str`): Name of the system top module
        """
        if expose_gpio:
            raise NotImplementedError
        system = context.system_top = Module(name, view = ModuleView.logical)
        # create ports
        clk = ModuleUtils.create_port(system, "clk", 1, PortDirection.input_, is_clock = True)
        rst = ModuleUtils.create_port(system, "rst", 1, PortDirection.input_)
        slave = Pktchain._create_axilite_intf(system, "m",
                PktchainProtocol.AXILiteController.ADDR_WIDTH,
                2 ** (PktchainProtocol.AXILiteController.DATA_WIDTH_LOG2 - 3))
        # create instances
        fabric = ModuleUtils.instantiate(system, context.database[ModuleView.logical, context.top.key], "i_fabric")
        intf = ModuleUtils.instantiate(system, context.database[ModuleView.logical, "pktchain_axilite_intf"],
                "i_intf")
        # assign IO pins
        assignments, gpio = cls.iobind_user_axilite(context, io_start_pos, io_scan_direction, io_start_subblock,
                leftovers = True)
        summary = context.summary.pktchain.setdefault("intf", {})
        summary["type"] = "axilite"
        summary["iobind"] = assignments
        # connect stuff
        NetUtils.connect(clk, intf.pins["clk"])
        NetUtils.connect(rst, intf.pins["rst"])
        # master axilite
        for name, port in iteritems(slave):
            if port.direction.is_input:
                NetUtils.connect(port, intf.pins[port.key])
            else:
                NetUtils.connect(intf.pins[port.key], port)
        # configuration intf
        NetUtils.connect(intf.pins["cfg_rst"],          fabric.pins["cfg_rst"])
        NetUtils.connect(intf.pins["cfg_e"],            fabric.pins["cfg_e"])
        NetUtils.connect(fabric.pins["phit_i_full"],    intf.pins["cfg_phit_o_full"])
        NetUtils.connect(intf.pins["cfg_phit_o_wr"],    fabric.pins["phit_i_wr"])
        NetUtils.connect(intf.pins["cfg_phit_o"],       fabric.pins["phit_i"])
        NetUtils.connect(intf.pins["cfg_phit_i_full"],  fabric.pins["phit_o_full"])
        NetUtils.connect(fabric.pins["phit_o_wr"],      intf.pins["cfg_phit_i_wr"])
        NetUtils.connect(fabric.pins["phit_o"],         intf.pins["cfg_phit_i"])
        # user axilite
        for p, ios in iteritems(assignments):
            if p == "ACLK":
                NetUtils.connect(intf.pins["uclk"],     fabric.pins[ios[0]])
            elif p == "ARESETn":
                NetUtils.connect(intf.pins["urst_n"],     fabric.pins[ios[0]])
            else:
                ip = intf.pins["u_" + p]
                if ip.model.direction.is_input:
                    for i, io in enumerate(ios):
                        NetUtils.connect(fabric.pins[io], ip[i])
                else:
                    for i, io in enumerate(ios):
                        NetUtils.connect(ip[i], fabric.pins[io])

    @classmethod
    def generate_axilite_io_assignment_constraint(cls, context, renderer, f, *,
            addr_width = 8, data_bytes = 4):
        """Add a rendering task for the IO assignment constraint file.

        Args:
            context (`Context`):
            renderer (`FileRenderer`):
            f (:obj:`str` or File-like Object):

        Keyword Args:
            addr_width (:obj:`int`):
            data_bytes (:obj:`int`):
        """
        try:
            if context.summary.pktchain["intf"]["type"] != "axilite":
                raise PRGAAPIError("The fabric does not support AXILite interface")
        except KeyError:
            raise PRGAAPIError("No interface has been added to the fabric yet")
        assignments = deepcopy(context.summary.pktchain["intf"]["iobind"])
        if addr_width <= 0 or addr_width > len(assignments["AWADDR"]):
            raise PRGAAPIError("Invalid address width. Valid range: (0, {}]".format(len(assignments["AWADDR"])))
        if data_bytes <= 0 or data_bytes > len(assignments["WSTRB"]):
            raise PRGAAPIError("Invalid data width (in bytes). Valid range: (0, {}]".format(len(assignments["WSTRB"])))
        assignments["AWADDR"] = assignments["AWADDR"][0:addr_width]
        assignments["ARADDR"] = assignments["ARADDR"][0:addr_width]
        assignments["WSTRB"] = assignments["WSTRB"][0:data_bytes]
        assignments["WDATA"] = assignments["WDATA"][0:data_bytes * 8]
        assignments["RDATA"] = assignments["RDATA"][0:data_bytes * 8]
        renderer.add_generic(f, "io.tmpl.pads", assignments = assignments)
