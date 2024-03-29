// Automatically generated by PRGA's RTL generator
`timescale 1ns/1ps
module {{ module.name }} (
    input wire [0:0] clk
    , input wire [0:0] D
    , output reg [0:0] Q

    , input wire [0:0] prog_done    // programming finished
    , input wire [0:0] prog_data    // mode: enabled (not disabled)
    );

    always @(posedge clk) begin
        if (~prog_done || ~prog_data) begin
            Q <= 1'b0;
        end else begin
            Q <= D;
        end
    end

endmodule
