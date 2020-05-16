// Automatically generated by PRGA's RTL generator
module prga_async_fifo #(
    parameter DEPTH_LOG2 = 1,
    parameter DATA_WIDTH = 32,
    parameter LOOKAHEAD = 0
) (
    input wire [0:0] rst,   // synchronous reset

    input wire [0:0] wclk,
    output wire [0:0] full,
    input wire [0:0] wr,
    input wire [DATA_WIDTH - 1:0] din,

    input wire [0:0] rclk,
    output wire [0:0] empty,
    input wire [0:0] rd,
    output wire [DATA_WIDTH - 1:0] dout
    );

    // register and sync reset signals
    reg rst_wclk_s0, rst_wclk, rst_resync_wclk_s0, rst_resync_wclk, rst_lock_wclk,
        rst_rclk_s0, rst_rclk, rst_resync_rclk_s0, rst_resync_rclk, rst_lock_rclk;

    always @(posedge wclk) begin
        // sample and sync rst to wclk domain
        rst_wclk_s0 <= rst;
        rst_wclk <= rst_wclk_s0;

        // resync rst from rclk domain to wclk domain
        rst_resync_wclk_s0 <= rst_rclk;
        rst_resync_wclk <= rst_resync_wclk_s0;

        // lock interface until we got resync'ed with the rclk domain
        if (rst_resync_wclk) begin
            rst_lock_wclk <= 'b0;
        end else if (rst_wclk) begin
            rst_lock_wclk <= 'b1;
        end
    end

    always @(posedge rclk) begin
        // sample ans sync rst to rclk domain
        rst_rclk_s0 <= rst;
        rst_rclk <= rst_rclk_s0;

        // resync rst from wclk domain to rclk domain
        rst_resync_rclk_s0 <= rst_wclk;
        rst_resync_rclk <= rst_resync_rclk_s0;

        // lock interface until we got resync'ed with the wclk domain
        if (rst_resync_rclk) begin
            rst_lock_rclk <= 'b0;
        end else if (rst_rclk) begin
            rst_lock_rclk <= 'b1;
        end
    end

    // counters
    reg [DEPTH_LOG2:0]  b_wptr_wclk, g_wptr_wclk, g_wptr_rclk_s0, g_wptr_rclk_s1, b_wptr_rclk,
                        b_rptr_rclk, g_rptr_rclk, g_rptr_wclk_s0, g_rptr_wclk_s1, b_rptr_wclk;

    localparam FIFO_DEPTH = 1 << DEPTH_LOG2;
    wire empty_internal, rd_internal;
    wire [DATA_WIDTH - 1:0] ram_dout;

    prga_ram_1r1w_dc #(
        .DATA_WIDTH             (DATA_WIDTH)
        ,.ADDR_WIDTH            (DEPTH_LOG2)
        ,.RAM_ROWS              (FIFO_DEPTH)
        ,.REGISTER_OUTPUT       (1)
    ) ram (
        .wclk                   (wclk)
        ,.waddr                 (b_wptr_wclk[0 +: DEPTH_LOG2])
        ,.wdata                 (din)
        ,.we                    (~full && wr)
        ,.rclk                  (rclk)
        ,.raddr                 (b_rptr_rclk[0 +: DEPTH_LOG2])
        ,.rdata                 (ram_dout)
        );

    // gray-to-binary converting logic
    wire [DEPTH_LOG2:0] b_wptr_rclk_next, b_rptr_wclk_next;

    genvar i;
    generate
        for (i = 0; i < DEPTH_LOG2; i = i + 1) begin: b2g
            assign b_wptr_rclk_next[i] = ^(g_wptr_rclk_s1 >> i);
            assign b_rptr_wclk_next[i] = ^(g_rptr_wclk_s1 >> i);
        end
    endgenerate

    // write-domain
    always @(posedge wclk) begin
        if (rst_wclk) begin
            b_wptr_wclk <= 'b0;
            g_wptr_wclk <= 'b0;
            g_rptr_wclk_s0 <= 'b0;
            g_rptr_wclk_s1 <= 'b0;
            b_rptr_wclk <= 'b0;
        end else begin
            if (~full && wr) begin
                b_wptr_wclk <= b_wptr_wclk + 1;
            end

            g_wptr_wclk <= b_wptr_wclk ^ (b_wptr_wclk >> 1);
            g_rptr_wclk_s0 <= g_rptr_rclk;
            g_rptr_wclk_s1 <= g_rptr_wclk_s0;
            b_rptr_wclk <= b_rptr_wclk_next;
        end
    end

    // read-domain
    always @(posedge rclk) begin
        if (rst_rclk) begin
            b_rptr_rclk <= 'b0;
            g_rptr_rclk <= 'b0;
            g_wptr_rclk_s0 <= 'b0;
            g_wptr_rclk_s1 <= 'b0;
            b_wptr_rclk <= 'b0;
        end else begin
            if (~empty_internal && rd_internal) begin
                b_rptr_rclk <= b_rptr_rclk + 1;
            end

            g_rptr_rclk <= b_rptr_rclk ^ (b_rptr_rclk >> 1);
            g_wptr_rclk_s0 <= g_wptr_wclk;
            g_wptr_rclk_s1 <= g_wptr_rclk_s0;
            b_wptr_rclk <= b_wptr_rclk_next;
        end
    end

    assign full = rst_lock_wclk || b_rptr_wclk == {~b_wptr_wclk[DEPTH_LOG2], b_wptr_wclk[0 +: DEPTH_LOG2]};
    assign empty_internal = rst_lock_rclk || b_rptr_rclk == b_wptr_rclk;

    generate if (LOOKAHEAD) begin
        prga_fifo_lookahead_buffer #(
            .DATA_WIDTH             (DATA_WIDTH)
            ,.REVERSED              (0)
        ) buffer (
            .clk                    (rclk)
            ,.rst                   (rst_rclk)
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
    end

endmodule