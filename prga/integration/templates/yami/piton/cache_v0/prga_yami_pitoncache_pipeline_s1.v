// Automatically generated by PRGA's RTL generator

/*
* Main pipeline, stage I for prga_yami_pitoncache.
*/

`include "prga_yami.vh"
`include "prga_yami_pitoncache.vh"
`default_nettype none

module prga_yami_pitoncache_pipeline_s1 (
    // -- System Ctrl --------------------------------------------------------
    input wire                                          clk
    , input wire                                        rst_n

    // -- Receive FMC Requests from Accelerator ------------------------------
    , output reg                                        a_fmc_rdy
    , input wire                                        a_fmc_vld
    , input wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]         a_fmc_type
    , input wire [`PRGA_YAMI_SIZE_WIDTH-1:0]            a_fmc_size
    , input wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]        a_fmc_addr
    , input wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]        a_fmc_data

    // -- Receive MFC Responses from Memory ----------------------------------
    , output reg                                        m_mfc_rdy
    , input wire                                        m_mfc_vld
    , input wire [`PRGA_YAMI_RESPTYPE_WIDTH-1:0]        m_mfc_type
    , input wire [`PRGA_YAMI_MFC_ADDR_WIDTH-1:0]        m_mfc_addr
    , input wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]        m_mfc_data
    , input wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]   m_mfc_inval_way // this is specific to OpenPiton
    , input wire                                        m_mfc_inval_all // this is specific to OpenPiton

    // -- To Stage II --------------------------------------------------------
    , input wire                                        stall_s2
    , output reg [`PRGA_YAMI_CACHE_S2OP_WIDTH-1:0]      op_s2_next
    , output reg [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]   inv_way_s2_next
    , output reg [`PRGA_YAMI_REQTYPE_WIDTH-1:0]         reqtype_s2_next
    , output reg [`PRGA_YAMI_SIZE_WIDTH-1:0]            size_s2_next
    , output reg [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]        addr_s2_next
    , output reg [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]        data_s2_next
    , output reg [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rpb_rob_entry_s2_next

    // -- From Stage III -----------------------------------------------------
    , input wire                                        enqueue_rpb_s3

    // -- From RPB -----------------------------------------------------------
    , output reg                                        dequeue_rpb_s1
    , input wire                                        rpb_empty_s1
    , input wire                                        rpb_vld_s1
    , input wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]         rpb_reqtype_s1
    , input wire [`PRGA_YAMI_SIZE_WIDTH-1:0]            rpb_size_s1
    , input wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]        rpb_addr_s1
    , input wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]        rpb_data_s1
    , input wire                                                rpb_rob_entry_vld_s1
    , input wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rpb_rob_entry_s1

    // -- From ILQ/ISQ/IMQ ---------------------------------------------------
    , input wire                                        ilq_full_s1
    , input wire                                        isq_full_s1
    , input wire                                        imq_full_s1
    );

    always @* begin
        a_fmc_rdy       = 1'b0;
        m_mfc_rdy       = 1'b0;
        dequeue_rpb_s1  = 1'b0;

        op_s2_next      = `PRGA_YAMI_CACHE_S2OP_NONE;
        inv_way_s2_next = m_mfc_inval_way;
        reqtype_s2_next = a_fmc_type;
        size_s2_next    = a_fmc_size;
        addr_s2_next    = { `PRGA_YAMI_FMC_ADDR_WIDTH {1'b0} };
        data_s2_next    = { `PRGA_YAMI_MFC_DATA_WIDTH {1'b0} };
        rpb_rob_entry_s2_next   = rpb_rob_entry_s1;

        if (!stall_s2) begin
            // prioritize MFC responses over RPB over FMC Requests
            m_mfc_rdy   = 1'b1;

            if (m_mfc_vld) begin
                addr_s2_next[`PRGA_YAMI_CACHE_INDEX_LOW +: `PRGA_YAMI_CACHE_INDEX_WIDTH] = m_mfc_addr;
                data_s2_next = m_mfc_data;

                case (m_mfc_type)
                    `PRGA_YAMI_RESPTYPE_LOAD_ACK: begin
                        op_s2_next = `PRGA_YAMI_CACHE_S2OP_LD_ACK;
                    end

                    `PRGA_YAMI_RESPTYPE_STORE_ACK: begin
                        op_s2_next = `PRGA_YAMI_CACHE_S2OP_ST_ACK;
                    end

                    `PRGA_YAMI_RESPTYPE_AMO_ACK: begin
                        op_s2_next = `PRGA_YAMI_CACHE_S2OP_AMO_ACK;
                    end

                    `PRGA_YAMI_RESPTYPE_CACHE_INV: begin
                        op_s2_next = m_mfc_inval_all ? `PRGA_YAMI_CACHE_S2OP_INV_ALL :
                                                       `PRGA_YAMI_CACHE_S2OP_INV_WAY;
                    end
                endcase
            end

            // RPB?
            else if (!rpb_empty_s1) begin
                dequeue_rpb_s1  = 1'b1;
                op_s2_next      = !rpb_vld_s1 ? `PRGA_YAMI_CACHE_S2OP_NONE :
                                  rpb_rob_entry_vld_s1 ? `PRGA_YAMI_CACHE_S2OP_REPLAY_REQ :
                                                         `PRGA_YAMI_CACHE_S2OP_APP_REQ;
                reqtype_s2_next = rpb_reqtype_s1;
                size_s2_next    = rpb_size_s1;
                addr_s2_next    = rpb_addr_s1;
                data_s2_next    = {2{rpb_data_s1}};
            end

            // a_fmc
            else if (!enqueue_rpb_s3) begin
                a_fmc_rdy       = 1'b1;

                reqtype_s2_next = a_fmc_type;
                size_s2_next    = a_fmc_size;
                addr_s2_next    = a_fmc_addr;
                data_s2_next    = {2{a_fmc_data}};

                case (a_fmc_type)
                    `PRGA_YAMI_REQTYPE_LOAD,
                    `PRGA_YAMI_REQTYPE_LOAD_NC: if (a_fmc_vld && !ilq_full_s1) begin
                        op_s2_next = `PRGA_YAMI_CACHE_S2OP_APP_REQ;
                    end

                    `PRGA_YAMI_REQTYPE_STORE,
                    `PRGA_YAMI_REQTYPE_STORE_NC: if (a_fmc_vld && !isq_full_s1) begin
                        op_s2_next = `PRGA_YAMI_CACHE_S2OP_APP_REQ;
                    end

                    `PRGA_YAMI_REQTYPE_AMO_LR,
                    `PRGA_YAMI_REQTYPE_AMO_SC,
                    `PRGA_YAMI_REQTYPE_AMO_SWAP,
                    `PRGA_YAMI_REQTYPE_AMO_ADD,
                    `PRGA_YAMI_REQTYPE_AMO_AND,
                    `PRGA_YAMI_REQTYPE_AMO_OR,
                    `PRGA_YAMI_REQTYPE_AMO_XOR,
                    `PRGA_YAMI_REQTYPE_AMO_MAX,
                    `PRGA_YAMI_REQTYPE_AMO_MAXU,
                    `PRGA_YAMI_REQTYPE_AMO_MIN,
                    `PRGA_YAMI_REQTYPE_AMO_MINU: if (a_fmc_vld && !imq_full_s1) begin
                        op_s2_next = `PRGA_YAMI_CACHE_S2OP_APP_REQ;
                    end

                endcase
            end
        end
    end

endmodule
