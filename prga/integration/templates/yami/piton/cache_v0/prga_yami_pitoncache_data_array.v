// Automatically generated by PRGA's RTL generator

/*
* Data array for prga_yami_pitoncache.
*/

`include "prga_yami.vh"
`include "prga_yami_pitoncache.vh"
`default_nettype none

module prga_yami_pitoncache_data_array (
    // -- System Ctrl --------------------------------------------------------
    input wire                                          clk
    , input wire                                        rst_n

    // -- Stage I ------------------------------------------------------------
    , input wire                                        rd_s2
    , input wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]     index_s2

    // -- Stage II -----------------------------------------------------------
    , output reg [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]        rdata_s3

    , input wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]   way_s3
    , input wire                                        wr_s3
    , input wire [`PRGA_YAMI_MFC_DATA_BYTES-1:0]        wstrb_s3
    , input wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]        wdata_s3
    );

    localparam  LINE_WIDTH  = `PRGA_YAMI_CACHE_NUM_WAYS * `PRGA_YAMI_MFC_DATA_WIDTH;
    localparam  LINE_COUNT  = 1 << `PRGA_YAMI_CACHE_INDEX_WIDTH;

    // -- Tag Array Memory --
    reg [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]  waddr;
    wire [LINE_WIDTH-1:0]                   din;
    reg [LINE_WIDTH-1:0]                    dout;
    reg [LINE_WIDTH-1:0]                    data [0:LINE_COUNT-1];

    always @(posedge clk) begin
        if (wr_s3)
            data[waddr] <= din;
    end

    always @(posedge clk) begin
        if (~rst_n)
            waddr   <= { `PRGA_YAMI_CACHE_INDEX_WIDTH {1'b0} };
            dout    <= { LINE_WIDTH {1'b0} };
        else if (rd_s2) begin
            waddr   <= raddr;
            if (wr_s3 && waddr == index_s2)
                dout    <= din;
            else
                dout    <= data[index_s2];
        end
    end

    wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]    dout_ways [0:`PRGA_YAMI_CACHE_NUM_WAYS-1];

    genvar gv_way, gv_byte;
    generate
        for (gv_way = 0; gv_way < `PRGA_YAMI_CACHE_NUM_WAYS; gv_way = gv_way + 1) begin: g_way
            wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]    din_tmp;
            
            assign dout_ways[gv_way] = dout[`PRGA_YAMI_MFC_DATA_WIDTH * gv_way +: `PRGA_YAMI_MFC_DATA_WIDTH];
            assign din[`PRGA_YAMI_MFC_DATA_WIDTH * gv_way +: `PRGA_YAMI_MFC_DATA_WIDTH] = din_tmp;

            for (gv_byte = 0; gv_byte < `PRGA_YAMI_MFC_DATA_BYTES; gv_byte = gv_byte + 1) begin: g_byte
                assign din_tmp[gv_byte * 8 +: 8] = gv_way == way_s3 && wstrb_s3[gv_byte] ? wdata_s3[gv_byte * 8 +: 8] :
                                                                                           dout_ways[gv_way][gv_byte * 8 +: 8];
            end
        end
    endgenerate

    always @* begin
        rdata_s3 = dout_ways[way_s3];
    end

endmodule

