/*
* ============================================================================
* ==== PRGA YAMI* (Yet-Another-Memory-Interface) =============================
* ============================================================================
*
* -----------------------
*   * pronounced as "yummy"
*
* Introduction
* ------------
*
*   YAMI is a memory interface for PRGA-based eFPGAs.
*
*   Each YAMI implementation consists of four (4) channels:
*       - One Fabric-Memory-Request (FMC/R) channel: similar to AXI4 AR/AW channel
*       - One Fabric-Memory-Data (FMC/D) channel: similar to AXI4 W channel
*       - One Memory-Fabric-Response (MFC/R) channel: similar to AXI4 B/R channel
*       - One Memory-Fabric-Data (MFC/D) channel: similar to AXI R channel
*
*   Each channel employs a valid-ready handshake (valid and ready must be
*   combinationally independent on the memory side, thus tolerating
*   combinational dependency inside the fabric).
*
*   Each YAMI implementation may support only a subset of YAMI's transactions.
*   For example, we may see load-only YAMI, store-only YAMI, etc. This is
*   similar to only having AXI4 AR+R, or only having AXI4 AW+W+B.
*
* Parameterization
* ----------------
*
*   * THREAD_WIDTH:
*
*   * FMC_ADDR_WIDTH: address width (increment in bytes)
*   * FMC_DATA_BYTES: #Bytes of the FMC data bus. Valid values: 4, 8
*
*   * MFC_ADDR_WIDTH: invalidation address
*   * MFC_DATA_BYTES: #Bytes of the MFC data bus. Valid values: 4, 8, 16, 32,
*                       64. Must be greater than or equal to `FMC_DATA_BYTES`.
*                       May be greater than FMC_DATA_BYTES so as to support
*                       in-fabric cache (L1 cache)
*
*   THREAD_WIDTH + FMC_ADDR_WIDTH must be equal to or less than 47 
*
* Transaction Types
* -----------------
*
*   FMC (request) types: 6bits
*
*     - Available to the fabric:
*       - LOAD: (non-)cacheable, streaming/repetitive
*       - STORE: (non-)cacheable, streaming/repetitive
*       - INTERRUPT
*       - AMO types
*
*     - Used internally in a YAMI implementation to cross async fifo:
*       - CREG_ACK:  ack to a Ctrl register load/store request
*
*   MFC (response) types: 4bits
*
*     - Availabel to the fabric:
*       - LOAD_ACK
*       - STORE_ACK
*       - INTERRUPT_ACK
*       - AMO_ACK
*       - CACHE_INV
*
*     - Used internally in a YAMI implementation to cross async fifo:
*       - CREG_LOAD: load a ctrl register value
*       - CREG_STORE: store a ctrl register value
*
* Optional Features
* -----------------
*
*   * Memory threads: similar to AXI4 ID
*   * Non-cacheable accesses:
*   * Streaming/repetitive requests:
*   * Atomic operations:
*   * Soft cache (L1 cache)
*   * Subword transactions:
*   * Interrupts
*
* FMC/R channel
* -------------
*
*   An FMC/R channel must have the following ports (direction from the
*   fabric's point of view):
*
*     - input                       fmr_rdy
*     - output                      fmr_vld
*     - output [5:0]                fmr_type: request type
*     - output [FMC_ADDR_WIDTH-1:0] fmr_addr: request address
*     - output                      fmr_parity: odd parity
*
*   Optional:
*
*     - output [THREAD_WIDTH-1:0]   fmr_thread
*     - output [2:0]                fmr_size: request size
*         * full, 1B, 2B, 4B, 8B, 16B, 32B, 64B
*     - output [7:0]                fmr_len:
*         * number of increments/repetitions **MINUS 1** in
*           streaming/repetitive mode. i.e. 0 means 1 load/store
*
* FMC/D channel
* -------------
*
*   Only needed when store/atomic operations are supported
*
*     - input                       fmd_rdy
*     - output                      fmd_vld
*     - output [FMC_DATA_WIDTH-1:0] fmd_data: request data
*         * when `fmc_size` is also supported, sub-word requests should be
*           replicated and filled. e.g. 1B write over an 8B interface:
*               data = {8{byte}}
*     - output                      fmd_parity: odd parity
*
* MFC/R channel
* -------------
*
*   An MFC/R channel must have the following ports (direction from the
*   fabric's point of view):
*
*     - output                      mfr_rdy
*     - input                       mfr_vld
*     - input [3:0]                 mfr_type: response type
*
*   Optional:
*
*     - input [THREAD_WIDTH-1:0]    mfr_thread
*     - input [MFC_ADDR_WIDTH-1:0]  mfr_addr: invalidation address
*     - input [7:0]                 mfr_len:
*         * number of increments/repetitions **MINUS 1** in
*           streaming/repetitive mode. i.e. 0 means 1 load/store
*         * required for non-endpoint implementations for flow control
*
* MFC/D channel
*
*   Only needed when load/atomic/l1cache are supported
*
*     - output                      mfd_rdy
*     - input                       mfd_vld
*     - input [MFC_DATA_WIDTH-1:0]  mfd_data: response data
*         * when `fmc_size` is also supported, sub-word requests should be
*           replicated and filled. e.g. 1B load over an 8B interface:
*               data = {8{byte}}
*
*/
`ifndef PRGA_YAMI_VH
`define PRGA_YAMI_VH

