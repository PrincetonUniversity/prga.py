# -*- encoding: ascii -*-

from .util import AppUtils
from ..netlist import Module, ModuleUtils, NetUtils

__all__ = []

# ----------------------------------------------------------------------------
# -- Common Module Mixins ----------------------------------------------------
# ----------------------------------------------------------------------------
class AppCommonMixin(object):
    """Mixin class for common modules.""" 

    def get_or_create_vldrdy_buf(self, data_width, parity = False):
        """Get or create a valid/ready buffer.

        Args:
            data_width (:obj:`int`): Bit width of the data bus
            parity (:obj:`bool`): If set, generate parity at the output

        Returns:
            `Module`:
        """

        name = "prga_app_vldrdy_{}buf_d{}".format("parity" if parity else "", data_width)

        if m := self.modules.get(name):
            return m

        m = self.add_module(Module(name,
            portgroups = {},
            verilog_template = "common/prga_app_vldrdy_{}buf.tmpl.v" .format("parity" if parity else "")
            ))

        m.portgroups.setdefault("syscon", {})[None] = AppUtils.create_syscon_ports(m, slave = True)

        ModuleUtils.create_port(m, "rdy_o",     1,          "output")
        ModuleUtils.create_port(m, "vld_i",     1,          "input")
        ModuleUtils.create_port(m, "data_i",    data_width, "input")
        ModuleUtils.create_port(m, "rdy_i",     1,          "input")
        ModuleUtils.create_port(m, "vld_o",     1,          "output")
        ModuleUtils.create_port(m, "data_o",    data_width, "output")

        if parity:
            ModuleUtils.create_port(m, "parity_o",  1,      "output")
            ModuleUtils.instantiate(m, self.get_or_create_vldrdy_buf(data_width),       "i_pre")
            ModuleUtils.instantiate(m, self.get_or_create_vldrdy_buf(data_width + 1),   "i_post")

        return m

    def __gconnect(self, mpg, spg, mnets, snets, reqnames, respnames = tuple()):
        for name in reqnames:
            if (mp := mpg.get(name)) and (sp := spg.get(name)):
                NetUtils.connect( mnets[mp.key],    snets[sp.key] )

        for name in respnames:
            if (mp := mpg.get(name)) and (sp := spg.get(name)):
                NetUtils.connect( snets[sp.key],    mnets[mp.key] )

    def connect_portgroup(self, type_, master, slave, master_id = None, slave_id = None):
        """Connect port group, and insert valid/ready buffer bettern the groups.

        Args:
            type_ (:obj:`str`): "axi4r", "axi4w", "rxi", or "yami"
            master (`Module` or `Instance`):
            slave (`Module` or `Instance`):
            master_id (:obj:`str`):
            slave_id (:obj:`str`):
        """

        # determine parent module
        module = None
        if isinstance(master, Module):
            module = master
        elif isinstance(slave, Module):
            module = slave
        else:
            module = master.parent

        # validate
        if ((not isinstance(master, Module) and master.parent is not module) or
                (slave if isinstance(slave, Module) else slave.parent) is not module):
            raise PRGAAPIError( "{} and {} are not in the same scope".format(master, slave) )

        # port groups
        mpg = (master if isinstance(master, Module) else master.model).portgroups[type_][master_id]
        spg = (slave  if isinstance(slave, Module)  else slave.model).portgroups[type_][slave_id]

        # nets
        mnets = master.ports if isinstance(master, Module) else master.pins
        snets = slave.ports  if isinstance(slave, Module)  else slave.pins

        # connect per type
        if type_ == "syscon":

            NetUtils.connect( mnets[mpg["clk"].key],    snets[spg["clk"].key] )
            NetUtils.connect( mnets[mpg["rst_n"].key],  snets[spg["rst_n"].key] )

        elif type_ == "axi4r":

            self.__gconnect( mpg, spg, mnets, snets,
                    ("arvalid", "rready",
                        "arprot", "arqos", "arburst", "arsize", "arlen", "araddr",
                        "arcache", "arlock", "aruser", "arregion", "arid"),
                    ("arready", "rvalid", "rresp", "rdata", "rlast", "ruser", "rid") )

        elif type_ == "axi4w":

            self.__gconnect( mpg, spg, mnets, snets,
                    ("awvalid", "wvalid", "bready",
                        "awprot", "awqos", "awburst", "awsize", "awlen", "awaddr",
                        "awcache", "awlock", "awuser", "awregion", "awid",
                        "wdata", "wlast", "wid", "wuser"),
                    ("awready", "wready", "bvalid", "bresp", "buser", "bid") )

        elif type_ == "rxi":

            self.__gconnect( mpg, spg, mnets, snets,
                    ("req_vld", "resp_rdy", "req_addr", "req_strb", "req_data"),
                    ("resp_vld", "req_rdy", "resp_sync", "resp_syncaddr", "resp_data", "resp_parity") )

        elif type_ == "yami":

            self.__gconnect( mpg, spg, mnets, snets,
                    ("fmc_vld", "mfc_rdy", "fmc_type", "fmc_size", "fmc_addr", "fmc_data", "fmc_parity"),
                    ("mfc_vld", "fmc_rdy", "mfc_type", "mfc_data", "mfc_addr") )

        else:
            raise NotImplementedError("Unsupported type: {}".format(type_))

    def __bgconnect(self, module, mpg, spg, mnets, snets, bufname, portnames, vldname, rdyname, parityname = None):
        """Buffered, grouped, connection."""
        parity = parityname is not None and parityname in spg

        mbus, sbus = [], []
        for name in portnames:
            if name in mpg and name in spg:
                mbus.append( mnets[mpg[name].key] )
                sbus.append( snets[spg[name].key] )

        buf_width = sum(len(n) for n in mbus)
        ibuf = ModuleUtils.instantiate(module,
                self.get_or_create_vldrdy_buf(buf_width, parity),
                bufname)

        NetUtils.connect(module.ports["clk"],       ibuf.pins["clk"])
        NetUtils.connect(module.ports["rst_n"],     ibuf.pins["rst_n"])

        NetUtils.connect(ibuf.pins["rdy_o"],        mnets[mpg[rdyname].key])
        NetUtils.connect(mnets[mpg[vldname].key],   ibuf.pins["vld_i"])
        NetUtils.connect(mbus,                      ibuf.pins["data_i"])

        NetUtils.connect(snets[spg[rdyname].key],   ibuf.pins["rdy_i"])
        NetUtils.connect(ibuf.pins["vld_o"],        snets[spg[vldname].key])
        NetUtils.connect(ibuf.pins["data_o"],       sbus)

        if parity:
            NetUtils.connect(ibuf.pins["parity_o"], snets[spg[parityname].key])

    def connect_portgroup_buf(self, type_, master, slave, master_id = None, slave_id = None, *,
            buffer_suffix = ''):
        """Connect port group, and insert valid/ready buffer bettern the groups.

        Args:
            type_ (:obj:`str`): "axi4r", "axi4w", "rxi", or "yami"
            master (`Module` or `Instance`):
            slave (`Module` or `Instance`):
            master_id (:obj:`str`):
            slave_id (:obj:`str`):

        Keyword Args:
            buffer_suffix (:obj:`str`): 
        """

        # determine parent module
        module = None
        if isinstance(master, Module):
            module = master
        elif isinstance(slave, Module):
            module = slave
        else:
            module = master.parent

        # validate
        if ((not isinstance(master, Module) and master.parent is not module) or
                (slave if isinstance(slave, Module) else slave.parent) is not module):
            raise PRGAAPIError( "{} and {} are not in the same scope".format(master, slave) )

        # port groups
        mpg = (master if isinstance(master, Module) else master.model).portgroups[type_][master_id]
        spg = (slave if isinstance(slave, Module) else slave.model).portgroups[type_][slave_id]

        # nets
        mnets = master.ports if isinstance(master, Module) else master.pins
        snets = slave.ports  if isinstance(slave, Module)  else slave.pins

        # connect per type
        if type_ == "axi4r":

            # buffer AR channel
            self.__bgconnect( module, mpg, spg, mnets, snets, "i_buf_axi4ar" + buffer_suffix,
                    ("arprot", "arqos", "arburst", "arsize", "arlen", "araddr",
                        "arcache", "arlock", "aruser", "arregion", "arid"),
                    "arvalid", "arready" )

            # buffer R channel
            self.__bgconnect( module, spg, mpg, snets, mnets, "i_buf_axi4r" + buffer_suffix,
                    ("rresp", "rdata", "rlast", "ruser", "rid"),
                    "rvalid", "rready" )

        elif type_ == "axi4w":

            # buffer AW channel
            self.__bgconnect( module, mpg, spg, mnets, snets, "i_buf_axi4aw" + buffer_suffix,
                    ("awprot", "awqos", "awburst", "awsize", "awlen", "awaddr",
                        "awcache", "awlock", "awuser", "awregion", "awid"),
                    "awvalid", "awready" )

            # buffer W channel
            self.__bgconnect( module, mpg, spg, mnets, snets, "i_buf_axi4w" + buffer_suffix,
                    ("wlast", "wdata", "wuser", "wid"),
                    "wvalid", "wready" )

            # buffer B channel
            self.__bgconnect( module, spg, mpg, snets, mnets, "i_buf_axi4b" + buffer_suffix,
                    ("bresp", "buser", "bid"),
                    "bvalid", "bready" )

        elif type_ == "rxi":

            # buffer RXI request
            self.__bgconnect( module, mpg, spg, mnets, snets, "i_buf_rxi_req" + buffer_suffix,
                    ("req_addr", "req_strb", "req_data"),
                    "req_vld", "req_rdy" )

            # buffer RXI response
            self.__bgconnect( module, spg, mpg, snets, mnets, "i_buf_rxi_resp" + buffer_suffix,
                    ("resp_sync", "resp_syncaddr", "resp_data"),
                    "resp_vld", "resp_rdy", "resp_parity" )

        elif type_ == "yami":

            # buffer FMC channel
            self.__bgconnect( module, mpg, spg, mnets, snets, "i_buf_yami_fmc" + buffer_suffix,
                    ("fmc_type", "fmc_size", "fmc_addr", "fmc_data"),
                    "fmc_vld", "fmc_rdy", "fmc_parity" )

            # buffer MFC channel
            self.__bgconnect( module, spg, mpg, snets, mnets, "i_buf_yami_mfc" + buffer_suffix,
                    ("mfc_type", "mfc_data", "mfc_addr"),
                    "mfc_vld", "mfc_rdy" )

        else:
            raise NotImplementedError("Unsupported type: {}".format(type_))
