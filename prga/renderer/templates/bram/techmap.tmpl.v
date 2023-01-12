module _mmap__{{ module.name }}_ (CLK1, A1ADDR, A1DATA, A1EN, B1ADDR, B1DATA, B1EN);

    input CLK1;
    input [{{ module.ports.addr1|length - 1 }}:0] A1ADDR;
    input A1EN;
    input A1DATA;
    input [{{ module.ports.addr2|length - 1 }}:0] B1ADDR;
    input B1EN;
    output B1DATA;

    // parameter INIT      =   1'b0;
    parameter CLKPOL1   =   1;
    parameter CLKPOL2   =   1;

    wire gnd = 1'b0;

    {{ module.vpr_model }} #(
        .ADDR_WIDTH         ({{ module.ports.addr1|length }})
    ) _TECHMAP_REPLACE_ (
        .clk(CLK1),
        .addr1(A1ADDR),
        .data1(A1DATA),
        .we1(A1EN),
        .addr2(B1ADDR),
        .we2(gnd),
        .out2(B1DATA)
        );

endmodule