// -- Parameterized Macros ---------------------------------------------------
`define PRGA_YAMI_THREAD_WIDTH              {{ [intf.thread_width, 1]|max }}
`define PRGA_YAMI_MAX_THREAD                {{ intf.max_thread }}

`define PRGA_YAMI_FMC_FIFO_DEPTH_LOG2       {{ intf.fmc_fifo_depth_log2 }}
`define PRGA_YAMI_FMC_ADDR_WIDTH            {{ intf.fmc_addr_width }}
`define PRGA_YAMI_FMC_DATA_BYTES_LOG2       {{ intf.fmc_data_bytes_log2 }}

`define PRGA_YAMI_MFC_FIFO_DEPTH_LOG2       {{ intf.mfc_fifo_depth_log2 }}
`define PRGA_YAMI_MFC_ADDR_WIDTH            {{ intf.mfc_addr_width }}
`define PRGA_YAMI_MFC_DATA_BYTES_LOG2       {{ intf.mfc_data_bytes_log2 }}

// -- Derived Macros ---------------------------------------------------------
`define PRGA_YAMI_FMC_DATA_BYTES            (1 << `PRGA_YAMI_FMC_DATA_BYTES_LOG2)
`define PRGA_YAMI_FMC_DATA_WIDTH            (8 << `PRGA_YAMI_FMC_DATA_BYTES_LOG2)

`define PRGA_YAMI_MFC_DATA_BYTES            (1 << `PRGA_YAMI_MFC_DATA_BYTES_LOG2)
`define PRGA_YAMI_MFC_DATA_WIDTH            (8 << `PRGA_YAMI_MFC_DATA_BYTES_LOG2)

// -- Fixed Macros -----------------------------------------------------------
`define PRGA_YAMI_SIZE_WIDTH                3
`define PRGA_YAMI_SIZE_FULL                 `PRGA_YAMI_SIZE_WIDTH'b000  // use FMC_DATA_WIDTH for store and MFC_DATA_WIDTH for load
`define PRGA_YAMI_SIZE_1B                   `PRGA_YAMI_SIZE_WIDTH'b001
`define PRGA_YAMI_SIZE_2B                   `PRGA_YAMI_SIZE_WIDTH'b010
`define PRGA_YAMI_SIZE_4B                   `PRGA_YAMI_SIZE_WIDTH'b011
`define PRGA_YAMI_SIZE_8B                   `PRGA_YAMI_SIZE_WIDTH'b100
`define PRGA_YAMI_SIZE_16B                  `PRGA_YAMI_SIZE_WIDTH'b101
`define PRGA_YAMI_SIZE_32B                  `PRGA_YAMI_SIZE_WIDTH'b110
`define PRGA_YAMI_SIZE_64B                  `PRGA_YAMI_SIZE_WIDTH'b111

`define PRGA_YAMI_LEN_WIDTH                 8

