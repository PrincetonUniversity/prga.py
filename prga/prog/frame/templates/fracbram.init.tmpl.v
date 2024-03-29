{%- from 'macros/module.tmpl' import instantiation -%}
// Automatically generated by PRGA's RTL generator
`timescale 1ns/1ps
module {{ module.name }} #(
    parameter   ADDR_WIDTH = {{ module.ports.waddr|length }}
    , parameter DATA_WIDTH = {{ module.ports.din|length }}
    , parameter PROG_ADDR_WIDTH = {{ module.ports.prog_addr|length }}
    , parameter PROG_DATA_WIDTH = {{ module.ports.prog_din|length }}
) (
    input wire clk

    , input wire we
    , input wire [ADDR_WIDTH - 1:0] waddr
    , input wire [DATA_WIDTH - 1:0] din

    , input wire [ADDR_WIDTH - 1:0] raddr
    , output wire [DATA_WIDTH - 1:0] dout

    , input wire prog_clk
    , input wire prog_rst
    , input wire prog_done
    , input wire [PROG_ADDR_WIDTH - 1:0] prog_addr
    , input wire [PROG_DATA_WIDTH - 1:0] prog_din
    , input wire prog_ce
    , input wire prog_we
    , output wire [PROG_DATA_WIDTH - 1:0] prog_dout
    );

    // divide memory space
    wire prog_ce_mem, prog_ce_modesel;
    wire prog_we_mem, prog_we_modesel;
    {{ instantiation(module.instances.i_wldec) }} (
        .ce_i           (prog_ce)
        ,.we_i          (prog_we)
        ,.addr_i        (prog_addr[PROG_ADDR_WIDTH - 1])
        ,.ce_o          ({prog_ce_modesel, prog_ce_mem})
        ,.we_o          ({prog_we_modesel, prog_we_mem})
        );

    wire [PROG_DATA_WIDTH - 1:0] dout_mem, dout_modesel;
    {{ instantiation(module.instances.i_rbmerge) }} (
        .prog_clk       (prog_clk)
        ,.prog_rst      (prog_rst)
        ,.dout          (prog_dout)
        ,.ce            ({prog_ce_modesel, prog_ce_mem})
        ,.din0          (dout_mem)
        ,.din1          (dout_modesel)
        );

    // controllers
    //  mode selection bits
    wire [{{ module.instances.i_modesel.pins.prog_data_o|length }} - 1:0] modesel;
    {{ instantiation(module.instances.i_modesel) }} (
        .prog_clk       (prog_clk)
        ,.prog_rst      (prog_rst)
        ,.prog_done     (prog_done)
        {%- if module.instances.i_modesel.pins.prog_addr %}
        ,.prog_addr     (prog_addr[0 +: {{ module.instances.i_modesel.pins.prog_addr|length }}])
        {%- endif %}
        ,.prog_din      (prog_din)
        ,.prog_ce       (prog_ce_modesel)
        ,.prog_we       (prog_we_modesel)
        ,.prog_data_o   (modesel)
        ,.prog_dout     (dout_modesel)
        );

    //  fracturable memory controller
    localparam  CORE_ADDR_WIDTH = {{ module.core_addr_width }};

    wire                            u_we, u_re;
    wire [CORE_ADDR_WIDTH - 1:0]    u_waddr, u_raddr;
    wire [DATA_WIDTH - 1:0]         u_din, u_bw, u_dout;

    {{ instantiation(module.instances.i_frac) }} (
        .clk            (clk)
        ,.u_waddr_i     (waddr)
        ,.u_we_i        (we)
        ,.u_din_i       (din)
        ,.u_raddr_i     (raddr)
        ,.u_dout_o      (dout)
        ,.ip_waddr_o    (u_waddr)
        ,.ip_we_o       (u_we)
        ,.ip_din_o      (u_din)
        ,.ip_bw_o       (u_bw)
        ,.ip_raddr_o    (u_raddr)
        ,.ip_re_o       (u_re)
        ,.ip_dout_i     (u_dout)
        ,.prog_done     (prog_done)
        ,.prog_data     (modesel)
        );

    //  memory initialization controller
    wire                            ip_clk, ip_rst, ip_we, ip_re;
    wire [CORE_ADDR_WIDTH - 1:0]    ip_waddr, ip_raddr;
    wire [DATA_WIDTH - 1:0]         ip_din, ip_bw, ip_dout;

    {{ instantiation(module.instances.i_init) }} (
        .u_clk                  (clk)
        ,.u_we                  (u_we)
        ,.u_waddr               (u_waddr)
        ,.u_din                 (u_din)
        ,.u_bw                  (u_bw)
        ,.u_re                  (u_re)
        ,.u_raddr               (u_raddr)
        ,.u_dout                (u_dout)

        ,.prog_clk              (prog_clk)
        ,.prog_rst              (prog_rst)
        ,.prog_done             (prog_done)
        ,.prog_addr             (prog_addr[0 +: PROG_ADDR_WIDTH - 1])
        ,.prog_din              (prog_din)
        ,.prog_ce               (prog_ce_mem)
        ,.prog_we               (prog_we_mem)
        ,.prog_dout             (dout_mem)
            
        ,.ip_clk                (ip_clk)
        ,.ip_rst                (ip_rst)
        ,.ip_we                 (ip_we)
        ,.ip_waddr              (ip_waddr)
        ,.ip_din                (ip_din)
        ,.ip_bw                 (ip_bw)
        ,.ip_re                 (ip_re)
        ,.ip_raddr              (ip_raddr)
        ,.ip_dout               (ip_dout)
        );

    // internal memory
    {{ instantiation(module.instances.i_ram) }} (
        .clk                    (ip_clk)
        ,.rst                   (ip_rst)
        ,.we                    (ip_we)
        ,.waddr                 (ip_waddr)
        ,.din                   (ip_din)
        ,.bw                    (ip_bw)
        ,.re                    (ip_re)
        ,.raddr                 (ip_raddr)
        ,.dout                  (ip_dout)
        );

endmodule
