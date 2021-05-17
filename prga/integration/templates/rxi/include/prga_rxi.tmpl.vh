/*
* ============================================================================
* ==== PRGA RXI* (Reconfigurable Accelerator Interface) ======================
* ============================================================================
*
* -----------------------
*   * pronounced as "reeksi"
*
* Introduction
* ------------
*   
*   RXI is an interface for PRGA-based eFPGAs based on addressable registers.
*
*   RXI diagram:
*
*       +--------------+                      +---------------+
*       |              |                      |  Programming  |
*       | prog-master >> -------------------> >>   Backend   >>
*       |              |                      +---------------+
*       |   Frontend   |    +------------+    +---------------+
*       |              x -> | Async FIFO | -> x               |
*       |              |    +------------+    |  Application  |
*       >> sys-slave   |    +------------+    |    Backend    |
*       |              x <- | Async FIFO | <- x               |
*       |              |    +------------+    | [app-master] >>
*       +--------------+                      +---------------+
*
*   Each ">>" symbol in the diagram above represents a simple addressable
*   register interface, with the following ports: (direction from the master's
*   point of view)
*
*     - input                       req_rdy
*     - output                      req_vld
*     - output [ADDR_WIDTH-1:0]     req_addr
*     - output [DATA_BYTES-1:0]     req_strb
*     - output [DATA_WIDTH-1:0]     req_data
*
*     - output                      resp_rdy
*     - input                       resp_vld
*     - input  [DATA_WIDTH-1:0]     resp_data
*
*   Specifically, [app-master] interface has a few extra ports in the response
*   channel:
*
*     - input                       resp_sync
*     - input  [HSRID_WIDTH-1:0]    resp_syncaddr
*     - input                       resp_parity
*
*   The 'sync' ports are used by the fabric to actively synchronize
*   hardware-sync'ed registers
*
* Notes
* -----
*
*   1. `req_addr` must be aligned to DATA_BYTES. [app-master] interface may save
*      the last few bits that are constant zero due to alignment
*   2. Use `req_strb` for subword accesses (must be supported by the
*      corresponding register, or a subword access will fail)
*   3. RXI only allows natually-aligned, single-unit store with `req_strb`.
*      For example, if DATA_WIDTH is 4B, valid `req_strb` values are:
*        - 4'b0001, 4'b0010, 4'b0100, 4'b1000:  for 1B store
*        - 4'b0011, 4'b1100:                    for 2B store
*        - 4'b1111:                             for 4B store
*   4. valid DATA_BYTES: 4 or 8
*
* Address Space
* -------------
*
*   The register address space is divided up into the following major regions:
*
*     - register  0-31: address 0x00 - 0x080/0x100 (DATA_BYTES=4B/8B)
*       control registers, not available to the application
*
*     - register 32-63: address 0x80/0x100 - 0x100/0x200
*       hardware-sync'ed registers
*
*     - register 64+: address 0x100/0x200 - max
*       custom soft registers
*
*   Control registers may be implemented in the system clock domain, the
*   application clock domain, or both. Loads/stores may or may not be forwarded
*   into the application clock domain.
*
*   Hardware-sync'ed registers are implemented in the system clock domain.
*   Loads/Stores to these addresses return immediately once the accesses
*   complete in the system clock domain.
*
*   Soft registers are implemented inside the application. Loads/Stores to
*   these addresses are always forwarded into the application clock domain,
*   and are only responded after the accesses complete in the application.
*   There are timers to keep the application to respond in time, otherwise the
*   interface will transition into an error state, and all soft register
*   accesses return bogus data until the interface is re-activated.
*
* Ordering
* --------
*
*   All accesses are responded in order at the frontend, no matter if the
*   accesses are to the same address or different addresses.
*
*   Accesses to programming registers (in the control register space) are
*   forwarded and responded in the same order as the frontend receives.
*   So are soft registers. Accesses to the hardware-sync'ed registers may not
*   be forwarded to the application in the same order as the frontend receives.
*
* Hardware-sync'ed Registers
* --------------------------
*
*   To accelerate the system accessing the reconfigurable accelerator, RXI
*   provides a few registers that are synchronized over to the system clock
*   domain, so certain accesses (load/store) return without going into the
*   application clock domain.
*
*   The first class of hardware-sync'ed registers are input FIFOs. Stores to
*   one of these addresses are pushed into a FIFO in the system clock domain,
*   and return immediately. The interface then eventually stores the value into
*   the application. Loads always return bogus data.
*
*   The second class are output token FIFOs. Each FIFO is accessible by two
*   addresses, one for blocking load, and the other for non-block load.
*   The application actively pushes data-less tokens into the FIFO. Loads to the
*   blocking address are stalled until valid tokens become available, or the
*   application times out; loads to the non-blocking address always return
*   immediately, either "success", "no-token", or "error". Stores to any of
*   these addresses do nothing.
*
*   The third class are output data FIFOs. They are like the blocking token
*   FIFOs with data. They return bogus data if the interface enters an error
*   state.
*
*   The last class are plain read-write registers implemented both in the system
*   clock domain and inside the application. Stores to these registers return
*   immediately, and are eventually forwarded into the application (only the
*   latest value). Loads to these registers return the value in the system
*   clock domain. Updates from the application are eventually
*   sync'ed over to the system clock domain. No timing/ordering guarantee is
*   provided when stores from the system and updates from the application happen
*   at the same time.
*/

