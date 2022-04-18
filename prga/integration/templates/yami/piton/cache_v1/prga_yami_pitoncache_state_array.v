// Automatically generated by PRGA's RTL generator

/*
* State array for prga_yami_pitoncache.
*/

`include "prga_yami.vh"
`include "prga_yami_pitoncache.vh"
`default_nettype none

module prga_yami_pitoncache_state_array #(
    parameter   USE_INITIAL_BLOCK   = 0     // if set, use `initial` block to initialize the state array
                                            // this only works when the cache is implemented as a soft cache inside the FPGA
) (
    // -- System Ctrl --------------------------------------------------------
    input wire                                          clk
    , input wire                                        rst_n

    // -- Stage I ------------------------------------------------------------
    , output wire                                       busy_s1
    , input wire                                        rd_s1
    , input wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]     index_s1

    // -- Stage II -----------------------------------------------------------
    , output wire [`PRGA_YAMI_CACHE_NUM_WAYS * `PRGA_YAMI_CACHE_STATE_WIDTH-1:0] rdata_s2

    // -- Stage III ----------------------------------------------------------
    , input wire                                        stall_s3
    , input wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]     index_s3
    , input wire [`PRGA_YAMI_CACHE_S3OP_SA_WIDTH-1:0]   op_s3
    , input wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]   way_s3
    );

    localparam  LINE_WIDTH  = `PRGA_YAMI_CACHE_NUM_WAYS * `PRGA_YAMI_CACHE_STATE_WIDTH;

    // -- State Array Memory --
    reg                                     we;
    reg [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]  waddr, raddr_f;
    wire [LINE_WIDTH-1:0]                   din, dout;
    reg [LINE_WIDTH-1:0]                    rdata_s3;

    prga_yami_pitoncache_ram_raw #(
        .ADDR_WIDTH     (`PRGA_YAMI_CACHE_INDEX_WIDTH)
        ,.DATA_WIDTH    (LINE_WIDTH)
        ,.INITIALIZE    (USE_INITIAL_BLOCK)
    ) i_mem (
        .clk        (clk)
        ,.rst_n     (rst_n)
        ,.we        (we)
        ,.waddr     (waddr) // @(posedge clk) index_s3 <= index_s2; index_s2 <= index_s1;
        ,.d         (din)
        ,.re        (rd_s1)
        ,.raddr     (index_s1)
        ,.q         (dout)
        );

    always @(posedge clk) begin
        if (~rst_n) begin
            raddr_f         <= { `PRGA_YAMI_CACHE_INDEX_WIDTH {1'b0} };
            rdata_s3        <= { LINE_WIDTH {1'b0} };
        end else begin
            raddr_f         <= index_s1;

            if (!stall_s3)
                rdata_s3    <= rdata_s2;
        end
    end

    assign rdata_s2 = we && raddr_f == index_s3 ? din : dout;

    // -- Initailization --
    wire                                    we_init;
    wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0] init_index;

    generate
        if (USE_INITIAL_BLOCK) begin
            assign busy_s1 = 1'b0;
            assign we_init = 1'b0;
            assign init_index = { `PRGA_YAMI_CACHE_INDEX_WIDTH {1'b0} };

        end else begin
            // -- FSM (for initialization) --
            localparam  ST_WIDTH    = 2;
            localparam  ST_RST      = 2'd0,
                        ST_INIT     = 2'd1,
                        ST_READY    = 2'd2;

            reg [ST_WIDTH-1:0]                      state, state_next;
            reg [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]  init_index_tmp;

            always @(posedge clk) begin
                if (~rst_n) begin
                    init_index_tmp <= { `PRGA_YAMI_CACHE_INDEX_WIDTH {1'b0} };
                end else if (state == ST_INIT) begin
                    init_index_tmp <= init_index_tmp + 1;
                end
            end

            always @(posedge clk) begin
                if (~rst_n) begin
                    state <= ST_RST;
                end else begin
                    state <= state_next;
                end
            end

            always @* begin
                state_next = state;

                case (state)
                    ST_RST:     state_next = ST_INIT;
                    ST_INIT:    state_next = &init_index_tmp ? ST_READY : ST_INIT;
                endcase
            end

            assign busy_s1 = state != ST_READY;
            assign we_init = state == ST_INIT;
            assign init_index = init_index_tmp;
        end
    endgenerate

    // -- Stage III --
    always @* begin
        if (we_init) begin
            we = 1'b1;
            waddr = init_index;

        end else begin
            waddr = index_s3;

            case (op_s3)
                `PRGA_YAMI_CACHE_S3OP_SA_TRANSITION_TO_IV,
                `PRGA_YAMI_CACHE_S3OP_SA_TRANSITION_TO_V,
                `PRGA_YAMI_CACHE_S3OP_SA_INVAL_WAY,
                `PRGA_YAMI_CACHE_S3OP_SA_INVAL_ALL:
                    we = 1'b1;
                default:
                    we = 1'b0;
            endcase
        end
    end

    genvar gv_way;
    generate
        for (gv_way = 0; gv_way < `PRGA_YAMI_CACHE_NUM_WAYS; gv_way = gv_way + 1) begin: g_way
            reg [`PRGA_YAMI_CACHE_STATE_WIDTH-1:0]  din_tmp;

            always @* begin
                din_tmp = rdata_s3[`PRGA_YAMI_CACHE_STATE_WIDTH * gv_way +: `PRGA_YAMI_CACHE_STATE_WIDTH];

                if (we_init) begin
                    din_tmp = `PRGA_YAMI_CACHE_STATE_I;

                end else begin
                    case (op_s3)
                        `PRGA_YAMI_CACHE_S3OP_SA_TRANSITION_TO_IV:
                            if (gv_way == way_s3)
                                din_tmp = `PRGA_YAMI_CACHE_STATE_IV;
                        `PRGA_YAMI_CACHE_S3OP_SA_TRANSITION_TO_V:
                            if (gv_way == way_s3)
                                din_tmp = `PRGA_YAMI_CACHE_STATE_V;
                        `PRGA_YAMI_CACHE_S3OP_SA_INVAL_WAY:
                            if (gv_way == way_s3)
                                din_tmp = `PRGA_YAMI_CACHE_STATE_I;
                        `PRGA_YAMI_CACHE_S3OP_SA_INVAL_ALL:
                            din_tmp = `PRGA_YAMI_CACHE_STATE_I;
                    endcase

                end
            end

            assign din[`PRGA_YAMI_CACHE_STATE_WIDTH * gv_way +: `PRGA_YAMI_CACHE_STATE_WIDTH] = din_tmp;
        end
    endgenerate

endmodule
