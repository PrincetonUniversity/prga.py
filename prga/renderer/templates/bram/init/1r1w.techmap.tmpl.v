module _rommap__{{ module.name }}_ (CLK1, A1ADDR, A1DATA, A1EN, B1ADDR, B1DATA, B1EN);

    localparam  ADDR_WIDTH = {{ module.ports.waddr|length }};
    localparam  DATA_WIDTH = {{ module.ports.din|length }};

    input CLK1;
    input [ADDR_WIDTH-1:0] A1ADDR;
    input A1EN;
    input [DATA_WIDTH-1:0] A1DATA;
    input [ADDR_WIDTH-1:0] B1ADDR;
    input B1EN;
    output [DATA_WIDTH-1:0] B1DATA;

    localparam NBITS = DATA_WIDTH << ADDR_WIDTH;

    parameter [NBITS - 1:0] INIT    =   { NBITS {1'bx} };
    parameter CLKPOL1               =   1;
    parameter CLKPOL2               =   1;

    {{ module.vpr_model }} #(
        .ADDR_WIDTH         (ADDR_WIDTH)
        ,.DATA_WIDTH        (DATA_WIDTH)
        ,.INIT              (INIT)
    ) _TECHMAP_REPLACE_ (
        .clk(CLK1)
        ,.waddr(A1ADDR)
        ,.din(A1DATA)
        ,.we(A1EN)
        ,.raddr(B1ADDR)
        ,.dout(B1DATA)
        );

endmodule

