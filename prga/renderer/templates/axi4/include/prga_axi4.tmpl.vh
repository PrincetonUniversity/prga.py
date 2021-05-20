`ifndef PRGA_AXI4_VH
`define PRGA_AXI4_VH

`define PRGA_AXI4_XRESP_WIDTH   2
`define PRGA_AXI4_XRESP_OKAY    2'b00
`define PRGA_AXI4_XRESP_EXOKAY  2'b01
`define PRGA_AXI4_XRESP_SLVERR  2'b10
`define PRGA_AXI4_XRESP_DECERR  2'b11

`define PRGA_AXI4_AXLEN_WIDTH   8

`define PRGA_AXI4_AXSIZE_WIDTH  3
`define PRGA_AXI4_AXSIZE_1B     3'b000
`define PRGA_AXI4_AXSIZE_2B     3'b001
`define PRGA_AXI4_AXSIZE_4B     3'b010
`define PRGA_AXI4_AXSIZE_8B     3'b011
`define PRGA_AXI4_AXSIZE_16B    3'b100
`define PRGA_AXI4_AXSIZE_32B    3'b101
`define PRGA_AXI4_AXSIZE_64B    3'b110
`define PRGA_AXI4_AXSIZE_128B   3'b111

`define PRGA_AXI4_AXBURST_WIDTH 2
`define PRGA_AXI4_AXBURST_FIXED 2'b00
`define PRGA_AXI4_AXBURST_INCR  2'b01
`define PRGA_AXI4_AXBURST_WRAP  2'b10

`define PRGA_AXI4_AXCACHE_WIDTH         4
// non-cacheable transactions
`define PRGA_AXI4_AXCACHE_DEV_NB        4'b0000     // device, non-bufferable
`define PRGA_AXI4_AXCACHE_DEV_BUF       4'b0001     // device, bufferable
`define PRGA_AXI4_AXCACHE_NORM_NC_NB    4'b0010     // normal, non-cacheable, non-bufferable
`define PRGA_AXI4_AXCACHE_NORM_NC_BUF   4'b0011     // normal, non-cahecable, bufferable
// cacheable reads
`define PRGA_AXI4_ARCACHE_WT_NA         4'b1010     // write-through, no-allocation
`define PRGA_AXI4_ARCACHE_WT_ALCT       4'b1110     // write-through, allocation
`define PRGA_AXI4_ARCACHE_WT_ALCT_ALT   4'b0110     // write-through, allocation
`define PRGA_AXI4_ARCACHE_WB_NA         4'b1110     // write-back, no-allocation
`define PRGA_AXI4_ARCACHE_WB_ALCT       4'b1111     // write-back, allocation
`define PRGA_AXI4_ARCACHE_WB_ALCT_ALT   4'b0111     // write-back, allocation
// cacheable writes
`define PRGA_AXI4_AWCACHE_WT_NA         4'b0110     // write-through, no-allocation
`define PRGA_AXI4_AWCACHE_WT_ALCT       4'b1110     // write-through, allocation
`define PRGA_AXI4_AWCACHE_WT_ALCT_ALT   4'b1010     // write-through, allocation
`define PRGA_AXI4_AWCACHE_WB_NA         4'b0111     // write-back, no-allocation
`define PRGA_AXI4_AWCACHE_WB_ALCT       4'b1111     // write-back, allocation
`define PRGA_AXI4_AWCACHE_WB_ALCT_ALT   4'b1011     // write-back, allocation

`define PRGA_AXI4_AXPROT_WIDTH          3
`define PRGA_AXI4_AXPROT_PRVL_INDEX     0
`define PRGA_AXI4_AXPROT_NSCR_INDEX     1
`define PRGA_AXI4_AXPROT_INST_INDEX     2

`define PRGA_AXI4_AXQOS_WIDTH           4
`define PRGA_AXI4_AXREGION_WIDTH        4

`endif /* `ifndef PRGA_AXI4_VH */
