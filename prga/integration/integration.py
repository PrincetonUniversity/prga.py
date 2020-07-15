# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from ..core.common import ModuleView, ModuleClass
from ..netlist.module.module import Module
from ..netlist.module.util import ModuleUtils
from ..exception import PRGAAPIError, PRGAInternalError

__all__ = ["Integration"]

# ----------------------------------------------------------------------------
# -- Wrapping the FPGA fabric for Hybrid Integration -------------------------
# ----------------------------------------------------------------------------
class Integration(object):
    """Wrapper class for utility functions that helps integrating the fabric into a hybrid system."""

    @classmethod
    def _register_lib(cls, context):
        """Register integration-related modules in to the module database.

        Args:
            context (`Context`):
        """
        # 1. add prga_system header
        context._add_verilog_header("prga_system.vh", "include/prga_system.tmpl.vh")

        # 2. register modules
        for d in ("prga_ctrl", "prga_ecc_parity", "prga_mprot", "prga_sax", "prga_uprot"):
            context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "{}.v".format(d))
        for d in ("prga_l15_transducer", ):
            context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "piton/{}.v".format(d))
        for d in ("prga_fe_axi4lite", ):
            context._database[ModuleView.logical, d] = Module(d,
                    view = ModuleView.logical,
                    module_class = ModuleClass.aux,
                    verilog_template = "axi4lite/{}.v".format(d))
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
