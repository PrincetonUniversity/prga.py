// Automatically generated by PRGA's RTL generator

/*
* Top-level module of prga_yami_pitoncache.
*/

`include "prga_yami.vh"
`include "prga_yami_pitoncache.vh"
`default_nettype none

module prga_yami_pitoncache #(
    parameter   INITIALIZE          = 1     // initialize LRU/tag array
    , parameter USE_INITIAL_BLOCK   = 0     // if set, use `initial` block to initialize the state/LRU/tag array
                                            // this only works when the cache is implemented as a soft cache inside the FPGA
) (
    // -- System Ctrl --------------------------------------------------------
    input wire                                          clk
    , input wire                                        rst_n

    // -- Receive FMC Requests from Accelerator ------------------------------
    , output wire                                       a_fmc_rdy
    , input wire                                        a_fmc_vld
    , input wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]         a_fmc_type
    , input wire [`PRGA_YAMI_SIZE_WIDTH-1:0]            a_fmc_size
    , input wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]        a_fmc_addr
    , input wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]        a_fmc_data

    // -- Send MFC Responses to Accelerator ----------------------------------
    , input wire                                        a_mfc_rdy
    , output wire                                       a_mfc_vld
    , output wire [`PRGA_YAMI_RESPTYPE_WIDTH-1:0]       a_mfc_type
    , output wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]       a_mfc_data

    // -- Send FMC Requests to Memory ----------------------------------------
    , input wire                                        m_fmc_rdy
    , output wire                                       m_fmc_vld
    , output wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]        m_fmc_type
    , output wire [`PRGA_YAMI_SIZE_WIDTH-1:0]           m_fmc_size
    , output wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]       m_fmc_addr
    , output wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]       m_fmc_data
    , output wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]  m_fmc_l1rplway  // this is specific to OpenPiton

    // -- Receive MFC Responses from Memory ----------------------------------
    , output wire                                       m_mfc_rdy
    , input wire                                        m_mfc_vld
    , input wire [`PRGA_YAMI_RESPTYPE_WIDTH-1:0]        m_mfc_type
    , input wire [`PRGA_YAMI_MFC_ADDR_WIDTH-1:0]        m_mfc_addr
    , input wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]        m_mfc_data
    , input wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]   m_mfc_l1invway  // this is specific to OpenPiton
    , input wire                                        m_mfc_l1invall  // this is specific to OpenPiton
    );

    // -- S1 wires --
    wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]             index_s1;
    wire [`PRGA_YAMI_CACHE_S3OP_WIDTH-1:0]              op_s2_next;
    wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]           inv_ilq_way_s2_next;
    wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]                 reqtype_s2_next;
    wire [`PRGA_YAMI_SIZE_WIDTH-1:0]                    size_s2_next;
    wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]                addr_s2_next;
    wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]                data_s2_next;
    wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rob_entry_s2_next;

    // -- S2 wires --
    wire                                                stall_s2;
    wire [`PRGA_YAMI_CACHE_S3OP_WIDTH-1:0]              op_s3_next;
    wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]           inv_ilq_way_s2;
    wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]                 reqtype_s2;
    wire [`PRGA_YAMI_SIZE_WIDTH-1:0]                    size_s2;
    wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]                addr_s2;
    wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]                data_s2;
    wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rob_entry_s2;
    wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]             index_s2;
    wire [`PRGA_YAMI_CACHE_TAG_WIDTH-1:0]               tag_s2;

    // -- S3 wires --
    wire                                                stall_s3;
    wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]             index_s3;
    wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]           way_s3;
    wire [`PRGA_YAMI_CACHE_TAG_WIDTH-1:0]               tag_s3;
    wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rob_entry_s3;

    // -- ROB wires --
    wire                                                rob_next_entry_vld_s1;
    wire                                                rob_alloc_s1;
    wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rob_next_entry_s1;
    wire [`PRGA_YAMI_RESPTYPE_WIDTH-1:0]                rob_alloc_resptype_s1;

    wire                                                rob_fill_s3;
    // wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rob_fill_entry_s3;
    wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]                rob_fill_data_s3;

    // -- RPB wires --
    wire                                                dequeue_rpb_s1;
    wire                                                validate_rpb_s3;

    wire                                                rpb_empty_s1;
    wire                                                rpb_vld_s1;
    wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]                 rpb_reqtype_s1;
    wire [`PRGA_YAMI_SIZE_WIDTH-1:0]                    rpb_size_s1;
    wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]                rpb_addr_s1;
    wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]                rpb_data_s1;
    wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    rpb_rob_entry_s1;

    wire                                                rpb_vld_s2;

    wire                                                enqueue_rpb_s3;
    wire [`PRGA_YAMI_REQTYPE_WIDTH-1:0]                 rpb_reqtype_s3;
    wire [`PRGA_YAMI_SIZE_WIDTH-1:0]                    rpb_size_s3;
    wire [`PRGA_YAMI_FMC_ADDR_WIDTH-1:0]                rpb_addr_s3;
    wire [`PRGA_YAMI_FMC_DATA_WIDTH-1:0]                rpb_data_s3;

    // -- ILQ wires --
    wire                                                ilq_rd_s1;
    wire                                                ilq_full_s1;
    wire                                                ilq_nc_s1;
    wire [`PRGA_YAMI_CACHE_INDEX_WIDTH-1:0]             ilq_index_s1;
    wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]           ilq_way_s1;
    wire [`PRGA_YAMI_CACHE_INDEX_LOW-1:0]               ilq_offset_s1;
    wire [`PRGA_YAMI_SIZE_WIDTH-1:0]                    ilq_size_s1;
    wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    ilq_rob_entry_s1;

    wire                                                ilq_wr_s3;
    wire                                                ilq_nc_s3;
    wire [`PRGA_YAMI_CACHE_INDEX_LOW-1:0]               ilq_offset_s3;
    wire [`PRGA_YAMI_SIZE_WIDTH-1:0]                    ilq_size_s3;

    // -- ISQ wires --
    wire                                                isq_rd_s1;
    wire                                                isq_full_s1;
    wire                                                isq_nc_s1;
    wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    isq_rob_entry_s1;

    wire                                                isq_wr_s3;
    wire                                                isq_nc_s3;

    // -- IMQ wires --
    wire                                                imq_rd_s1;
    wire                                                imq_full_s1;
    wire [`PRGA_YAMI_CACHE_INDEX_LOW-1:0]               imq_offset_s1;
    wire [`PRGA_YAMI_SIZE_WIDTH-1:0]                    imq_size_s1;
    wire [`PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2-1:0]    imq_rob_entry_s1;

    wire                                                imq_wr_s3;
    wire [`PRGA_YAMI_CACHE_INDEX_LOW-1:0]               imq_offset_s3;
    wire [`PRGA_YAMI_SIZE_WIDTH-1:0]                    imq_size_s3;

    // -- state array wires --
    wire                                                state_array_busy_s1;
    wire                                                state_array_rd_s1;

    wire [`PRGA_YAMI_CACHE_NUM_WAYS * `PRGA_YAMI_CACHE_STATE_WIDTH - 1:0]   state_array_rdata_s2;

    wire [`PRGA_YAMI_CACHE_S3OP_SA_WIDTH-1:0]           state_array_op_s3;

    // -- tag array wires --
    wire                                                tag_array_busy_s1;
    wire                                                tag_array_rd_s1;

    wire [`PRGA_YAMI_CACHE_TAG_WIDTH * `PRGA_YAMI_CACHE_NUM_WAYS - 1:0]     tag_array_rdata_s2;

    wire                                                tag_array_wr_s3;

    // -- LRU array wires --
    wire                                                lru_array_busy_s1;
    wire                                                lru_array_rd_s1;

    wire [`PRGA_YAMI_CACHE_LRU_WIDTH * `PRGA_YAMI_CACHE_NUM_WAYS - 1:0]     lru_array_rdata_s2;

    wire                                                lru_array_wr_s3;
    wire [`PRGA_YAMI_CACHE_NUM_WAYS-1:0]                lru_array_inc_mask_s3;
    wire [`PRGA_YAMI_CACHE_NUM_WAYS-1:0]                lru_array_clr_mask_s3;

    // -- data array wires --
    wire                                                data_array_rd_s2;

    wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]                data_array_rdata_s3;

    wire                                                data_array_wr_s3;
    wire [`PRGA_YAMI_MFC_DATA_BYTES-1:0]                data_array_wstrb_s3;
    wire [`PRGA_YAMI_MFC_DATA_WIDTH-1:0]                data_array_wdata_s3;

    // -- way logic wires --
    wire                                                hit_s3;
    wire [`PRGA_YAMI_CACHE_NUM_WAYS_LOG2-1:0]           hit_rpl_way_s3;
    wire                                                iv_s3;

    // -- instances --
    prga_yami_pitoncache_pipeline_s1 i_s1 (
        .clk                    (clk)
        ,.rst_n                 (rst_n)

        ,.a_fmc_rdy             (a_fmc_rdy)
        ,.a_fmc_vld             (a_fmc_vld)
        ,.a_fmc_type            (a_fmc_type)
        ,.a_fmc_size            (a_fmc_size)
        ,.a_fmc_addr            (a_fmc_addr)
        ,.a_fmc_data            (a_fmc_data)

        ,.m_mfc_rdy             (m_mfc_rdy)
        ,.m_mfc_vld             (m_mfc_vld)
        ,.m_mfc_type            (m_mfc_type)
        ,.m_mfc_addr            (m_mfc_addr)
        ,.m_mfc_data            (m_mfc_data)
        ,.m_mfc_inval_way       (m_mfc_l1invway)
        ,.m_mfc_inval_all       (m_mfc_l1invall)

        ,.rob_next_entry_vld_s1 (rob_next_entry_vld_s1)
        ,.rob_next_entry_s1     (rob_next_entry_s1)
        ,.rob_alloc_s1          (rob_alloc_s1)
        ,.rob_alloc_resptype_s1 (rob_alloc_resptype_s1)

        ,.ilq_rd_s1             (ilq_rd_s1)
        ,.ilq_full_s1           (ilq_full_s1)
        ,.ilq_nc_s1             (ilq_nc_s1)
        ,.ilq_index_s1          (ilq_index_s1)
        ,.ilq_way_s1            (ilq_way_s1)
        ,.ilq_offset_s1         (ilq_offset_s1)
        ,.ilq_size_s1           (ilq_size_s1)
        ,.ilq_rob_entry_s1      (ilq_rob_entry_s1)

        ,.isq_rd_s1             (isq_rd_s1)
        ,.isq_full_s1           (isq_full_s1)
        ,.isq_nc_s1             (isq_nc_s1)
        ,.isq_rob_entry_s1      (isq_rob_entry_s1)

        ,.imq_rd_s1             (imq_rd_s1)
        ,.imq_full_s1           (imq_full_s1)
        ,.imq_offset_s1         (imq_offset_s1)
        ,.imq_size_s1           (imq_size_s1)
        ,.imq_rob_entry_s1      (imq_rob_entry_s1)

        ,.lru_array_busy_s1     (lru_array_busy_s1)
        ,.tag_array_busy_s1     (tag_array_busy_s1)
        ,.state_array_busy_s1   (state_array_busy_s1)

        ,.index_s1              (index_s1)
        ,.lru_array_rd_s1       (lru_array_rd_s1)
        ,.tag_array_rd_s1       (tag_array_rd_s1)
        ,.state_array_rd_s1     (state_array_rd_s1)

        ,.stall_s2              (stall_s2)
        ,.op_s2_next            (op_s2_next)
        ,.inv_ilq_way_s2_next   (inv_ilq_way_s2_next)
        ,.reqtype_s2_next       (reqtype_s2_next)
        ,.size_s2_next          (size_s2_next)
        ,.addr_s2_next          (addr_s2_next)
        ,.data_s2_next          (data_s2_next)
        ,.rob_entry_s2_next     (rob_entry_s2_next)
        ,.enqueue_rpb_s3        (enqueue_rpb_s3)
        ,.dequeue_rpb_s1        (dequeue_rpb_s1)
        ,.rpb_empty_s1          (rpb_empty_s1)
        ,.rpb_vld_s1            (rpb_vld_s1)
        ,.rpb_reqtype_s1        (rpb_reqtype_s1)
        ,.rpb_size_s1           (rpb_size_s1)
        ,.rpb_addr_s1           (rpb_addr_s1)
        ,.rpb_data_s1           (rpb_data_s1)
        ,.rpb_rob_entry_s1      (rpb_rob_entry_s1)
        );

    prga_yami_pitoncache_pipeline_s2 i_s2 (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.stall_s2              (stall_s2)
        ,.op_s2_next            (op_s2_next)
        ,.inv_ilq_way_s2_next   (inv_ilq_way_s2_next)
        ,.reqtype_s2_next       (reqtype_s2_next)
        ,.size_s2_next          (size_s2_next)
        ,.addr_s2_next          (addr_s2_next)
        ,.data_s2_next          (data_s2_next)
        ,.rob_entry_s2_next     (rob_entry_s2_next)
        ,.stall_s3              (stall_s3)
        ,.enqueue_rpb_s3        (enqueue_rpb_s3)
        ,.op_s3_next            (op_s3_next)
        ,.inv_ilq_way_s2        (inv_ilq_way_s2)
        ,.reqtype_s2            (reqtype_s2)
        ,.size_s2               (size_s2)
        ,.addr_s2               (addr_s2)
        ,.data_s2               (data_s2)
        ,.rob_entry_s2          (rob_entry_s2)
        ,.rpb_vld_s2            (rpb_vld_s2)
        ,.data_array_rd_s2      (data_array_rd_s2)
        ,.index_s2              (index_s2)
        ,.tag_s2                (tag_s2)
        );

    prga_yami_pitoncache_pipeline_s3 i_s3 (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.stall_s3              (stall_s3)
        ,.index_s3              (index_s3)
        ,.way_s3                (way_s3)
        ,.rob_entry_s3          (rob_entry_s3)
        ,.op_s3_next            (op_s3_next)
        ,.inv_ilq_way_s3_next   (inv_ilq_way_s2)
        ,.reqtype_s3_next       (reqtype_s2)
        ,.size_s3_next          (size_s2)
        ,.addr_s3_next          (addr_s2)
        ,.data_s3_next          (data_s2)
        ,.rob_entry_s3_next     (rob_entry_s2)
        ,.state_array_op_s3     (state_array_op_s3)
        ,.tag_array_wr_s3       (tag_array_wr_s3)
        ,.tag_s3                (tag_s3)
        ,.lru_array_wr_s3       (lru_array_wr_s3)
        ,.data_array_rdata_s3   (data_array_rdata_s3)
        ,.data_array_wr_s3      (data_array_wr_s3)
        ,.data_array_wstrb_s3   (data_array_wstrb_s3)
        ,.data_array_wdata_s3   (data_array_wdata_s3)
        ,.rob_fill_s3           (rob_fill_s3)
        ,.rob_fill_data_s3      (rob_fill_data_s3)
        ,.hit_s3                (hit_s3)
        ,.iv_s3                 (iv_s3)
        ,.hit_rpl_way_s3        (hit_rpl_way_s3)
        ,.enqueue_rpb_s3        (enqueue_rpb_s3)
        ,.validate_rpb_s3       (validate_rpb_s3)
        ,.rpb_reqtype_s3        (rpb_reqtype_s3)
        ,.rpb_size_s3           (rpb_size_s3)
        ,.rpb_addr_s3           (rpb_addr_s3)
        ,.rpb_data_s3           (rpb_data_s3)
        ,.ilq_wr_s3             (ilq_wr_s3)
        ,.ilq_nc_s3             (ilq_nc_s3)
        ,.ilq_offset_s3         (ilq_offset_s3)
        ,.ilq_size_s3           (ilq_size_s3)
        ,.isq_wr_s3             (isq_wr_s3)
        ,.isq_nc_s3             (isq_nc_s3)
        ,.imq_wr_s3             (imq_wr_s3)
        ,.imq_offset_s3         (imq_offset_s3)
        ,.imq_size_s3           (imq_size_s3)
        ,.m_fmc_rdy             (m_fmc_rdy)
        ,.m_fmc_vld             (m_fmc_vld)
        ,.m_fmc_type            (m_fmc_type)
        ,.m_fmc_size            (m_fmc_size)
        ,.m_fmc_addr            (m_fmc_addr)
        ,.m_fmc_data            (m_fmc_data)
        ,.m_fmc_rpl_way         (m_fmc_l1rplway)
        );

    prga_yami_pitoncache_rob i_rob (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.mfc_rdy               (a_mfc_rdy)
        ,.mfc_vld               (a_mfc_vld)
        ,.mfc_type              (a_mfc_type)
        ,.mfc_data              (a_mfc_data)
        ,.next_entry_vld_s1     (rob_next_entry_vld_s1)
        ,.next_entry_s1         (rob_next_entry_s1)
        ,.alloc_s1              (rob_alloc_s1)
        ,.alloc_resptype_s1     (rob_alloc_resptype_s1)
        ,.fill_s3               (rob_fill_s3)
        ,.fill_entry_s3         (rob_entry_s3)
        ,.fill_data_s3          (rob_fill_data_s3)
        );

    prga_yami_pitoncache_fifo #(
        .DEPTH_LOG2     (3)
        ,.DATA_WIDTH    (1
            + `PRGA_YAMI_CACHE_INDEX_WIDTH
            + `PRGA_YAMI_CACHE_NUM_WAYS_LOG2
            + `PRGA_YAMI_CACHE_INDEX_LOW
            + `PRGA_YAMI_SIZE_WIDTH
            + `PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2
        )
        ,.LOOKAHEAD     (1)
        ,.RESERVATIONS  (1)
    ) i_ilq (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.full                  (ilq_full_s1)
        ,.wr                    (ilq_wr_s3)
        ,.din                   ({
            ilq_nc_s3
            , index_s3
            , way_s3
            , ilq_offset_s3
            , ilq_size_s3
            , rob_entry_s3
        })
        ,.empty                 ()
        ,.rd                    (ilq_rd_s1)
        ,.dout                  ({
            ilq_nc_s1
            , ilq_index_s1
            , ilq_way_s1
            , ilq_offset_s1
            , ilq_size_s1
            , ilq_rob_entry_s1
        })
        );

    prga_yami_pitoncache_fifo #(
        .DEPTH_LOG2     (3)
        ,.DATA_WIDTH    (1
            + `PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2
        )
        ,.LOOKAHEAD     (1)
        ,.RESERVATIONS  (1)
    ) i_isq (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.full                  (isq_full_s1)
        ,.wr                    (isq_wr_s3)
        ,.din                   ({
            isq_nc_s3
            , rob_entry_s3
        })
        ,.empty                 ()
        ,.rd                    (isq_rd_s1)
        ,.dout                  ({
            isq_nc_s1
            , isq_rob_entry_s1
        })
        );

    prga_yami_pitoncache_fifo #(
        .DEPTH_LOG2     (3)
        ,.DATA_WIDTH    (
            `PRGA_YAMI_CACHE_INDEX_LOW
            + `PRGA_YAMI_SIZE_WIDTH
            + `PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2
        )
        ,.LOOKAHEAD     (1)
        ,.RESERVATIONS  (1)
    ) i_imq (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.full                  (imq_full_s1)
        ,.wr                    (imq_wr_s3)
        ,.din                   ({
            imq_offset_s3
            , imq_size_s3
            , rob_entry_s3
        })
        ,.empty                 ()
        ,.rd                    (imq_rd_s1)
        ,.dout                  ({
            imq_offset_s1
            , imq_size_s1
            , imq_rob_entry_s1
        })
        );

    prga_yami_pitoncache_state_array i_state_array (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.busy_s1               (state_array_busy_s1)
        ,.rd_s1                 (state_array_rd_s1)
        ,.index_s1              (index_s1)
        ,.rdata_s2              (state_array_rdata_s2)
        ,.stall_s3              (stall_s3)
        ,.index_s3              (index_s3)
        ,.op_s3                 (state_array_op_s3)
        ,.way_s3                (way_s3)
        );

    prga_yami_pitoncache_tag_array i_tag_array (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.busy_s1               (tag_array_busy_s1)
        ,.rd_s1                 (tag_array_rd_s1)
        ,.index_s1              (index_s1)
        ,.rdata_s2              (tag_array_rdata_s2)
        ,.stall_s3              (stall_s3)
        ,.index_s3              (index_s3)
        ,.way_s3                (way_s3)
        ,.wr_s3                 (tag_array_wr_s3)
        ,.wdata_s3              (tag_s3)
        );

    prga_yami_pitoncache_lru_array i_lru_array (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.busy_s1               (lru_array_busy_s1)
        ,.rd_s1                 (lru_array_rd_s1)
        ,.index_s1              (index_s1)
        ,.rdata_s2              (lru_array_rdata_s2)
        ,.stall_s3              (stall_s3)
        ,.index_s3              (index_s3)
        ,.wr_s3                 (lru_array_wr_s3)
        ,.inc_mask_s3           (lru_array_inc_mask_s3)
        ,.clr_mask_s3           (lru_array_clr_mask_s3)
        );

    prga_yami_pitoncache_data_array i_data_array (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.rd_s2                 (data_array_rd_s2)
        ,.index_s2              (index_s2)
        ,.rdata_s3              (data_array_rdata_s3)
        ,.index_s3              (index_s3)
        ,.way_s3                (way_s3)
        ,.wr_s3                 (data_array_wr_s3)
        ,.wstrb_s3              (data_array_wstrb_s3)
        ,.wdata_s3              (data_array_wdata_s3)
        );

    prga_yami_pitoncache_rpb i_rpb (
        .clk                    (clk)
        ,.rst_n                 (rst_n)

        ,.rpb_vld_s2            (rpb_vld_s2)
        ,.rpb_reqtype_s2        (reqtype_s2)
        ,.rpb_size_s2           (size_s2)
        ,.rpb_addr_s2           (addr_s2)
        ,.rpb_data_s2           (data_s2[0 +: `PRGA_YAMI_FMC_DATA_WIDTH])
        ,.rpb_rob_entry_s2      (rob_entry_s2)

        ,.enqueue_rpb_s3        (enqueue_rpb_s3)
        ,.rpb_reqtype_s3        (rpb_reqtype_s3)
        ,.rpb_size_s3           (rpb_size_s3)
        ,.rpb_addr_s3           (rpb_addr_s3)
        ,.rpb_data_s3           (rpb_data_s3)
        ,.rpb_rob_entry_s3      (rob_entry_s3)

        ,.validate_rpb_s3       (validate_rpb_s3)
        ,.index_s3              (index_s3)
        ,.dequeue_rpb_s1        (dequeue_rpb_s1)
        ,.rpb_empty_s1          (rpb_empty_s1)
        ,.rpb_vld_s1            (rpb_vld_s1)
        ,.rpb_reqtype_s1        (rpb_reqtype_s1)
        ,.rpb_size_s1           (rpb_size_s1)
        ,.rpb_addr_s1           (rpb_addr_s1)
        ,.rpb_data_s1           (rpb_data_s1)
        ,.rpb_rob_entry_s1      (rpb_rob_entry_s1)
        );

    prga_yami_pitoncache_way_logic i_way_logic (
        .clk                    (clk)
        ,.rst_n                 (rst_n)
        ,.stateline_s2          (state_array_rdata_s2)
        ,.tagline_s2            (tag_array_rdata_s2)
        ,.lruline_s2            (lru_array_rdata_s2)
        ,.tag_s2                (tag_s2)
        ,.stall_s3              (stall_s3)
        ,.hit_s3                (hit_s3)
        ,.way_s3                (hit_rpl_way_s3)
        ,.iv_s3                 (iv_s3)
        ,.lru_inc_mask_s3       (lru_array_inc_mask_s3)
        ,.lru_clr_mask_s3       (lru_array_clr_mask_s3)
        );

endmodule
