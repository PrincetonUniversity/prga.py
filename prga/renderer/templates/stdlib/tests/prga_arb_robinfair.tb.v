`timescale 1ns/1ps
module prga_arb_robinfair_tb ();

    localparam  INDEX_WIDTH = 3;
    localparam  NUM_CANDIDATES = 5;

    reg                         clk, rst_n, ce;
    reg [NUM_CANDIDATES-1:0]    candidates;
    wire [INDEX_WIDTH-1:0]      current, next;

    prga_arb_robinfair #(
        .INDEX_WIDTH        (INDEX_WIDTH)
        ,.NUM_CANDIDATES    (NUM_CANDIDATES)
    ) dut (
        .clk            (clk)
        ,.rst_n         (rst_n)
        ,.ce            (ce)
        ,.candidates    (candidates)
        ,.current       (current)
        ,.next          (next)
        );

    always #0.5 clk = ~clk;

    task automatic check_state;
        input integer line;
        input [INDEX_WIDTH-1:0] current_expected;
        input [INDEX_WIDTH-1:0] next_expected;
        begin
            #0.1;

            if (current != current_expected) begin
                $display("[Line %04d] [ERROR] current is %d (%d expected)", line, current, current_expected);
                $display("[FAIL]");
                $finish;
            end

            #0.1;

            if (next != next_expected) begin
                $display("[Line %04d] [ERROR] next is %d (%d expected)", line, next, next_expected);
                $display("[FAIL]");
                $finish;
            end
        end
    endtask

    initial begin
        clk = 1'b0;
        rst_n = 1'b0;
        ce = 1'b0;
        candidates = { NUM_CANDIDATES {1'b0} };

        #2.2;
        rst_n = 1'b1;

        @(posedge clk);
        check_state(`__LINE__, 0, 0);

        #0.1;
        candidates = 5'b0_1010;

        @(posedge clk);
        check_state(`__LINE__, 1, 3);

        #0.1;
        ce = 1'b1;

        @(posedge clk);
        check_state(`__LINE__, 3, 1);

        $display("[PASS]");
        $finish;
    end

endmodule
