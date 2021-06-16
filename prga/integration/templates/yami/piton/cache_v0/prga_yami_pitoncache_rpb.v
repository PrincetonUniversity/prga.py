// Automatically generated by PRGA's RTL generator

/*
* Request RePlay Buffer for prga_yami_pitoncache.
*/

module prga_yami_pitoncache_rpb (
    // -- System Ctrl --------------------------------------------------------
    input wire                                          clk
    , input wire                                        rst_n

    // -- Enqueue ------------------------------------------------------------
    // -- Stage II --
    , input wire                                        rpb_vld_s2
    , input wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]         rpb_reqtype_s2
    , input wire [`PRGA_YAMI_SIZE_WIDTH-1:0]            rpb_size_s2
    , input wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]        rpb_addr_s2
    , input wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]        rpb_data_s2

    // -- Stage III --
    , input wire                                        enqueue_rpb_s3
    , input wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]         rpb_reqtype_s3
    , input wire [`PRGA_YAMI_SIZE_WIDTH-1:0]            rpb_size_s3
    , input wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]        rpb_addr_s3
    , input wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]        rpb_data_s3
    , input wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rpb_rob_entry_s3

    // -- Validate -----------------------------------------------------------
    , input wire                                        validate_rpb_s2
    , input wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]     index_s2

    // -- Dequeue ------------------------------------------------------------
    , input wire                                        dequeue_rpb_s1
    , output wire                                       rpb_empty_s1
    , output wire                                       rpb_vld_s1
    , output wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]        rpb_reqtype_s1
    , output wire [`PRGA_YAMI_SIZE_WIDTH-1:0]           rpb_size_s1
    , output wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]       rpb_addr_s1
    , output wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]       rpb_data_s1
    , output wire                                       rpb_rob_entry_vld_s1
    , output wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]   rpb_rob_entry_s1
    );

    // -- FSM --
    localparam  ST_WIDTH        = 2;
    localparam  ST_RST          = 2'd0,
                ST_EMPTY        = 2'd1,
                ST_S3_BUFFERED  = 2'd2,     // S3 buffered
                ST_S2_BUFFERED  = 2'd3;

    reg [ST_WIDTH-1:0]  state, state_next;

    always @(posedge clk) begin
        if (~rst_n) begin
            state   <= ST_RST;
        end else begin
            state   <= state_next;
        end
    end

    // -- buffer S2 request --
    reg                                 s2buf_vld;
    reg [`PRGA_YAMI_REQTYPE_WIDTH-1:0]  s2buf_reqtype;
    reg [`PRGA_YAMI_SIZE_WIDTH-1:0]     s2buf_size;
    reg [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0] s2buf_addr;
    reg [`PRGA_YAMI_FMC_DATA_WIDTH-1:0] s2buf_data;

    always @(posedge clk) begin
        if (~rst_n) begin
            s2buf_vld       <= 1'b0;
            s2buf_reqtype   <= `PRGA_YAMI_REQTYPE_NONE;
            s2buf_size      <= { `PRGA_YAMI_SIZE_WIDTH {1'b0} };
            s2buf_addr      <= { `PRGA_YAMI_FMC_ADDR_WIDTH {1'b0} };
            s2buf_data      <= { `PRGA_YAMI_FMC_DATA_WIDTH {1'b0} };
        end else if (state == ST_S2_BUFFERED && dequeue_rpb_s1) begin
            s2buf_vld       <= 1'b0;
        end else if (rpb_vld_s2) begin
            s2buf_vld       <= 1'b1;
            s2buf_reqtype   <= rpb_reqtype_s2;
            s2buf_size      <= rpb_size_s2;
            s2buf_addr      <= rpb_addr_s2;
            s2buf_data      <= rpb_data_s2;
        end
    end

    // -- buffer S3 request --
    reg                                 s3buf_vld;
    reg [`PRGA_YAMI_REQTYPE_WIDTH-1:0]  s3buf_reqtype;
    reg [`PRGA_YAMI_SIZE_WIDTH-1:0]     s3buf_size;
    reg [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0] s3buf_addr;
    reg [`PRGA_YAMI_FMC_DATA_WIDTH-1:0] s3buf_data;
    reg [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]     s3buf_rob_entry;

    always @(posedge clk) begin
        if (~rst_n) begin
            s3buf_vld       <= 1'b0;
            s3buf_reqtype   <= `PRGA_YAMI_REQTYPE_NONE;
            s3buf_size      <= { `PRGA_YAMI_SIZE_WIDTH {1'b0} };
            s3buf_addr      <= { `PRGA_YAMI_FMC_ADDR_WIDTH {1'b0} };
            s3buf_data      <= { `PRGA_YAMI_FMC_DATA_WIDTH {1'b0} };
            s3buf_rob_entry <= { `PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2 {1'b0} };
        end else if (state == ST_S3_BUFFERED) begin
            if (s3buf_vld && dequeue_rpb_s1) begin
                s3buf_vld   <= 1'b0;
            end else if (validate_rpb_s2
                && index_s2 == s3buf_addr[`PRGA_YAMI_CACHE_INDEX_LOW +: `PRGA_YAMI_CACHE_INDEX_WIDTH]
            ) begin
                s3buf_vld   <= 1'b1;
            end
        end else if (enqueue_rpb_s3) begin
            s3buf_vld       <= 1'b0;
            s3buf_reqtype   <= rpb_reqtype_s3;
            s3buf_size      <= rpb_size_s3;
            s3buf_addr      <= rpb_addr_s3;
            s3buf_data      <= rpb_data_s3;
            s3buf_rob_entry <= rpb_rob_entry_s3;
        end
    end

    always @* begin
        state_next = state;

        case (state)
            ST_RST:
                state_next = ST_EMPTY;

            ST_EMPTY:
                state_next = enqueue_rpb_s3 ? ST_S3_BUFFERED : state;

            ST_S3_BUFFERED:
                state_next = !s3buf_vld || !dequeue_rpb_s1 ? state :
                             s2buf_vld ? ST_S2_BUFFERED :
                                         ST_EMPTY;

            ST_S2_BUFFERED:
                state_next = s2buf_vld && dequeue_rpb_s1 ? ST_EMPTY : state;
        endcase
    end

    assign rpb_empty_s1 = state == ST_EMPTY;
    assign rpb_vld_s1 = state == ST_S3_BUFFERED ? s3buf_vld :
                        state == ST_S2_BUFFERED ? s2buf_vld : 1'b0;
    assign rpb_reqtype_s1 = state == ST_S2_BUFFERED ? s2buf_reqtype : s3buf_reqtype;
    assign rpb_size_s1 = state == ST_S2_BUFFERED ? s2buf_size : s3buf_size;
    assign rpb_addr_s1 = state == ST_S2_BUFFERED ? s2buf_addr : s3buf_addr;
    assign rpb_data_s1 = state == ST_S2_BUFFERED ? s2buf_data : s3buf_data;
    assign rpb_rob_entry_vld_s1 = state == ST_S3_BUFFERED;
    assign rpb_rob_entry_s1 = s3buf_rob_entry;

endmodule