`define PRGA_YAMI_FMC_REQTYPE_WIDTH         6
`define PRGA_YAMI_FMC_REQTYPE_NONE          `PRGA_YAMI_FMC_REQTYPE_WIDTH'b000000
`define PRGA_YAMI_FMC_REQTYPE_CREG_ACK      `PRGA_YAMI_FMC_REQTYPE_WIDTH'b000001

`define PRGA_YAMI_FMC_REQTYPE_LOAD          `PRGA_YAMI_FMC_REQTYPE_WIDTH'b100000
`define PRGA_YAMI_FMC_REQTYPE_LOAD_NC       `PRGA_YAMI_FMC_REQTYPE_WIDTH'b100001
`define PRGA_YAMI_FMC_REQTYPE_LOAD_REP_NC   `PRGA_YAMI_FMC_REQTYPE_WIDTH'b100011    // repetitive, non-cacheable

`define PRGA_YAMI_FMC_REQTYPE_STORE         `PRGA_YAMI_FMC_REQTYPE_WIDTH'b101000
`define PRGA_YAMI_FMC_REQTYPE_STORE_NC      `PRGA_YAMI_FMC_REQTYPE_WIDTH'b101001
`define PRGA_YAMI_FMC_REQTYPE_STORE_REP_NC  `PRGA_YAMI_FMC_REQTYPE_WIDTH'b101011    // repetitive, non-cacheable

`define PRGA_YAMI_FMC_REQTYPE_AMO_LR        `PRGA_YAMI_FMC_REQTYPE_WIDTH'b110001
`define PRGA_YAMI_FMC_REQTYPE_AMO_SC        `PRGA_YAMI_FMC_REQTYPE_WIDTH'b110010
`define PRGA_YAMI_FMC_REQTYPE_AMO_SWAP      `PRGA_YAMI_FMC_REQTYPE_WIDTH'b110011
`define PRGA_YAMI_FMC_REQTYPE_AMO_ADD       `PRGA_YAMI_FMC_REQTYPE_WIDTH'b110100
`define PRGA_YAMI_FMC_REQTYPE_AMO_AND       `PRGA_YAMI_FMC_REQTYPE_WIDTH'b110101
`define PRGA_YAMI_FMC_REQTYPE_AMO_OR        `PRGA_YAMI_FMC_REQTYPE_WIDTH'b110110
`define PRGA_YAMI_FMC_REQTYPE_AMO_XOR       `PRGA_YAMI_FMC_REQTYPE_WIDTH'b110111
`define PRGA_YAMI_FMC_REQTYPE_AMO_MAX       `PRGA_YAMI_FMC_REQTYPE_WIDTH'b111000
`define PRGA_YAMI_FMC_REQTYPE_AMO_MAXU      `PRGA_YAMI_FMC_REQTYPE_WIDTH'b111001
`define PRGA_YAMI_FMC_REQTYPE_AMO_MIN       `PRGA_YAMI_FMC_REQTYPE_WIDTH'b111010
`define PRGA_YAMI_FMC_REQTYPE_AMO_MINU      `PRGA_YAMI_FMC_REQTYPE_WIDTH'b111011
// `define PRGA_YAMI_FMC_REQTYPE_AMO_CAS1      `PRGA_YAMI_FMC_REQTYPE_WIDTH'b111100
// `define PRGA_YAMI_FMC_REQTYPE_AMO_CAS2      `PRGA_YAMI_FMC_REQTYPE_WIDTH'b111101

`define PRGA_YAMI_MFC_RESPTYPE_WIDTH        4
`define PRGA_YAMI_MFC_RESPTYPE_NONE         `PRGA_YAMI_MFC_RESPTYPE_WIDTH'b0000
`define PRGA_YAMI_MFC_RESPTYPE_CREG_LOAD    `PRGA_YAMI_MFC_RESPTYPE_WIDTH'b0010
`define PRGA_YAMI_MFC_RESPTYPE_CREG_STORE   `PRGA_YAMI_MFC_RESPTYPE_WIDTH'b0001
`define PRGA_YAMI_MFC_RESPTYPE_LOAD_ACK     `PRGA_YAMI_MFC_RESPTYPE_WIDTH'b1000
`define PRGA_YAMI_MFC_RESPTYPE_STORE_ACK    `PRGA_YAMI_MFC_RESPTYPE_WIDTH'b1001
`define PRGA_YAMI_MFC_RESPTYPE_CACHE_INV    `PRGA_YAMI_MFC_RESPTYPE_WIDTH'b1011
`define PRGA_YAMI_MFC_RESPTYPE_AMO_DATA     `PRGA_YAMI_MFC_RESPTYPE_WIDTH'b1100
`define PRGA_YAMI_MFC_RESPTYPE_AMO_ACK      `PRGA_YAMI_MFC_RESPTYPE_WIDTH'b1101

