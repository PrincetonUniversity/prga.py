# -*- encoding: ascii -*-

from ..netlist import Module, ModuleUtils, NetUtils

__all__ = []

# ----------------------------------------------------------------------------
# -- Common Utilities --------------------------------------------------------
# ----------------------------------------------------------------------------
class AppUtils(object):
    """A host class for application wrapping utility functions."""

    @classmethod
    def create_syscon_ports(cls, module, slave = False, *,
            prefix = '', suffix = '', uppercase = False,
            omit_ports = tuple()):
        """Create system control ports in ``module``.

        Args:
            module (`Module`):
            slave (:obj:`bool`): If set, create slave interface

        Keyword Args:
            prefix (:obj:`str`): Prefix to be added before the standard port names, e.g. "{prefix}clk"
            suffix (:obj:`str`): Suffix to be added after the standard port names, e.g. "clk{suffix}"
            uppercase (:obj:`bool`): If set, port names are converted to uppercase. Does not affect ``prefix`` or
                ``suffix``.
            omit_ports (:obj:`Container` [:obj:`str` ]): Exclude the specified ports from creation. Ports are named by
                standard port names only, case-insensitive.

        Returns:
            :obj:`dict` [:obj:`str`, `Port` ]: Mapping from standard port names (lowercase) to ports

        The following ports are created: clk, rst_n
        """

        # omit ports
        omit_ports = set( s.lower() for s in omit_ports )

        # return value
        d = {}

        # short aliases
        def mi(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "output" if slave else "input",
                        **kwargs)

        def mo(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "input" if slave else "output",
                        **kwargs)

        # create ports
        mo("clk",   1, is_clock = True)
        mo("rst_n", 1)

        return d

    @classmethod
    def create_axi4r_ports(cls, module, addr_width, data_bytes_log2, slave = False, *,
            prefix = '', suffix = '', uppercase = False,
            aruser_width = 0, ruser_width = 0, region_width = 0, id_width = 0,
            omit_ports = tuple()):
        """Create AXI4 AR & R channel ports in ``module``.

        Args:
            module (`Module`):
            addr_width (:obj:`int`): Address width
            data_bytes_log2 (:obj:`int`): Log 2 of the number of bytes in the data bus
            slave (:obj:`bool`): If set, create slave interface

        Keyword Args:
            prefix (:obj:`str`): Prefix to be added before the standard port names, e.g. "{prefix}arready"
            suffix (:obj:`str`): Suffix to be added after the standard port names, e.g. "arready{suffix}"
            uppercase (:obj:`bool`): If set, AXI4 port names are converted to uppercase. Does not affect ``prefix`` or
                ``suffix``.
            aruser_width (:obj:`int`): If set, ``ARUSER`` port is added with the specified bit width
            ruser_width (:obj:`int`): If set, ``RUSER`` port is added with the specified bit width
            region_width (:obj:`int`): If set, ``ARREGION` port is added with the specified bit width
            id_width (:obj:`int`): If set, ``ARID`` and ``RID`` ports are added with the spcified bit width
            omit_ports (:obj:`Container` [:obj:`str` ]): Exclude the specified ports from creation. Ports are named by
                standard port names only, case-insensitive. This argument takes precedence over ``aruser_width`` etc.

        Returns:
            :obj:`dict` [:obj:`str`, `Port` ]: Mapping from standard port names (lowercase) to ports

        The following ports are created: arready, arvalid, arprot, arqos, arburst, arsize, arlen, araddr, arcache, arlock,
        rready, rvalid, rlast, rresp, rdata. Optionally: aruser, arregion, arid, ruser, rid
        """

        # omit ports
        omit_ports = set( s.lower() for s in omit_ports )

        # return value
        d = {}

        # short aliases
        def mi(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "output" if slave else "input",
                        **kwargs)

        def mo(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "input" if slave else "output",
                        **kwargs)

        # AR channel
        mi("arready", 1)
        mo("arvalid", 1)
        mo("arprot",  3)
        mo("arqos",   4)
        mo("arburst", 2)
        mo("arsize",  3)
        mo("arlen",   8)
        mo("araddr",  addr_width)
        mo("arcache", 4)
        mo("arlock",  1)
        if aruser_width > 0: mo("aruser",   aruser_width)
        if region_width > 0: mo("arregion", region_width) 
        if id_width > 0:     mo("arid",     id_width)

        # R channel
        mo("rready",  1)
        mi("rvalid",  1)
        mi("rresp",   2)
        mi("rdata",   8 << data_bytes_log2)
        mi("rlast",   1)
        if ruser_width > 0:  mi("ruser",    ruser_width)
        if id_width > 0:     mi("rid",      id_width)

        return d

    @classmethod
    def create_axi4w_ports(cls, module, addr_width, data_bytes_log2, slave = False, *,
            prefix = '', suffix = '', uppercase = False,
            awuser_width = 0, wuser_width = 0, buser_width = 0, region_width = 0, id_width = 0,
            omit_ports = tuple()):
        """Create AXI4 AW, W & B channel ports in ``module``.

        Args:
            module (`Module`):
            addr_width (:obj:`int`): Address width
            data_bytes_log2 (:obj:`int`): Log 2 of the number of bytes in the data bus
            slave (:obj:`bool`): If set, create slave interface

        Keyword Args:
            prefix (:obj:`str`): Prefix to be added before the standard port names, e.g. "{prefix}awready"
            suffix (:obj:`str`): Suffix to be added after the standard port names, e.g. "awready{suffix}"
            uppercase (:obj:`bool`): If set, AXI4 port names are converted to uppercase. Does not affect ``prefix`` or
                ``suffix``.
            awuser_width (:obj:`int`): If set, ``AWUSER`` port is added with the specified bit width
            wuser_width (:obj:`int`): If set, ``WUSER`` port is added with the specified bit width
            region_width (:obj:`int`): If set, ``AWREGION` port is added with the specified bit width
            id_width (:obj:`int`): If set, ``AWID``, ``WID`` and ``BID`` ports are added with the spcified bit width
            omit_ports (:obj:`Container` [:obj:`str` ]): Exclude the specified ports from creation. Ports are named by
                standard port names only, case-insensitive. This argument takes precedence over ``awuser_width`` etc.

        Returns:
            :obj:`dict` [:obj:`str`, `Port` ]: Mapping from standard port names (lowercase) to ports

        The following ports are created: awready, awvalid, awprot, awqos, awburst, awsize, awlen, awaddr, awcache, awlock,
        wready, wvalid, wlast, wstrb, wdata, bvalid, bready, bresp. Optionally: awuser, awregion, awid, wuser, wid,
        buser, bid
        """

        # omit ports
        omit_ports = set( s.lower() for s in omit_ports )

        # return value
        d = {}

        # short aliases
        def mi(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "output" if slave else "input",
                        **kwargs)

        def mo(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "input" if slave else "output",
                        **kwargs)

        # AW channel
        mi("awready", 1)
        mo("awvalid", 1)
        mo("awprot",  3)
        mo("awqos",   4)
        mo("awburst", 2)
        mo("awsize",  3)
        mo("awlen",   8)
        mo("awaddr",  addr_width)
        mo("awcache", 4)
        mo("awlock",  1)
        if awuser_width > 0: mo("awuser",   awuser_width)
        if region_width > 0: mo("awregion", region_width) 
        if id_width > 0:     mo("awid",     id_width)

        # W channel
        mi("wready",  1)
        mo("wvalid",  1)
        mo("wlast",   1)
        mo("wstrb",   1 << data_bytes_log2)
        mo("wdata",   8 << data_bytes_log2)
        if wuser_width > 0:  mo("wuser",    wuser_width)
        if id_width > 0:     mo("wid",      id_width)

        # B channel
        mo("bready",  1)
        mi("bvalid",  1)
        mi("bresp",   2)
        if buser_width > 0:  mi("buser",    buser_width)
        if id_width > 0:     mi("bid",      id_width)

        return d

    @classmethod
    def create_yami_ports(cls, module, intf, slave = False, *,
            prefix = '', suffix = '', uppercase = False,
            omit_ports = tuple()):
        """Create YAMI ports in ``module``.

        Args:
            module (`Module`):
            intf (`FabricIntf`):
            slave (:obj:`bool`): If set, create slave interface

        Keyword Args:
            prefix (:obj:`str`): Prefix to be added before the standard port names, e.g. "{prefix}fmc_rdy"
            suffix (:obj:`str`): Suffix to be added after the standard port names, e.g. "fmc_rdy{suffix}"
            uppercase (:obj:`bool`): If set, YAMI port names are converted to uppercase. Does not affect ``prefix`` or
                ``suffix``.
            omit_ports (:obj:`Container` [:obj:`str` ]): Exclude the specified ports from creation. Ports are named by
                standard port names only, case-insensitive

        Returns:
            :obj:`dict` [:obj:`str`, `Port` ]: Mapping from standard port names (lowercase) to ports
        """

        # omit ports
        omit_ports = set( s.lower() for s in omit_ports )

        # return values
        d = {}

        # short aliases
        def mi(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "output" if slave else "input",
                        **kwargs)

        def mo(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "input" if slave else "output",
                        **kwargs)

        # fmc channel
        mi("fmc_rdy",       1)
        mo("fmc_vld",       1)
        mo("fmc_type",      5)
        mo("fmc_size",      3)
        mo("fmc_addr",      intf.fmc_addr_width)
        mo("fmc_data",      8 << intf.fmc_data_bytes_log2)
        mo("fmc_parity",    1)

        # mfc channel
        mo("mfc_rdy",       1)
        mi("mfc_vld",       1)
        mi("mfc_type",      4)
        mi("mfc_data",      8 << intf.mfc_data_bytes_log2)
        mi("mfc_addr",      intf.mfc_addr_width)

        # piton-specific
        if intf.is_yami_piton:
            mo("fmc_thread_id", 1)
            mo("fmc_l1rplway",  2)
            mi("mfc_thread_id", 1)
            mi("mfc_l1invall",  1)
            mi("mfc_l1invway",  2)

        return d

    @classmethod
    def create_rxi_ports(cls, module, intf, slave = False,
            prefix = '', suffix = '', uppercase = False,
            omit_ports = tuple()):
        """Create RXI ports in ``module``.

        Args:
            module (`Module`):
            intf (`FabricIntf`):
            slave (:obj:`bool`): If set, create slave interface

        Keyword Args:
            prefix (:obj:`str`): Prefix to be added before the standard port names, e.g. "{prefix}req_rdy"
            suffix (:obj:`str`): Suffix to be added after the standard port names, e.g. "req_rdy{suffix}"
            uppercase (:obj:`bool`): If set, RXI port names are converted to uppercase. Does not affect ``prefix`` or
                ``suffix``.
            omit_ports (:obj:`Container` [:obj:`str` ]): Exclude the specified ports from creation. Ports are named by
                standard port names only, case-insensitive

        Returns:
            :obj:`dict` [:obj:`str`, `Port` ]: Mapping from standard port names (lowercase) to ports
        """

        # omit ports
        omit_ports = set( s.lower() for s in omit_ports )

        # return values
        d = {}

        # short aliases
        def mi(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "output" if slave else "input",
                        **kwargs)

        def mo(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "input" if slave else "output",
                        **kwargs)

        # request channel
        mi("req_rdy",       1)
        mo("req_vld",       1)
        mo("req_addr",      intf.addr_width - intf.data_bytes_log2)
        mo("req_strb",      1 << intf.data_bytes_log2)
        mo("req_data",      8 << intf.data_bytes_log2)

        # response/sync channel
        mo("resp_rdy",      1)
        mi("resp_vld",      1)
        mi("resp_sync",     1)
        mi("resp_syncaddr", 5)
        mi("resp_data",     8 << intf.data_bytes_log2)
        mi("resp_parity",   1)

        return d

    @classmethod
    def create_vldrdy_ports(cls, module, payloads, slave = False,
            prefix = '', suffix = '', uppercase = False,
            omit_ports = tuple()):
        """Create simple valid-ready interface in ``module``.

        Args:
            module (`Module`):
            payloads (:obj:`dict` [:obj:`str`, :obj:`int`]): A mapping from port names to widths
            slave (:obj:`bool`): If set, create slave interface

        Keyword Args:
            prefix (:obj:`str`): Prefix to be added before the standard port names, e.g. "{prefix}req_rdy"
            suffix (:obj:`str`): Suffix to be added after the standard port names, e.g. "req_rdy{suffix}"
            uppercase (:obj:`bool`): If set, RXI port names are converted to uppercase. Does not affect ``prefix`` or
                ``suffix``.
            omit_ports (:obj:`Container` [:obj:`str` ]): Exclude the specified ports from creation. Ports are named by
                standard port names only, case-insensitive

        Returns:
            :obj:`dict` [:obj:`str`, `Port` ]: Mapping from standard port names (lowercase) to ports
        """

        # omit ports
        omit_ports = set( s.lower() for s in omit_ports )

        # return values
        d = {}

        # short aliases
        def mi(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "output" if slave else "input",
                        **kwargs)

        def mo(n, w, **kwargs):
            if n not in omit_ports:
                d[n] = ModuleUtils.create_port(module,
                        prefix + (n.upper() if uppercase else n) + suffix,
                        w,
                        "input" if slave else "output",
                        **kwargs)

        # ports
        mi("rdy",   1)
        mo("vld",   1)
        for k, v in payloads.items():
            mo(k,   v)

        return d
