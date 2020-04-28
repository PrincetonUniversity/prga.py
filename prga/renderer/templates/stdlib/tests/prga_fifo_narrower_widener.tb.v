module prga_fifo_narrower_widener_tb ();

    localparam DATA_WIDTH = 8;
    localparam MULTIPLIER = 4;

    reg clk, rst;
    reg [DATA_WIDTH - 1:0] src [0:1023];

    initial begin
        clk = 'b0;
        rst = 'b0;

        src[0] = 'h5A;
        src[1] = 'hF6;
        src[2] = 'h09;
        src[3] = 'hC4;
        src[4] = 'h81;
        src[5] = 'hE2;
        src[6] = 'hA0;
        src[7] = 'h7A;

        $dumpfile("dump.vcd");
        $dumpvars;

        #3;
        rst = 'b1;
        #10;
        rst = 'b0;

        #10000;
        $display("[TIMEOUT]");
        $finish;
    end

    always #5 clk = ~clk;

    wire A_full, A_empty, B_full, B_empty, C_full, C_empty;
    wire [DATA_WIDTH - 1:0] A_dout, C_din, C_dout;
    wire [DATA_WIDTH * MULTIPLIER - 1:0] B_din, B_dout;
    wire A_rd, A_wr, B_rd, B_wr, C_wr;
    reg C_rd;
    integer A_wr_cnt, C_rd_cnt;

    prga_fifo #(
        .DATA_WIDTH                     (DATA_WIDTH)
        ,.DEPTH_LOG2                    (2)
        ,.LOOKAHEAD                     (1)
    ) A (
        .clk        (clk)
        ,.rst       (rst)
        ,.full      (A_full)
        ,.wr        (src[A_wr_cnt] !== {DATA_WIDTH{1'bx}})
        ,.din       (src[A_wr_cnt])
        ,.empty     (A_empty)
        ,.rd        (A_rd)
        ,.dout      (A_dout)
        );

    prga_fifo_widener #(
        .DATA_WIDTH                     (DATA_WIDTH)
        ,.MULTIPLIER                    (MULTIPLIER)
    ) widener (
        .clk        (clk)
        ,.rst       (rst)
        ,.empty_i   (A_empty)
        ,.rd_i      (A_rd)
        ,.dout_i    (A_dout)
        ,.full_o    (B_full)
        ,.wr_o      (B_wr)
        ,.din_o     (B_din)
        );

    prga_fifo #(
        .DATA_WIDTH                     (DATA_WIDTH * MULTIPLIER)
        ,.DEPTH_LOG2                    (2)
        ,.LOOKAHEAD                     (1)
    ) B (
        .clk        (clk)
        ,.rst       (rst)
        ,.full      (B_full)
        ,.wr        (B_wr)
        ,.din       (B_din)
        ,.empty     (B_empty)
        ,.rd        (B_rd)
        ,.dout      (B_dout)
        );

    prga_fifo_narrower #(
        .DATA_WIDTH                     (DATA_WIDTH)
        ,.MULTIPLIER                    (MULTIPLIER)
    ) narrower (
        .clk        (clk)
        ,.rst       (rst)
        ,.empty_i   (B_empty)
        ,.rd_i      (B_rd)
        ,.dout_i    (B_dout)
        ,.full_o    (C_full)
        ,.wr_o      (C_wr)
        ,.din_o     (C_din)
        );

    prga_fifo #(
        .DATA_WIDTH                     (DATA_WIDTH)
        ,.DEPTH_LOG2                    (2)
        ,.LOOKAHEAD                     (1)
    ) C (
        .clk        (clk)
        ,.rst       (rst)
        ,.full      (C_full)
        ,.wr        (C_wr)
        ,.din       (C_din)
        ,.empty     (C_empty)
        ,.rd        (C_rd)
        ,.dout      (C_dout)
        );

    reg error;

    always @(posedge clk) begin
        if (rst) begin
            A_wr_cnt <= 'b0;
            C_rd_cnt <= 'b0;
            C_rd <= 'b0;
            error <= 'b0;
        end else begin
            if (!A_full && src[A_wr_cnt] !== {DATA_WIDTH{1'bx}}) begin
                A_wr_cnt <= A_wr_cnt + 1;
            end

            if (!C_empty && C_rd) begin
                if (src[C_rd_cnt] !== C_dout) begin
                    error <= 'b1;
                    $display("[ERROR] C output No. %d 0x%08x != 0x%08x", C_rd_cnt, C_dout, src[C_rd_cnt]);
                end
                C_rd_cnt <= C_rd_cnt + 1;
            end

            C_rd <= $random() % 3 == 0;

            if (src[C_rd_cnt] === {DATA_WIDTH{1'bx}}) begin
                if (error) begin
                    $display("[FAIL]");
                end else begin
                    $display("[PASS]");
                end
                $finish;
            end
        end
    end

endmodule
