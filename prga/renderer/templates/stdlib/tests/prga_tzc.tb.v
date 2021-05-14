`timescale 1ns/1ps
module prga_tzc_tb ();

    localparam  COUNTER_WIDTH = 4;
    localparam  DATA_WIDTH = 13;

    wire [COUNTER_WIDTH-1:0]    cnt;
    wire                        all_zero;
    reg [DATA_WIDTH-1:0]        data;

    prga_tzc #(
        .COUNTER_WIDTH  (COUNTER_WIDTH)
        ,.DATA_WIDTH    (DATA_WIDTH)
    ) dut (
        .data_i         (data)
        ,.cnt_o         (cnt)
        ,.all_zero_o    (all_zero)
        );

    task automatic test;
        input [DATA_WIDTH-1:0]      q;
        input [COUNTER_WIDTH-1:0]   a;
        input                       z;
        begin
            data = q;
            #1;

            if (all_zero != z) begin
                $display("[ERROR] %b should be all zeros", q);
                $display("[FAIL]");
                $finish;
            end else if (!z && cnt != a) begin
                $display("[ERROR] counting %b => %d != %d", q, cnt, a);
                $display("[FAIL]");
                $finish;
            end
        end
    endtask

    integer i;

    initial begin
        test( 13'b1_1111_1111_1111,  0, 0 );
        test( 13'b0_0000_0000_0000,  0, 1 );
        test( 13'b1_1010_0101_0000,  4, 0 );
        test( 13'b0_1100_0100_0000,  6, 0 );
        test( 13'b1_1100_0011_0010,  1, 0 );
        test( 13'b1_1000_1010_0000,  5, 0 );
        test( 13'b1_0000_0000_0000, 12, 0 );
        test( 13'b0_0001_0000_0000,  8, 0 );

        $display("[PASS]");
        $finish;
    end

endmodule
