// Automatically generated by PRGA's RTL generator
`timescale 1ns/1ps
module prga_fifo #(
    parameter DEPTH_LOG2 = 1,
    parameter DATA_WIDTH = 32,
    parameter LOOKAHEAD = 0,
    parameter ALLOW_RAM_UNREGISTERED_OUTPUT = 0
) (
    input wire [0:0] clk,
    input wire [0:0] rst,

    output wire [0:0] full,
    input wire [0:0] wr,
    input wire [DATA_WIDTH - 1:0] din,

    output wire [0:0] empty,
    input wire [0:0] rd,
    output wire [DATA_WIDTH - 1:0] dout
    );

    // register reset signal for timing purpose
    reg rst_f;

    always @(posedge clk) begin
        rst_f <= rst;
    end

    localparam FIFO_DEPTH = 1 << DEPTH_LOG2;

    reg [DEPTH_LOG2:0] wr_ptr, rd_ptr;
    wire empty_internal, rd_internal;
    wire [DATA_WIDTH - 1:0] ram_dout;

    prga_ram_1r1w #(
        .DATA_WIDTH         (DATA_WIDTH)
        ,.ADDR_WIDTH        (DEPTH_LOG2)
        ,.RAM_ROWS          (FIFO_DEPTH)
        ,.REGISTER_OUTPUT   (!ALLOW_RAM_UNREGISTERED_OUTPUT || !LOOKAHEAD)
    ) ram (
        .clk                (clk)
        ,.raddr             (rd_ptr[0 +: DEPTH_LOG2])
        ,.dout              (ram_dout)
        ,.waddr             (wr_ptr[0 +: DEPTH_LOG2])
        ,.din               (din)
        ,.we                (!full && wr)
        );

    always @(posedge clk) begin
        if (rst) begin
            wr_ptr <= 'b0;
            rd_ptr <= 'b0;
        end else begin
            if (~full && wr) begin
                wr_ptr <= wr_ptr + 1;
            end

            if (~empty_internal && rd_internal) begin
                rd_ptr <= rd_ptr + 1;
            end
        end
    end

    assign full = rst_f || rd_ptr == {~wr_ptr[DEPTH_LOG2], wr_ptr[0 +: DEPTH_LOG2]};
    assign empty_internal = rst_f || rd_ptr == wr_ptr;

    generate if (LOOKAHEAD && !ALLOW_RAM_UNREGISTERED_OUTPUT) begin
        prga_fifo_lookahead_buffer #(
            .DATA_WIDTH             (DATA_WIDTH)
            ,.REVERSED              (0)
        ) buffer (
            .clk                    (clk)
            ,.rst                   (rst)
            ,.empty_i               (empty_internal)
            ,.rd_i                  (rd_internal)
            ,.dout_i                (ram_dout)
            ,.empty                 (empty)
            ,.rd                    (rd)
            ,.dout                  (dout)
            );
    end else begin
        assign rd_internal = rd;
        assign dout = ram_dout;
        assign empty = empty_internal;
    end endgenerate

endmodule