// -- Ctrl Registers ---------------------------------------------------------
`define PRGA_YAMI_CREG_ADDR_WIDTH           8
`define PRGA_YAMI_CREG_DATA_BYTES_LOG2      2
`define PRGA_YAMI_CREG_DATA_BYTES           (1 << `PRGA_YAMI_CREG_DATA_BYTES_LOG2)
`define PRGA_YAMI_CREG_DATA_WIDTH           (8 << `PRGA_YAMI_CREG_DATA_BYTES_LOG2)

`define PRGA_YAMI_CREG_ADDR_STATUS          `PRGA_YAMI_CREG_ADDR_WIDTH'h00
`define PRGA_YAMI_CREG_ADDR_FEATURES        `PRGA_YAMI_CREG_ADDR_WIDTH'h04
`define PRGA_YAMI_CREG_ADDR_TIMEOUT         `PRGA_YAMI_CREG_ADDR_WIDTH'h08
`define PRGA_YAMI_CREG_ADDR_ERRCODE         `PRGA_YAMI_CREG_ADDR_WIDTH'h0c

`define PRGA_YAMI_CREG_STATUS_WIDTH         2
`define PRGA_YAMI_CREG_STATUS_RESET         `PRGA_YAMI_CREG_STATUS_WIDTH'b00
`define PRGA_YAMI_CREG_STATUS_INACTIVE      `PRGA_YAMI_CREG_STATUS_WIDTH'b01
`define PRGA_YAMI_CREG_STATUS_ACTIVE        `PRGA_YAMI_CREG_STATUS_WIDTH'b10
`define PRGA_YAMI_CREG_STATUS_ERROR         `PRGA_YAMI_CREG_STATUS_WIDTH'b11

`define PRGA_YAMI_CREG_FEATURE_WIDTH        24
`define PRGA_YAMI_CREG_FEATURE_BIT_LOAD     0
`define PRGA_YAMI_CREG_FEATURE_BIT_STORE    1
`define PRGA_YAMI_CREG_FEATURE_BIT_SUBWORD  2
`define PRGA_YAMI_CREG_FEATURE_BIT_NC       3
`define PRGA_YAMI_CREG_FEATURE_BIT_AMO      4
`define PRGA_YAMI_CREG_FEATURE_BIT_THREAD   5   // enable multiple memory threads
`define PRGA_YAMI_CREG_FEATURE_BIT_L1CACHE  6
`define PRGA_YAMI_CREG_FEATURE_BIT_STRREP   7

