`ifndef PRGA_YAMI_PITONCACHE_VH
`define PRGA_YAMI_PITONCACHE_VH

`include "prga_yami.vh"

    // 4-way associative
// `define PRGA_YAMI_CACHE_NUM_WAYS_LOG2   2
// `define PRGA_YAMI_CACHE_NUM_WAYS        (1 << `PRGA_YAMI_CACHE_NUM_WAYS_LOG2)

    // 7-bit index (8KB = 128 x 4(#ways) x 16B(cacheline size))
`define PRGA_YAMI_CACHE_INDEX_LOW       `PRGA_YAMI_CACHELINE_BYTES_LOG2 // 16B cacheline
`define PRGA_YAMI_CACHE_INDEX_WIDTH     7

    // LRU counter: 0 (youngest) -> 3 (oldest) 
`define PRGA_YAMI_CACHE_LRU_WIDTH       2

    // tag
`define PRGA_YAMI_CACHE_TAG_LOW         (`PRGA_YAMI_CACHE_INDEX_LOW + `PRGA_YAMI_CACHE_INDEX_WIDTH)
`define PRGA_YAMI_CACHE_TAG_WIDTH       (`PRGA_YAMI_FMC_ADDR_WIDTH - `PRGA_YAMI_CACHE_TAG_LOW + 1)

// ===========================================================================
// == Response ReOrder Buffer ================================================
// ===========================================================================
`define PRGA_YAMI_CACHE_ROB_NUM_ENTRIES_LOG2    3   // 8 in-flight transactions

// ===========================================================================
// == State Array ============================================================
// ===========================================================================
    // cacheline state
`define PRGA_YAMI_CACHE_STATE_WIDTH     2
`define PRGA_YAMI_CACHE_STATE_I         `PRGA_YAMI_CACHE_STATE_WIDTH'b00    // invalid
`define PRGA_YAMI_CACHE_STATE_V         `PRGA_YAMI_CACHE_STATE_WIDTH'b01    // valid
`define PRGA_YAMI_CACHE_STATE_IV        `PRGA_YAMI_CACHE_STATE_WIDTH'b10    // un-ack'ed cache fill

    // State Array Operation: Stage III
`define PRGA_YAMI_CACHE_S3OP_SA_WIDTH               3
`define PRGA_YAMI_CACHE_S3OP_SA_NONE                3'd0
`define PRGA_YAMI_CACHE_S3OP_SA_TRANSITION_TO_IV    3'd4    // transition one way from I or V to IV
`define PRGA_YAMI_CACHE_S3OP_SA_TRANSITION_TO_V     3'd5    // transition one way from IV to V
`define PRGA_YAMI_CACHE_S3OP_SA_INVAL_WAY           3'd6    // invalidate one way (transition from V or IV to I)
`define PRGA_YAMI_CACHE_S3OP_SA_INVAL_ALL           3'd7    // invalidate all ways

// ===========================================================================
// == Main Pipeline, Stage II ================================================
// ===========================================================================
`define PRGA_YAMI_CACHE_S2OP_WIDTH              3
`define PRGA_YAMI_CACHE_S2OP_NONE               3'h0
`define PRGA_YAMI_CACHE_S2OP_APP_REQ            3'h1
`define PRGA_YAMI_CACHE_S2OP_INV_WAY            3'h2
`define PRGA_YAMI_CACHE_S2OP_INV_ALL            3'h3
`define PRGA_YAMI_CACHE_S2OP_LD_ACK             3'h4
`define PRGA_YAMI_CACHE_S2OP_ST_ACK             3'h5
`define PRGA_YAMI_CACHE_S2OP_AMO_ACK            3'h6
`define PRGA_YAMI_CACHE_S2OP_REPLAY_REQ         3'h7

// ===========================================================================
// == Main Pipeline, Stage III ===============================================
// ===========================================================================
`define PRGA_YAMI_CACHE_S3OP_WIDTH              3
`define PRGA_YAMI_CACHE_S3OP_NONE               3'h0
`define PRGA_YAMI_CACHE_S3OP_APP_REQ            3'h1
`define PRGA_YAMI_CACHE_S3OP_INV_WAY            3'h2
`define PRGA_YAMI_CACHE_S3OP_INV_ALL            3'h3
`define PRGA_YAMI_CACHE_S3OP_LD_ACK             3'h4
`define PRGA_YAMI_CACHE_S3OP_LD_NC_ACK          3'h5
`define PRGA_YAMI_CACHE_S3OP_ST_NC_ACK          3'h6
`define PRGA_YAMI_CACHE_S3OP_AMO_ACK            3'h7

`endif /* `ifndef PRGA_YAMI_PITONCACHE_VH */
