# -*- encoding: ascii -*-

from .util import AppUtils
from ..netlist import Module, ModuleUtils

__all__ = []

# ----------------------------------------------------------------------------
# -- Memory Interface/Integration Mixins -------------------------------------
# ----------------------------------------------------------------------------
class AppMemMixin(object):
    """Mixin class for memory interfacing/integration methods."""

    def get_or_create_axi4ldshim_yami(self, yami, addr_width, data_bytes_log2):
        """Get or create an AXI4-YAMI load shim.

        Args:
            yami (`FabricIntf`): YAMI interface
            addr_width (:obj:`int`): AXI4 address width
            data_bytes_log2 (:obj:`int`): Log 2 of the number of bytes of the AXI4 data bus.

        Returns:
            `Module`:
        """

        name = "prga_app_axi4ldshim_yami_a{}d{}".format(addr_width, 8 << data_bytes_log2)

        if m := self.modules.get(name):
            return m

        m = self.add_module(Module(name,
            portgroups = {},
            verilog_template = "yami/prga_app_axi4ldshim.tmpl.v"))

        m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)

        m.portgroups.setdefault("axi4r", {})[None] = AppUtils.create_axi4r_ports(m,
                addr_width, data_bytes_log2, slave = True,
                omit_ports = ("arprot", "arqos", "arcache", "arlock"))

        m.portgroups.setdefault("yami", {})[None] = AppUtils.create_yami_ports(m, yami,
                omit_ports = ("fmc_data", "fmc_parity", "mfc_type", "mfc_addr"))

        ModuleUtils.create_port(m, "cfg_addr_offset",   yami.fmc_addr_width,    "input")
        ModuleUtils.create_port(m, "cfg_nc",            1,                      "input")

        return m

    def get_or_create_axi4stshim_yami(self, yami, addr_width, data_bytes_log2):
        """Get or create an AXI4-YAMI store shim.

        Args:
            yami (`FabricIntf`): YAMI interface
            addr_width (:obj:`int`): AXI4 address width
            data_bytes_log2 (:obj:`int`): Log 2 of the number of bytes of the AXI4 data bus.

        Returns:
            `Module`:
        """

        name = "prga_app_axi4stshim_yami_a{}d{}".format(addr_width, 8 << data_bytes_log2)

        if m := self.modules.get(name):
            return m

        m = self.add_module(Module(name,
            portgroups = {},
            verilog_template = "yami/prga_app_axi4stshim.tmpl.v"))

        m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)

        m.portgroups.setdefault("axi4w", {})[None] = AppUtils.create_axi4w_ports(m,
                addr_width, data_bytes_log2, slave = True,
                omit_ports = ("awprot", "awqos", "awcache", "awlock"))

        m.portgroups.setdefault("yami", {})[None] = AppUtils.create_yami_ports(m, yami,
                omit_ports = ("fmc_parity", "mfc_type", "mfc_data", "mfc_addr"))

        ModuleUtils.create_port(m, "cfg_addr_offset",   yami.fmc_addr_width,    "input")
        ModuleUtils.create_port(m, "cfg_nc",            1,                      "input")

        return m

    def get_or_create_yami_mux(self, yami, num_srcs):
        """Get or create a YAMI mux.

        Args:
            yami (`FabricIntf`): YAMI interface
            num_srcs (:obj:`int`): Number of sources.

        Returns:
            `Module`:
        """

        name = "prga_app_yami_mux{}".format(num_srcs)

        if m := self.modules.get(name):
            return m

        m = self.add_module(Module(name,
            portgroups = {},
            num_srcs = num_srcs,
            verilog_template = "yami/prga_app_yami_mux.tmpl.v"))

        m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)

        for i in range(num_srcs):
            m.portgroups.setdefault("yami", {})[i] = AppUtils.create_yami_ports(m, yami,
                    slave = True, prefix = "src{}_".format(i),
                    omit_ports = ("fmc_parity", "mfc_addr"))

        m.portgroups.setdefault("yami", {})[None] = AppUtils.create_yami_ports(m, yami,
                slave = False, prefix = "dst_",
                omit_ports = ("fmc_parity", "mfc_addr"))

        return m