`define PRGA_YAMI_CREG_FEATURE_LOAD         (`PRGA_YAMI_CREG_FEATURE_WIDTH'h1 << `PRGA_YAMI_CREG_FEATURE_BIT_LOAD)
`define PRGA_YAMI_CREG_FEATURE_STORE        (`PRGA_YAMI_CREG_FEATURE_WIDTH'h1 << `PRGA_YAMI_CREG_FEATURE_BIT_STORE)
`define PRGA_YAMI_CREG_FEATURE_SUBWORD      (`PRGA_YAMI_CREG_FEATURE_WIDTH'h1 << `PRGA_YAMI_CREG_FEATURE_BIT_SUBWORD)
`define PRGA_YAMI_CREG_FEATURE_NC           (`PRGA_YAMI_CREG_FEATURE_WIDTH'h1 << `PRGA_YAMI_CREG_FEATURE_BIT_NC)
`define PRGA_YAMI_CREG_FEATURE_AMO          (`PRGA_YAMI_CREG_FEATURE_WIDTH'h1 << `PRGA_YAMI_CREG_FEATURE_BIT_AMO)
`define PRGA_YAMI_CREG_FEATURE_THREAD       (`PRGA_YAMI_CREG_FEATURE_WIDTH'h1 << `PRGA_YAMI_CREG_FEATURE_BIT_THREAD)
`define PRGA_YAMI_CREG_FEATURE_L1CACHE      (`PRGA_YAMI_CREG_FEATURE_WIDTH'h1 << `PRGA_YAMI_CREG_FEATURE_BIT_L1CACHE)
`define PRGA_YAMI_CREG_FEATURE_STRREP       (`PRGA_YAMI_CREG_FEATURE_WIDTH'h1 << `PRGA_YAMI_CREG_FEATURE_BIT_STRREP)

`define PRGA_YAMI_CREG_ERRCODE_UNKNOWN              `PRGA_YAMI_CREG_DATA_WIDTH'h00_000000
`define PRGA_YAMI_CREG_ERRCODE_FMD_TIMEOUT          `PRGA_YAMI_CREG_DATA_WIDTH'h01_000000
`define PRGA_YAMI_CREG_ERRCODE_MFR_TIMEOUT          `PRGA_YAMI_CREG_DATA_WIDTH'h01_000001
`define PRGA_YAMI_CREG_ERRCODE_MFD_TIMEOUT          `PRGA_YAMI_CREG_DATA_WIDTH'h01_000002
`define PRGA_YAMI_CREG_ERRCODE_PARITY               `PRGA_YAMI_CREG_DATA_WIDTH'h01_000004
`define PRGA_YAMI_CREG_ERRCODE_THREAD_OUT_OF_RANGE  `PRGA_YAMI_CREG_DATA_WIDTH'h01_000005
`define PRGA_YAMI_CREG_ERRCODE_SIZE_OUT_OF_RANGE    `PRGA_YAMI_CREG_DATA_WIDTH'h01_000006
`define PRGA_YAMI_CREG_ERRCODE_MISSING_FEATURES     `PRGA_YAMI_CREG_DATA_WIDTH'h80_000000   // missing features should be added
`define PRGA_YAMI_CREG_ERRCODE_INVAL_REQTYPE        `PRGA_YAMI_CREG_DATA_WIDTH'h81_000000   // reqtype should be added
`define PRGA_YAMI_CREG_ERRCODE_NONZERO_LEN          `PRGA_YAMI_CREG_DATA_WIDTH'h82_000000   // reqtype should be added

// -- Async FIFO Packets -----------------------------------------------------
    /*  FMC FIFO Header Packet
    *       * creg_load/creg_store packet
    *            63        58 57                        40 39       32 31                  0
    *           +------------+----------------------------+-----------+---------------------+
    *           |   reqtype  |              -             |    addr   | ctrl register value |
    *           +------------+----------------------------+-----------+---------------------+
    *
    *       * other ckets
    *            63        58 57  55 54         47 46    ??     ??                         0
    *           +------------+------+-------------+--------+---+----------------------------+
    *           |   reqtype  | size | str/rep len | thread | - |          address           |
    *           +------------+------+-------------+--------+---+----------------------------+
    *
    */
