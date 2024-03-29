// Automatically generated by PRGA's blackbox library generator
`timescale 1ns/1ps
module {{ module.vpr_model }} #(
    parameter   ADDR_WIDTH = {{ module.ports.waddr|length }}
) (
    input wire clk

    , input wire we
    , input wire [ADDR_WIDTH - 1:0] waddr
    , input wire din

    , input wire [ADDR_WIDTH - 1:0] raddr
    , output reg dout
    );

    localparam  NUM_ROWS = 1 << ADDR_WIDTH;

    reg data [0:NUM_ROWS - 1];

`ifndef PRGA_POSTSYN_NO_MEMINIT
    integer i;
    initial begin
        dout = $unsigned($random) % 2;

        for (i = 0; i < NUM_ROWS; i = i + 1)
            data[i] = $unsigned($random) % 2;
    end
`endif

    always @(posedge clk) begin
        if (we) begin
            data[waddr] <= din;
        end

        dout <= data[raddr];
    end

endmodule
