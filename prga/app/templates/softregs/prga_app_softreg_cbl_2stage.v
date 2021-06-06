// Automatically generated by PRGA's RTL generator
module prga_app_softreg_cbl_2stage #(
    parameter   DATA_WIDTH  = 1
    , parameter RSTVAL = 1'b0
    , parameter OPT_THRUPUT = 0     // optimize throughput (use feedthrough control)
) (
    input wire                          clk
    , input wire                        rst_n

    // -- system-side --------------------------------------------------------
    // -- request --
    , output wire                       req_rdy
    , input wire                        req_vld
    , input wire                        req_we
    , input wire [DATA_WIDTH - 1:0]     req_wmask
    , input wire [DATA_WIDTH - 1:0]     req_data

    // -- response --
    , input wire                        resp_rdy
    , output reg                        resp_vld
    , output wire [DATA_WIDTH - 1:0]    resp_data

    // -- kernel-side --------------------------------------------------------
    , output reg [DATA_WIDTH - 1:0]     var_o
    , input wire                        var_ack
    , input wire                        var_done
    );

    reg var_done_pending;

    always @(posedge clk) begin
        if (~rst_n) begin
            var_o <= RSTVAL;
        end else if (req_rdy && req_vld && !req_we) begin
            var_o <= ~RSTVAL;
        end else if (var_ack) begin
            var_o <= RSTVAL;
        end
    end

    always @(posedge clk) begin
        if (~rst_n) begin
            var_done_pending <= 1'b0;
        end else if (var_done) begin
            var_done_pending <= 1'b0;
        end else if (var_ack) begin
            var_done_pending <= 1'b1;
        end
    end

    always @(posedge clk) begin
        if (~rst_n) begin
            resp_vld <= 1'b0;
        end else if ((req_rdy && req_vld && req_we) || var_done) begin
            resp_vld <= 1'b1;
        end else if (resp_rdy) begin
            resp_vld <= 1'b0;
        end
    end

    assign resp_data = RSTVAL;

    generate if (OPT_THRUPUT) begin
        assign req_rdy = var_o == RSTVAL && !var_done_pending && (!resp_vld || resp_rdy);
    end else begin
        // low throughput, but simpler design, lower resource consumption, and
        // better timing
        assign req_rdy = var_o == RSTVAL && !var_done_pending && !resp_vld;
    end endgenerate
endmodule