`define PRGA_YAMI_FMC_FIFO_DATA_BYTES_LOG2      3   // 64-bit wide
`define PRGA_YAMI_FMC_FIFO_DATA_BYTES           (1 << `PRGA_YAMI_FMC_FIFO_DATA_BYTES_LOG2)
`define PRGA_YAMI_FMC_FIFO_DATA_WIDTH           (8 << `PRGA_YAMI_FMC_FIFO_DATA_BYTES_LOG2)

`define PRGA_YAMI_FMC_FIFO_HDR_REQTYPE_INDEX    63-:`PRGA_YAMI_FMC_REQTYPE_WIDTH
`define PRGA_YAMI_FMC_FIFO_HDR_SIZE_INDEX       57-:`PRGA_YAMI_SIZE_WIDTH
`define PRGA_YAMI_FMC_FIFO_HDR_LEN_INDEX        54-:`PRGA_YAMI_LEN_WIDTH
`define PRGA_YAMI_FMC_FIFO_HDR_THREAD_INDEX     46-:`PRGA_YAMI_THREAD_WIDTH
`define PRGA_YAMI_FMC_FIFO_HDR_ADDR_INDEX       0+:`PRGA_YAMI_FMC_ADDR_WIDTH
`define PRGA_YAMI_FMC_FIFO_HDR_CREG_ADDR_INDEX  `PRGA_YAMI_CREG_DATA_WIDTH+:`PRGA_YAMI_CREG_ADDR_WIDTH
`define PRGA_YAMI_FMC_FIFO_HDR_CREG_DATA_INDEX  0+:`PRGA_YAMI_CREG_DATA_WIDTH

    /*   MFC FIFO Header Packet
    *       * creg_ack packet
    *            63      60 59                                      32 31                  0
    *           +----------+------------------------------------------+---------------------+
    *           | resptype |                     -                    | ctrl register value |
    *           +----------+------------------------------------------+---------------------+
    *
    *       * other packets
    *            63      60 59    55 54         47 46    ??     ??                         0
    *           +----------+--------+-------------+--------+---+----------------------------+
    *           | resptype |    -   | str/rep len | thread | - |          address           |
    *           +----------+--------+-------------+--------+---+----------------------------+
    *
    */

`define PRGA_YAMI_MFC_FIFO_DATA_BYTES_LOG2      3   // 64-bit wide
`define PRGA_YAMI_MFC_FIFO_DATA_BYTES           (1 << `PRGA_YAMI_FMC_FIFO_DATA_BYTES_LOG2)
`define PRGA_YAMI_MFC_FIFO_DATA_WIDTH           (8 << `PRGA_YAMI_FMC_FIFO_DATA_BYTES_LOG2)

`define PRGA_YAMI_MFC_FIFO_HDR_RESPTYPE_INDEX   63-:`PRGA_YAMI_MFC_RESPTYPE_WIDTH
`define PRGA_YAMI_MFC_FIFO_HDR_LEN_INDEX        54-:`PRGA_YAMI_LEN_WIDTH
`define PRGA_YAMI_MFC_FIFO_HDR_THREAD_INDEX     46-:`PRGA_YAMI_THREAD_WIDTH
`define PRGA_YAMI_MFC_FIFO_HDR_ADDR_INDEX       0+:`PRGA_YAMI_MFC_ADDR_WIDTH
`define PRGA_YAMI_MFC_FIFO_HDR_CREG_ADDR_INDEX  `PRGA_YAMI_CREG_DATA_WIDTH+:`PRGA_YAMI_CREG_ADDR_WIDTH
`define PRGA_YAMI_MFC_FIFO_HDR_CREG_DATA_INDEX  0+:`PRGA_YAMI_CREG_DATA_WIDTH

`endif /* `ifndef PRGA_YAMI_VH */
