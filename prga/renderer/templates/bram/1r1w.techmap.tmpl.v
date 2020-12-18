module _mmap__{{ module.name }}_ (CLK1, A1ADDR, A1DATA, A1EN, B1ADDR, B1DATA, B1EN);

    input CLK1;
    input [{{ module.ports.waddr|length - 1 }}:0] A1ADDR;
    input A1EN;
    input A1DATA;
    input [{{ module.ports.raddr|length - 1 }}:0] B1ADDR;
    input B1EN;
    output B1DATA;

    parameter INIT      =   1'bx;
    parameter CLKPOL1   =   1;
    parameter CLKPOL2   =   1;

    {{ module.vpr_model }} _TECHMAP_REPLACE_ (
        .clk(CLK1)
        ,.waddr(A1ADDR)
        ,.din(A1DATA)
        ,.we(A1EN)
        ,.raddr(B1ADDR)
        ,.dout(B1DATA)
        );

endmodule

