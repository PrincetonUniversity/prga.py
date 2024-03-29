// Automatically generated by PRGA's RTL generator
`timescale 1ns/1ps
module {{ module.name }} (
    input wire [0:0] prog_clk
    , input wire [0:0] prog_rst
    , input wire [0:0] prog_done

    , input wire [0:0] prog_we
    , input wire [{{ module.ports.prog_din|length }} - 1:0] prog_din

    , output reg [{{ module.ports.prog_data|length }} - 1:0] prog_data
    , output wire [{{ module.ports.prog_dout|length }} - 1:0] prog_dout
    );

    localparam CHAIN_BITCOUNT = {{ module.ports.prog_data|length }};
    localparam CHAIN_WIDTH = {{ module.ports.prog_din|length }};

    wire [CHAIN_BITCOUNT + CHAIN_WIDTH - 1:0] prog_data_next;
    assign prog_data_next = {prog_data, prog_din};

    always @(posedge prog_clk) begin
        if (prog_rst) begin
            prog_data <= {CHAIN_BITCOUNT{1'b0}};
        end else if (~prog_done && prog_we) begin
            prog_data <= prog_data_next[0 +: CHAIN_BITCOUNT];
        end
    end

    assign prog_dout = prog_data_next[CHAIN_BITCOUNT +: CHAIN_WIDTH];

endmodule
