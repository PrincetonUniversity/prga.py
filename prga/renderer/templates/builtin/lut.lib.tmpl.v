// Automatically generated by PRGA's RTL generator
`timescale 1ns/1ps
module {{ module.vpr_model }} #(
    parameter   WIDTH   = 6
    , parameter LUT     = 64'b0
) (
    input wire [WIDTH - 1:0] in
    , output reg [0:0] out
    );

    always @* begin
        out = LUT >> in;
    end

endmodule