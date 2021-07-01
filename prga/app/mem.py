# -*- encoding: ascii -*-

from .util import AppUtils
from ..netlist import Module, ModuleUtils
from ..util import uno

import os

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
                omit_ports = ("fmc_data", "fmc_l1rplway", "fmc_parity",
                    "mfc_type", "mfc_addr", "mfc_l1invall", "mfc_l1invway"))

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
                omit_ports = ("fmc_l1rplway", "fmc_parity",
                    "mfc_type", "mfc_data", "mfc_addr", "mfc_l1invall", "mfc_l1invway"))

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
                    omit_ports = ("fmc_l1rplway", "fmc_parity",
                        "mfc_addr", "mfc_l1invall", "mfc_l1invway"))

        m.portgroups.setdefault("yami", {})[None] = AppUtils.create_yami_ports(m, yami,
                slave = False, prefix = "dst_",
                omit_ports = ("fmc_l1rplway", "fmc_parity",
                        "mfc_addr", "mfc_l1invall", "mfc_l1invway"))

        return m

    def get_or_create_yami_demux(self, yami, num_dsts, *,
            demux_addr_low = None, demux_addr_high = None):
        """Get or create a YAMI demux based on address.

        Args:
            yami (`FabricIntf`): YAMI interface
            num_dsts (:obj:`int`): Number of destinations.

        Keyword Args:
            demux_addr_low (:obj:`int`): ``demux_addr_high - (num_dsts-1).bit_length()`` if not set
            demux_addr_high (:obj:`int`): ``yami.fmc_addr_width-1`` if not set

        Returns:
            `Module`:
        """

        name = "prga_app_yami_demux{}".format(num_dsts)

        if m := self.modules.get(name):
            return m

        demux_addr_high = uno(demux_addr_high, yami.fmc_addr_width - 1)
        demux_addr_low  = uno(demux_addr_low,  demux_addr_high - (num_dsts - 1).bit_length())

        m = self.add_module(Module(name,
            portgroups = {},
            num_dsts = num_dsts,
            demux_addr_low = demux_addr_low,
            demux_addr_high = demux_addr_high,
            verilog_template = "yami/prga_app_yami_demux.tmpl.v"))

        m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)
        m.portgroups.setdefault("yami", {})[None] = AppUtils.create_yami_ports(m, yami,
                slave = True, prefix = "src_",
                omit_ports = ("fmc_l1rplway", "fmc_parity",
                    "mfc_addr", "mfc_l1invall", "mfc_l1invway"))

        for i in range(num_dsts):
            m.portgroups.setdefault("yami", {})[i] = AppUtils.create_yami_ports(m, yami,
                    slave = False, prefix = "dst{}_".format(i),
                    omit_ports = ("fmc_l1rplway", "fmc_parity",
                        "mfc_addr", "mfc_l1invall", "mfc_l1invway"))

        return m

    def get_or_create_yami_pitoncache(self, yami):
        """Get or create a YAMI L1 Cache.

        Args:
            yami (`FabricIntf`):

        Returns:
            `Module`:
        """

        name = "prga_yami_pitoncache"

        if m := self.modules.get(name):
            return m

        # add search paths
        self.template_search_paths.append(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'integration', 'templates')
                )

        # add header
        self.add_verilog_header("prga_yami_pitoncache.vh",
                "yami/piton/cache_v0/include/prga_yami_pitoncache.vh")

        # add top-level cache module
        m = self.add_module(Module("prga_yami_pitoncache",
                portgroups = {},
                verilog_template = "yami/piton/cache_v0/prga_yami_pitoncache.v",
                verilog_dep_headers = ("prga_yami_pitoncache.vh", )))

        # create port groups
        m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)
        m.portgroups.setdefault("yami", {})["kernel"] = AppUtils.create_yami_ports(m, yami,
                slave = True, prefix = "a_",
                omit_ports = ("fmc_l1rplway", "fmc_parity", "mfc_addr", "mfc_l1invall", "mfc_l1invway"))
        m.portgroups.setdefault("yami", {})["memory"] = AppUtils.create_yami_ports(m, yami,
                slave = False, prefix = "m_",
                omit_ports = ("fmc_parity", ))

        # add and instantiate sub-modules
        for d in (
                "prga_yami_pitoncache_data_array",
                "prga_yami_pitoncache_lru_array",
                "prga_yami_pitoncache_state_array",
                "prga_yami_pitoncache_tag_array",
                "prga_yami_pitoncache_rob",
                "prga_yami_pitoncache_rpb",
                "prga_yami_pitoncache_way_logic",
                "prga_yami_pitoncache_pipeline_s1",
                "prga_yami_pitoncache_pipeline_s2",
                "prga_yami_pitoncache_pipeline_s3",
                ):
            sub = self.add_module(Module(d,
                verilog_template = "yami/piton/cache_v0/{}.v".format(d)))
            ModuleUtils.instantiate(m, sub, d)

        return m

    def get_or_create_pipeldshim_yami(self, yami, data_bytes_log2):
        """Get or create a valid-ready to YAMI load shim.

        Args:
            yami (`FabricIntf`): YAMI interface
            data_bytes_log2 (:obj:`int`): Log 2 of the number of bytes of the data bus.

        Returns:
            `Module`:
        """

        name = "prga_app_pipeldshim_yami_d{}".format(8 << data_bytes_log2)

        if m := self.modules.get(name):
            return m

        m = self.add_module(Module(name,
            portgroups = {},
            verilog_template = "yami/prga_app_pipeldshim.tmpl.v"))

        m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)
        m.portgroups.setdefault("vldrdy", {})[None] = AppUtils.create_vldrdy_ports(m, 
                {"data": 8 << data_bytes_log2}, prefix = "k")
        m.portgroups.setdefault("yami", {})[None] = AppUtils.create_yami_ports(m, yami,
                omit_ports = ("fmc_data", "fmc_l1rplway", "fmc_parity",
                    "mfc_type", "mfc_addr", "mfc_l1invall", "mfc_l1invway"))

        ModuleUtils.create_port(m, "cfg_addr",  yami.fmc_addr_width, "input")
        ModuleUtils.create_port(m, "cfg_len",   32,                  "input")
        ModuleUtils.create_port(m, "cfg_start", 1,                   "input")
        ModuleUtils.create_port(m, "cfg_idle",  1,                   "output")

        return m

    def get_or_create_pipestshim_yami(self, yami, data_bytes_log2):
        """Get or create a valid-ready to YAMI store shim.

        Args:
            yami (`FabricIntf`): YAMI interface
            data_bytes_log2 (:obj:`int`): Log 2 of the number of bytes of the data bus.

        Returns:
            `Module`:
        """

        name = "prga_app_pipestshim_yami_d{}".format(8 << data_bytes_log2)

        if m := self.modules.get(name):
            return m

        m = self.add_module(Module(name,
            portgroups = {},
            verilog_template = "yami/prga_app_pipestshim.tmpl.v"))

        m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)
        m.portgroups.setdefault("vldrdy", {})[None] = AppUtils.create_vldrdy_ports(m,
                {"data": 8 << data_bytes_log2}, slave = True, prefix = "k")
        m.portgroups.setdefault("yami", {})[None] = AppUtils.create_yami_ports(m, yami,
                omit_ports = ("fmc_l1rplway", "fmc_parity",
                    "mfc_type", "mfc_data", "mfc_addr", "mfc_l1invall", "mfc_l1invway"))

        ModuleUtils.create_port(m, "cfg_addr",  yami.fmc_addr_width, "input")
        ModuleUtils.create_port(m, "cfg_len",   32,                  "input")
        ModuleUtils.create_port(m, "cfg_start", 1,                   "input")
        ModuleUtils.create_port(m, "cfg_idle",  1,                   "output")

        return m

