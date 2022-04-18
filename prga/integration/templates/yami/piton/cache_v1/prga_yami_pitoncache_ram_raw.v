// Automatically generated by PRGA's RTL generator

/*
* Read-after-write RAM
*/

`default_nettype none

module prga_yami_pitoncache_ram_raw #(
    parameter   ADDR_WIDTH  = 4
    , parameter DATA_WIDTH  = 8
    , parameter INITIALIZE  = 0
) (
    input wire                      clk
    , input wire                    rst_n

    , input wire                    we
    , input wire [ADDR_WIDTH-1:0]   waddr
    , input wire [DATA_WIDTH-1:0]   d

    , input wire                    re
    , input wire [ADDR_WIDTH-1:0]   raddr
    , output wire [DATA_WIDTH-1:0]  q
    );

    reg                     use_dout;
    reg [DATA_WIDTH-1:0]    d_f, dout;

    reg [DATA_WIDTH-1:0]    data    [(1 << ADDR_WIDTH)-1:0];

    always @(posedge clk) begin
        if (~rst_n) begin
            use_dout    <= 1'b0;
        end else begin
            use_dout    <= re && (!we || waddr != raddr);
        end
    end

    always @(posedge clk) begin
        d_f     <= d;
    end

    always @(posedge clk) begin
        dout <= data[raddr];

        if (we)
            data[waddr] <= d;
    end

    assign q = use_dout ? dout : d_f;

    generate if (INITIALIZE) begin
        integer data_init;
        initial begin
            for (data_init = 0; data_init < (1 << ADDR_WIDTH); data_init = data_init + 1) begin
                data[data_init] = { DATA_WIDTH {1'b0} };
            end
        end
    end endgenerate

endmodule
