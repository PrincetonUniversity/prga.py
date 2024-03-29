// Automatically generated by PRGA's RTL generator
`timescale 1ns/1ps
module prga_tokenfifo #(
    parameter DEPTH_LOG2 = 1
) (
    input wire [0:0] clk,
    input wire [0:0] rst,

    output wire [0:0] full,
    input wire [0:0] wr,

    output wire [0:0] empty,
    input wire [0:0] rd
    );

    localparam FIFO_DEPTH = 1 << DEPTH_LOG2;

    reg [DEPTH_LOG2:0] wr_ptr, rd_ptr;

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 'b0;
            rd_ptr <= 'b0;
        end else begin
            if (~full && wr) begin
                wr_ptr <= wr_ptr + 1;
            end

            if (~empty && rd) begin
                rd_ptr <= rd_ptr + 1;
            end
        end
    end

    assign full = rd_ptr == {~wr_ptr[DEPTH_LOG2], wr_ptr[0 +: DEPTH_LOG2]};
    assign empty = rd_ptr == wr_ptr;

endmodule