`ifndef PRGA_RXI_VH
`define PRGA_RXI_VH

// -- parameterized macros --------------------------------------------------- 
`define PRGA_RXI_DATA_BYTES_LOG2        {{ intf.data_bytes_log2 }} // 2 or 3 (4B or 8B)
`define PRGA_RXI_ADDR_WIDTH             {{ intf.addr_width }} // at least 7 + DATA_BYTES_LOG2

// -- Derived Macros ---------------------------------------------------------
`define PRGA_RXI_DATA_BYTES             (1 << `PRGA_RXI_DATA_BYTES_LOG2)
`define PRGA_RXI_DATA_WIDTH             (8 << `PRGA_RXI_DATA_BYTES_LOG2)

`define PRGA_RXI_REGID_WIDTH            (`PRGA_RXI_ADDR_WIDTH - `PRGA_RXI_DATA_BYTES_LOG2)

// -- Non-Soft Registers -----------------------------------------------------
// non-soft register ID width
`define PRGA_RXI_NSRID_WIDTH            6

// -- Control Registers ------------------------------------------------------
// # registers: 32

// #0: status
`define PRGA_RXI_NSRID_STATUS           0
`define PRGA_RXI_STATUS_WIDTH           3

`define PRGA_RXI_STATUS_RESET           `PRGA_RXI_STATUS_WIDTH'h0
`define PRGA_RXI_STATUS_STANDBY         `PRGA_RXI_STATUS_WIDTH'h1
`define PRGA_RXI_STATUS_PROG_ERROR      `PRGA_RXI_STATUS_WIDTH'h2
`define PRGA_RXI_STATUS_APP_ERROR       `PRGA_RXI_STATUS_WIDTH'h3
`define PRGA_RXI_STATUS_PROGRAMMING     `PRGA_RXI_STATUS_WIDTH'h4
`define PRGA_RXI_STATUS_ACTIVE          `PRGA_RXI_STATUS_WIDTH'h5

// #1: error code
`define PRGA_RXI_NSRID_ERRCODE          1
`define PRGA_RXI_ERRCODE_WIDTH          32

`define PRGA_RXI_ERRCODE_NONE           `PRGA_RXI_ERRCODE_WIDTH'h00_000000
`define PRGA_RXI_ERRCODE_NOTOKEN        `PRGA_RXI_ERRCODE_WIDTH'h00_000001
`define PRGA_RXI_ERRCODE_REQ_TIMEOUT    `PRGA_RXI_ERRCODE_WIDTH'h01_000000
`define PRGA_RXI_ERRCODE_RESP_TIMEOUT   `PRGA_RXI_ERRCODE_WIDTH'h01_000001
`define PRGA_RXI_ERRCODE_RESP_PARITY    `PRGA_RXI_ERRCODE_WIDTH'h01_000002
`define PRGA_RXI_ERRCODE_RESP_NOREQ     `PRGA_RXI_ERRCODE_WIDTH'h01_000003
`define PRGA_RXI_ERRCODE_YAMI           `PRGA_RXI_ERRCODE_WIDTH'h10_000000  // add erroneous YAMI IDs

// #2: clock divider
`define PRGA_RXI_NSRID_CLKDIV           2
`define PRGA_RXI_CLKDIV_WIDTH           8

// #3: soft register timer
`define PRGA_RXI_NSRID_SOFTREG_TIMEOUT  3

/* #4: app reset
* 
*   Hold reset for the set amount of cycles and then release it
* 
*   Notes: app reset should typically be held for some time (e.g. a few hundred
*   cycles). If not held long enough, the memory response to a request sent
*   before the app reset could confuse the application after reset.
*/
`define PRGA_RXI_NSRID_APP_RST          4

/* #5: programming reset
*
*   Hold reset for the set amount of cycles and then release it
*
*   Notes: programming reset should typically be held for some time (e.g.
*   a few hundred cycles).
*/
`define PRGA_RXI_NSRID_PROG_RST         5

/* #6: YAMI array
*
*   Enable YAMI instances
*/
`define PRGA_RXI_NSRID_ENABLE_YAMI      6

// #7: reserved

/* #8 - #15: scratchpads (8x registers)
*
*   Software-managed hard registers
*/
`define PRGA_RXI_NSRID_SCRATCHPAD       8
`define PRGA_RXI_SCRATCHPAD_ID_WIDTH    3
`define PRGA_RXI_NUM_SCRATCHPADS        (1 << `PRGA_RXI_SCRATCHPAD_ID_WIDTH)

