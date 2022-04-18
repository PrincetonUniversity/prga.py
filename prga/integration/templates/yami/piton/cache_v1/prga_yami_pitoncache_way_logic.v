// Automatically generated by PRGA's RTL generator

/*
* Hit/Replace way logic for prga_yami_pitoncache.
*/

`include "prga_yami.vh"
`include "prga_yami_pitoncache.vh"
`default_nettype none

module prga_yami_pitoncache_way_logic (
    // -- System Ctrl --------------------------------------------------------
    input wire                                          clk
    , input wire                                        rst_n

    // -- Stage II -----------------------------------------------------------
    , input wire [`PRGA_YAMI_CACHE_NUM_WAYS * `PRGA_YAMI_CACHE_STATE_WIDTH-1:0] stateline_s2
    , input wire [`PRGA_YAMI_CACHE_NUM_WAYS * `PRGA_YAMI_CACHE_TAG_WIDTH-1:0]   tagline_s2
    , input wire [`PRGA_YAMI_CACHE_NUM_WAYS * `PRGA_YAMI_CACHE_LRU_WIDTH-1:0]   lruline_s2
    , input wire [`PRGA_YAMI_CACHE_TAG_WIDTH-1:0]       tag_s2

    // -- Stage III ----------------------------------------------------------
    , input wire                                        stall_s3
    , output reg                                        hit_s3
    , output reg [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]   way_s3      // hit way if ``hit_s3``, else replacement way
    , output reg                                        iv_s3

    , output reg [`PRGA_YAMI_CACHE_NUM_WAYS-1:0]        lru_inc_mask_s3
    , output reg [`PRGA_YAMI_CACHE_NUM_WAYS-1:0]        lru_clr_mask_s3
    );

    generate
        if (`PRGA_YAMI_CACHE_NUM_WAYS != 4) begin
            __PRGA_MACRO_ERROR__ __error__();
        end
    endgenerate

    reg                                         hit_s3_next, iv_s3_next;
    reg [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]    way_s2;
    wire [`PRGA_YAMI_CACHE_NUM_WAYS-1:0]        lru_inc_mask_s3_next, lru_clr_mask_s3_next;

    always @(posedge clk) begin
        if (~rst_n) begin
            hit_s3          <= 1'b0;
            way_s3          <= { `PRGA_YAMI_CACHE_NUM_WAYS_LOG2 {1'b0} };
            iv_s3           <= 1'b0;
            lru_inc_mask_s3 <= { `PRGA_YAMI_CACHE_NUM_WAYS {1'b0} };
            lru_clr_mask_s3 <= { `PRGA_YAMI_CACHE_NUM_WAYS {1'b0} };
        end else if (!stall_s3) begin
            hit_s3          <= hit_s3_next;
            way_s3          <= way_s2;
            iv_s3           <= iv_s3_next;
            lru_inc_mask_s3 <= lru_inc_mask_s3_next;
            lru_clr_mask_s3 <= lru_clr_mask_s3_next;
        end
    end

    // -- Decompose Ways --
    wire [`PRGA_YAMI_CACHE_STATE_WIDTH-1:0] state_ways  [0:`PRGA_YAMI_CACHE_NUM_WAYS-1];
    wire [`PRGA_YAMI_CACHE_TAG_WIDTH-1:0]   tag_ways    [0:`PRGA_YAMI_CACHE_NUM_WAYS-1];
    wire [`PRGA_YAMI_CACHE_LRU_WIDTH-1:0]   lru_ways    [0:`PRGA_YAMI_CACHE_NUM_WAYS-1];

    reg  [`PRGA_YAMI_CACHE_LRU_WIDTH-1:0]   lru_rpl;

    genvar gv_way;
    generate
        for (gv_way = 0; gv_way < `PRGA_YAMI_CACHE_NUM_WAYS; gv_way = gv_way + 1) begin: g_way
            wire [`PRGA_YAMI_CACHE_STATE_WIDTH-1:0] state;
            wire [`PRGA_YAMI_CACHE_TAG_WIDTH-1:0]   tag;
            wire [`PRGA_YAMI_CACHE_LRU_WIDTH-1:0]   lru;

            assign state    = stateline_s2[gv_way * `PRGA_YAMI_CACHE_STATE_WIDTH +: `PRGA_YAMI_CACHE_STATE_WIDTH];
            assign tag      = tagline_s2  [gv_way * `PRGA_YAMI_CACHE_TAG_WIDTH   +: `PRGA_YAMI_CACHE_TAG_WIDTH];
            assign lru      = lruline_s2  [gv_way * `PRGA_YAMI_CACHE_LRU_WIDTH   +: `PRGA_YAMI_CACHE_LRU_WIDTH];

            assign state_ways[gv_way]   = state;
            assign tag_ways[gv_way]     = tag;
            assign lru_ways[gv_way]     = lru;

            assign lru_inc_mask_s3_next[gv_way] = (state == `PRGA_YAMI_CACHE_STATE_IV || state == `PRGA_YAMI_CACHE_STATE_V)
                                                  && lru < lru_rpl;
            assign lru_clr_mask_s3_next[gv_way] = gv_way == way_s2;
        end
    endgenerate

    // -- Way Logic --
    always @* begin
        hit_s3_next     = 1'b0;
        way_s2     = { `PRGA_YAMI_CACHE_NUM_WAYS_LOG2 {1'b0} };

        // find hit
        if (tag_ways[0] == tag_s2 &&
            (state_ways[0] == `PRGA_YAMI_CACHE_STATE_IV || state_ways[0] == `PRGA_YAMI_CACHE_STATE_V)
        ) begin
            hit_s3_next = 1'b1;
            way_s2 = 0;
        end

        else if (tag_ways[1] == tag_s2 &&
            (state_ways[1] == `PRGA_YAMI_CACHE_STATE_IV || state_ways[1] == `PRGA_YAMI_CACHE_STATE_V)
        ) begin
            hit_s3_next = 1'b1;
            way_s2 = 1;
        end

        else if (tag_ways[2] == tag_s2 &&
            (state_ways[2] == `PRGA_YAMI_CACHE_STATE_IV || state_ways[2] == `PRGA_YAMI_CACHE_STATE_V)
        ) begin
            hit_s3_next = 1'b1;
            way_s2 = 2;
        end

        else if (tag_ways[3] == tag_s2 &&
            (state_ways[3] == `PRGA_YAMI_CACHE_STATE_IV || state_ways[3] == `PRGA_YAMI_CACHE_STATE_V)
        ) begin
            hit_s3_next = 1'b1;
            way_s2 = 3;
        end

        // find replacement: invalid line
        else if (state_ways[0] == `PRGA_YAMI_CACHE_STATE_I)
            way_s2 = 0;
        else if (state_ways[1] == `PRGA_YAMI_CACHE_STATE_I)
            way_s2 = 1;
        else if (state_ways[2] == `PRGA_YAMI_CACHE_STATE_I)
            way_s2 = 2;
        else if (state_ways[3] == `PRGA_YAMI_CACHE_STATE_I)
            way_s2 = 3;

        // find replacement: LRU == 3 && not IV
        else if (state_ways[0] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[0] == 3)
            way_s2 = 0;
        else if (state_ways[1] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[1] == 3)
            way_s2 = 1;
        else if (state_ways[2] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[2] == 3)
            way_s2 = 2;
        else if (state_ways[3] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[3] == 3)
            way_s2 = 3;

        // find replacement: LRU == 2 && not IV
        else if (state_ways[0] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[0] == 2)
            way_s2 = 0;
        else if (state_ways[1] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[1] == 2)
            way_s2 = 1;
        else if (state_ways[2] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[2] == 2)
            way_s2 = 2;
        else if (state_ways[3] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[3] == 2)
            way_s2 = 3;

        // find replacement: LRU == 1 && not IV
        else if (state_ways[0] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[0] == 1)
            way_s2 = 0;
        else if (state_ways[1] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[1] == 1)
            way_s2 = 1;
        else if (state_ways[2] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[2] == 1)
            way_s2 = 2;
        else if (state_ways[3] == `PRGA_YAMI_CACHE_STATE_V && lru_ways[3] == 1)
            way_s2 = 3;

        // find replacement: LRU == 0 && not IV
        else if (state_ways[0] == `PRGA_YAMI_CACHE_STATE_V)
            way_s2 = 0;
        else if (state_ways[1] == `PRGA_YAMI_CACHE_STATE_V)
            way_s2 = 1;
        else if (state_ways[2] == `PRGA_YAMI_CACHE_STATE_V)
            way_s2 = 2;
        else if (state_ways[3] == `PRGA_YAMI_CACHE_STATE_V)
            way_s2 = 3;

    end

    always @* begin
        iv_s3_next      =   state_ways[way_s2] == `PRGA_YAMI_CACHE_STATE_IV;
        lru_rpl         =   state_ways[way_s2] == `PRGA_YAMI_CACHE_STATE_I ? 
                            { `PRGA_YAMI_CACHE_LRU_WIDTH {1'b0} } :
                            lru_ways[way_s2];
    end

endmodule
