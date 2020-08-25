module {{ module.name }}_wrapper (CLK1, A1ADDR, A1DATA, A1EN, B1ADDR, B1DATA, B1EN);

    input CLK1;
    input [{{ module.ports.addr1|length - 1 }}:0] A1ADDR;
    input [{{ module.ports.data1|length - 1 }}:0] A1EN;
    input [{{ module.ports.data1|length - 1 }}:0] A1DATA;
    input [{{ module.ports.addr2|length - 1 }}:0] B1ADDR;
    input B1EN;
    output [{{ module.ports.data2|length - 1 }}:0] B1DATA;

    parameter INIT      =   1'bx;
    parameter CLKPOL1   =   1;
    parameter CLKPOL2   =   1;

    wire gnd = 1'b0;

    genvar i;
    generate for (i = 0; i < {{ module.ports.data1|length }}; i = i + 1) begin: slice
        {{ module.vpr_model|default(module.name) }} _TECHMAP_REPLACE_ (
            .clk(CLK1),
            .addr1(A1ADDR),
            .data1(A1DATA[i]),
            .we1(A1EN[i]),
            .addr2(B1ADDR),
            .we2(gnd),
            .out2(B1DATA[i])
            );
    end endgenerate

endmodule