/* #16 - #31: programming registers (16x registers)
* 
*   Implemented in the programming backend
*/
`define PRGA_RXI_NSRID_PROG             16
`define PRGA_RXI_PROG_REG_ID_WIDTH      4
`define PRGA_RXI_NUM_PROG_REGS          (1 << `PRGA_RXI_PROG_REG_ID_WIDTH)

// -- Hardware-Sync'ed Registers ---------------------------------------------
// # registers: 32
`define PRGA_RXI_NSRID_HSR              32
`define PRGA_RXI_HSRID_WIDTH            5

// #32 - #35: input FIFO
`define PRGA_RXI_HSRID_IQ               0
`define PRGA_RXI_HSR_IQ_ID_WIDTH        2
`define PRGA_RXI_NUM_HSR_IQS            (1 << `PRGA_RXI_HSR_IQ_ID_WIDTH)

// #36 - #39: output data FIFO
`define PRGA_RXI_HSRID_OQ               4
`define PRGA_RXI_HSR_OQ_ID_WIDTH        2
`define PRGA_RXI_NUM_HSR_OQS            (1 << `PRGA_RXI_HSR_OQ_ID_WIDTH)

// #40 - #47: output token FIFO
`define PRGA_RXI_HSR_TQ_ID_WIDTH        2
`define PRGA_RXI_NUM_HSR_TQS            (1 << `PRGA_RXI_HSR_TQ_ID_WIDTH)
`define PRGA_RXI_HSRID_TQ               8
`define PRGA_RXI_HSRID_TQ_NB            12

// #48 - #63: plain sync'ed registers
`define PRGA_RXI_HSR_PLAIN_ID_WIDTH     4
`define PRGA_RXI_NUM_HSR_PLAINS         (1 << `PRGA_RXI_HSR_PLAIN_ID_WIDTH)
`define PRGA_RXI_HSRID_PLAIN            16

// -- Soft Registers ---------------------------------------------------------
`define PRGA_RXI_SRID_BASE              64

// -- Async FIFO -------------------------------------------------------------
/*  FE->BE FIFO Element
*       |<- DATA_BYTES ->|<- REGID_WIDTH ->|<- DATA_WIDTH ->|
*       +----------------+-----------------+----------------+
*       |      strb      |      regid      |      data      |
*       +----------------+-----------------+----------------+
*
*   BE->FE FIFO Element
*       |<- 1bit ->|<- NSRID_WIDTH ->|<- DATA_WIDTH ->|
*       +----------+-----------------+----------------+
*       |   sync   |      hsrid      |      data      |
*       +----------+-----------------+----------------+
*
*/

`define PRGA_RXI_F2B_ELEM_WIDTH     (`PRGA_RXI_DATA_BYTES + `PRGA_RXI_REGID_WIDTH + `PRGA_RXI_DATA_WIDTH)
`define PRGA_RXI_F2B_DATA_BASE      0
`define PRGA_RXI_F2B_REGID_BASE     (`PRGA_RXI_F2B_DATA_BASE + `PRGA_RXI_DATA_WIDTH)
`define PRGA_RXI_F2B_STRB_BASE      (`PRGA_RXI_F2B_REGID_BASE + `PRGA_RXI_REGID_WIDTH)
`define PRGA_RXI_F2B_DATA_INDEX     `PRGA_RXI_F2B_DATA_BASE+:`PRGA_RXI_DATA_WIDTH
`define PRGA_RXI_F2B_REGID_INDEX    `PRGA_RXI_F2B_REGID_BASE+:`PRGA_RXI_REGID_WIDTH
`define PRGA_RXI_F2B_STRB_INDEX     `PRGA_RXI_F2B_STRB_BASE+:`PRGA_RXI_DATA_BYTES

`define PRGA_RXI_B2F_ELEM_WIDTH     (1 + `PRGA_RXI_NSRID_WIDTH + `PRGA_RXI_DATA_WIDTH)
`define PRGA_RXI_B2F_DATA_BASE      0
`define PRGA_RXI_B2F_NSRID_BASE     (`PRGA_RXI_B2F_DATA_BASE + `PRGA_RXI_DATA_WIDTH)
`define PRGA_RXI_B2F_SYNC_INDEX     (`PRGA_RXI_B2F_NSRID_BASE + `PRGA_RXI_NSRID_WIDTH)
`define PRGA_RXI_B2F_DATA_INDEX     `PRGA_RXI_B2F_DATA_BASE+:`PRGA_RXI_DATA_WIDTH
`define PRGA_RXI_B2F_NSRID_INDEX    `PRGA_RXI_B2F_NSRID_BASE+:`PRGA_RXI_NSRID_WIDTH

`endif /* `ifndef PRGA_RXI_VH */
