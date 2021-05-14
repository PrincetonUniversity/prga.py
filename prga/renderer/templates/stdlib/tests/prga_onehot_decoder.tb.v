`timescale 1ns/1ps
module prga_onehot_decoder_tb ();

    localparam  INDEX_WIDTH = 4;
    localparam  DATA_WIDTH = 13;

    wire [INDEX_WIDTH-1:0]  idx;
    reg [DATA_WIDTH-1:0]    data;

    prga_onehot_decoder #(
        .INDEX_WIDTH    (4)
        ,.DATA_WIDTH    (13)
    ) dut (
        .data_i         (data)
        ,.idx_o         (idx)
        );

    task automatic test;
        input [DATA_WIDTH-1:0]      q;
        input [INDEX_WIDTH-1:0]     a;
        begin
            data = q;
            #1;

            if (idx != a) begin
                $display("[ERROR] decoding %b => %d != %d", q, idx, a);
                $display("[FAIL]");
                $finish;
            end
        end
    endtask

    integer i;

    initial begin
        for (i = 0; i < DATA_WIDTH; i = i + 1) begin
            test( 1 << i, i );
        end

        test( 0, { INDEX_WIDTH {1'b1} } );

        $display("[PASS]");
        $finish;
    end

endmodule
