// Automatically generated by PRGA's RTL generator
`timescale 1ns/1ps
module prga_simple_buf (
    input wire [0:0] C,
    input wire [0:0] D,
    output reg [0:0] Q
    );

    always @(posedge C) begin
        Q <= D;
    end

endmodule