// Automatically generated by PRGA's RTL generator
`include "pktchain_axilite_intf.vh"
`timescale 1ns/1ps
module {{ module.name }} (
    // system ctrl signals
    input wire [0:0] clk,
    input wire [0:0] rst,

    // CREG (Controller Register) write interface
    input wire [0:0] wval,
    output reg [0:0] wrdy,
    input wire [`PRGA_BYTES_PER_AXI_DATA - 1:0] wstrb,
    input wire [`PRGA_AXI_DATA_WIDTH - 1:0] wdata,

    output wire [0:0] wresp,

    output reg [0:0] success,       // end of programming
    output reg [0:0] fail,          // end of programming

    // Error FIFO
    input wire [0:0] errfifo_full,
    output reg [0:0] errfifo_wr,
    output reg [`PRGA_AXI_DATA_WIDTH - 1:0] errfifo_data,

    // programming interface
    output reg [0:0] cfg_rst,
    output reg [0:0] cfg_e,

    // configuration output
    input wire [0:0] cfg_phit_o_full,
    output wire [0:0] cfg_phit_o_wr,
    output wire [`PRGA_PKTCHAIN_PHIT_WIDTH - 1:0] cfg_phit_o,

    // configuration input
    output wire [0:0] cfg_phit_i_full,
    input wire [0:0] cfg_phit_i_wr,
    input wire [`PRGA_PKTCHAIN_PHIT_WIDTH - 1:0] cfg_phit_i
    );

    assign wresp = wval && wrdy;    // immediate responses to writes

    // =======================================================================
    // -- Bitstream Programming Output & Response Input ----------------------
    // =======================================================================

    // AXI data FIFO
    wire [`PRGA_AXI_DATA_WIDTH + `PRGA_BYTES_PER_AXI_DATA - 1:0] axififo_din, axififo_dout;
    wire axififo_full, axififo_empty, axififo_rd;

    // put byte enable close to each byte (so the resizer can grab those correctly)
    genvar axi_disasm_i;
    generate
        for (axi_disasm_i = 0; axi_disasm_i < `PRGA_BYTES_PER_AXI_DATA; axi_disasm_i = axi_disasm_i + 1) begin: axi_disasm
            assign axififo_din[axi_disasm_i * 9 +: 9] = {wstrb[axi_disasm_i], wdata[axi_disasm_i * 8 +: 8]};
        end
    endgenerate

    prga_fifo #(
        .DATA_WIDTH             (`PRGA_AXI_DATA_WIDTH + `PRGA_BYTES_PER_AXI_DATA)
        ,.LOOKAHEAD             (0)
    ) axififo (
        .clk                    (clk)
        ,.rst                   (rst)
        ,.full                  (axififo_full)
        ,.wr                    (wval && wrdy)
        ,.din                   (axififo_din)
        ,.empty                 (axififo_empty)
        ,.rd                    (axififo_rd)
        ,.dout                  (axififo_dout)
        );

    // AXI data resizer
    wire [`PRGA_PKTCHAIN_FRAME_SIZE + `PRGA_BYTES_PER_FRAME - 1:0] axififo_resizer_dout;
    wire axififo_resizer_empty, axififo_resizer_rd;

    prga_fifo_resizer #(
        .DATA_WIDTH             (`PRGA_PKTCHAIN_FRAME_SIZE + `PRGA_BYTES_PER_FRAME)
        ,.INPUT_MULTIPLIER      (`PRGA_FRAMES_PER_AXI_DATA)
        ,.INPUT_LOOKAHEAD       (0)
        ,.OUTPUT_LOOKAHEAD      (1)
    ) axififo_resizer (
        .clk                    (clk)
        ,.rst                   (rst)
        ,.empty_i               (axififo_empty)
        ,.rd_i                  (axififo_rd)
        ,.dout_i                (axififo_dout)
        ,.empty                 (axififo_resizer_empty)
        ,.rd                    (axififo_resizer_rd)
        ,.dout                  (axififo_resizer_dout)
        );

    // re-assemble 
    wire [`PRGA_BYTES_PER_FRAME - 1:0] bsframe_mask;
    wire [`PRGA_PKTCHAIN_FRAME_SIZE - 1:0] bsframe;

    genvar bsframe_asm_i;
    generate
        for (bsframe_asm_i = 0; bsframe_asm_i < `PRGA_BYTES_PER_FRAME; bsframe_asm_i = bsframe_asm_i + 1) begin: bsframe_asm
            assign {bsframe_mask[bsframe_asm_i], bsframe[bsframe_asm_i * 8 +: 8]} = axififo_resizer_dout[bsframe_asm_i * 9 +: 9];
        end
    endgenerate

    localparam  OP_INVAL    = 2'b00,
                OP_ACCEPT   = 2'b01,
                OP_DROP     = 2'b10;

    wire bsframe_val, bsresp_val;
    reg [1:0] bsframe_op, bsresp_op;

    // frame disassembler
    wire bsframe_fifo_full;

    pktchain_frame_disassemble #(
        .DEPTH_LOG2             (11 - `PRGA_PKTCHAIN_PHIT_WIDTH_LOG2)   // buffer capacity: 64 frames
    ) bsframe_fifo (
        .cfg_clk                    (clk)
        ,.cfg_rst                   (cfg_rst)
        ,.frame_full                (bsframe_fifo_full)
        ,.frame_wr                  (bsframe_val && bsframe_op == OP_ACCEPT)
        ,.frame_i                   (bsframe)
        ,.phit_wr                   (cfg_phit_o_wr)
        ,.phit_full                 (cfg_phit_o_full)
        ,.phit_o                    (cfg_phit_o)
        );

    assign bsframe_val = ~axififo_resizer_empty && (&bsframe_mask);
    assign axififo_resizer_rd = ~bsframe_val || (bsframe_op == OP_ACCEPT && ~bsframe_fifo_full) || bsframe_op == OP_DROP;

    // response assembler
    wire bsresp_fifo_empty;
    wire [`PRGA_PKTCHAIN_FRAME_SIZE - 1:0] bsresp;

    pktchain_frame_assemble #(
        .DEPTH_LOG2             (2)                                     // buffer capacity: 4 frames
    ) bsresp_fifo (
        .cfg_clk                    (clk)
        ,.cfg_rst                   (cfg_rst)
        ,.phit_full                 (cfg_phit_i_full)
        ,.phit_wr                   (cfg_phit_i_wr)
        ,.phit_i                    (cfg_phit_i)
        ,.frame_empty               (bsresp_fifo_empty)
        ,.frame_rd                  (bsresp_op == OP_ACCEPT || bsresp_op == OP_DROP)
        ,.frame_o                   (bsresp)
        );

    assign bsresp_val = ~bsresp_fifo_empty;

    // =======================================================================
    // -- Tile Status Tracker ------------------------------------------------
    // =======================================================================

    // Tile status tracker
    localparam  LOG2_PKTCHAIN_X_TILES = `CLOG2(`PRGA_PKTCHAIN_X_TILES),
                LOG2_PKTCHAIN_Y_TILES = `CLOG2(`PRGA_PKTCHAIN_Y_TILES);
    reg [LOG2_PKTCHAIN_X_TILES - 1:0]   tile_status_tracker_rd_xpos,
                                        tile_status_tracker_rd_xpos_f;
    reg [LOG2_PKTCHAIN_Y_TILES - 1:0]   tile_status_tracker_rd_ypos,
                                        tile_status_tracker_rd_ypos_f;
    wire [`PRGA_PKTCHAIN_Y_TILES * `PRGA_TILE_STATUS_TRACKER_WIDTH - 1:0] tile_status_tracker_col_dout;
    reg [`PRGA_PKTCHAIN_Y_TILES * `PRGA_TILE_STATUS_TRACKER_WIDTH - 1:0] tile_status_tracker_col_din;
    reg tile_status_tracker_col_we;

    prga_ram_1r1w #(
        .DATA_WIDTH                 (`PRGA_PKTCHAIN_Y_TILES * `PRGA_TILE_STATUS_TRACKER_WIDTH)
        ,.ADDR_WIDTH                (LOG2_PKTCHAIN_X_TILES)
        ,.RAM_ROWS                  (`PRGA_PKTCHAIN_X_TILES)
    ) tile_status_tracker (
        .clk                        (clk)
        ,.raddr                     (tile_status_tracker_rd_xpos)
        ,.dout                      (tile_status_tracker_col_dout)
        ,.waddr                     (tile_status_tracker_rd_xpos_f)
        ,.din                       (tile_status_tracker_col_din)
        ,.we                        (tile_status_tracker_col_we)
        );

    always @(posedge clk) begin
        if (rst) begin
            tile_status_tracker_rd_xpos_f <= 'b0;
            tile_status_tracker_rd_ypos_f <= 'b0;
        end else begin
            tile_status_tracker_rd_xpos_f <= tile_status_tracker_rd_xpos;
            tile_status_tracker_rd_ypos_f <= tile_status_tracker_rd_ypos;
        end
    end

    reg [`PRGA_TILE_STATUS_TRACKER_WIDTH - 1:0] tile_status_tracker_dout;
    reg [`PRGA_TILE_STATUS_TRACKER_WIDTH - 1:0] tile_status_tracker_din;
    reg tile_status_tracker_wop_clean_col, tile_status_tracker_wop_update;

    always @* begin
        tile_status_tracker_col_we = tile_status_tracker_wop_clean_col || tile_status_tracker_wop_update;
        tile_status_tracker_dout = tile_status_tracker_col_dout[tile_status_tracker_rd_ypos_f * `PRGA_TILE_STATUS_TRACKER_WIDTH +:
                                   `PRGA_TILE_STATUS_TRACKER_WIDTH];
        tile_status_tracker_col_din = tile_status_tracker_col_dout;
        
        if (tile_status_tracker_wop_clean_col) begin
            tile_status_tracker_col_din = 'b0;
        end else if (tile_status_tracker_wop_update) begin
            tile_status_tracker_col_din[tile_status_tracker_rd_ypos_f * `PRGA_TILE_STATUS_TRACKER_WIDTH +:
                `PRGA_TILE_STATUS_TRACKER_WIDTH] = tile_status_tracker_din;
        end
    end

    // =======================================================================
    // -- Main FSM -----------------------------------------------------------
    // =======================================================================

    // PHASE (or, big state)
    localparam  PHASE_RST                   = 4'h0,     // system is just reset
                PHASE_CLR_TILE_STAT_TRCKERS = 4'h1,     // clearing tile status trackers
                PHASE_STANDBY               = 4'h2,     // waiting for the SOB packet
                PHASE_PROG                  = 4'h3,     // actively accepting bitstream
                PHASE_STBLIZ                = 4'h4,     // stop accepting bitstream and focus on collecting pending responses
                PHASE_SUCCESS               = 4'h5,     // programming completed successfully
                PHASE_FAIL                  = 4'h6;     // programming failed

    // STATE (or, small state)
    localparam  ST_IDLE                     = 4'h0,     // waiting for a header frame
                ST_HDR                      = 4'h1,     // processing a valid header
                ST_FWD_PLD                  = 4'h2,     // forwarding valid payload frames
                ST_DUMP_PLD                 = 4'h3,     // dumping invalid frames
                ST_ERR                      = 4'h4;     // an error is pending

    reg [3:0] phase, phase_next;
    reg [3:0] pkt_st, pkt_st_next, resp_st, resp_st_next;
    reg [`PRGA_PKTCHAIN_PAYLOAD_WIDTH - 1:0] pkt_payload, pkt_payload_next, resp_payload, resp_payload_next;
    reg [`PRGA_PKTCHAIN_POS_WIDTH * 2 - 1:0] init_tiles, init_tiles_next;
    reg [`PRGA_PKTCHAIN_POS_WIDTH * 2 - 1:0] pending_tiles, pending_tiles_next;
    reg [`PRGA_PKTCHAIN_POS_WIDTH * 2 - 1:0] err_tiles, err_tiles_next;
    reg [`PRGA_AXI_DATA_WIDTH - 1:0] errfifo_data_pkt, errfifo_data_pkt_f;
    reg [`PRGA_AXI_DATA_WIDTH - 1:0] errfifo_data_resp, errfifo_data_resp_f;

    // resource management helpers
    reg tile_status_tracker_busy;

    always @(posedge clk) begin
        if (rst) begin
            phase <= PHASE_RST;
            pkt_st <= ST_IDLE;
            resp_st <= ST_IDLE;
            pkt_payload <= 'b0;
            resp_payload <= 'b0;
            init_tiles <= 'b0;
            pending_tiles <= 'b0;
            err_tiles <= 'b0;
            errfifo_data_pkt_f <= 'b0;
            errfifo_data_resp_f <= 'b0;
        end else begin
            phase <= phase_next;
            pkt_st <= pkt_st_next;
            resp_st <= resp_st_next;
            pkt_payload <= pkt_payload_next;
            resp_payload <= resp_payload_next;
            init_tiles <= init_tiles_next;
            pending_tiles <= pending_tiles_next;
            err_tiles <= err_tiles_next;
            errfifo_data_pkt_f <= errfifo_data_pkt;
            errfifo_data_resp_f <= errfifo_data_resp;
        end
    end
    {#
        // ===================================================================
        // -- Define Text Macros (Jinja2) ------------------------------------
        // ===================================================================
        #}
    {%- macro try_send_error(is_resp) %}
        {%- set v0 = "resp" if is_resp else "pkt" %}
        {%- set v1 = "resp" if is_resp else "frame" %}
        if (~errfifo_wr) begin
            errfifo_wr = 'b1;
            errfifo_data = errfifo_data_{{ v0 }};

            if (~errfifo_full) begin
                bs{{ v1 }}_op = OP_DROP;
                {{ v0 }}_payload_next = bs{{ v1 }}[`PRGA_PKTCHAIN_PAYLOAD_INDEX];

                if (bs{{ v1 }}[`PRGA_PKTCHAIN_PAYLOAD_INDEX] > 0) begin
                    {{ v0 }}_st_next = ST_DUMP_PLD;
                end else begin
                    {{ v0 }}_st_next = ST_IDLE;
                end
            end else begin
                {{ v0 }}_st_next = ST_ERR;
            end
        end else begin
            {{ v0 }}_st_next = ST_ERR;
        end
    {%- endmacro %}

    always @* begin
        phase_next = phase;

        init_tiles_next = init_tiles;
        pending_tiles_next = pending_tiles;
        err_tiles_next = err_tiles;

        wrdy = 'b0;
        success = 'b0;
        fail = 'b0;
        errfifo_wr = 'b0;
        errfifo_data = 'b0;
        cfg_rst = 'b0;
        cfg_e = 'b0;
        
        tile_status_tracker_rd_xpos = 'b0;
        tile_status_tracker_rd_ypos = 'b0;
        tile_status_tracker_din = tile_status_tracker_dout;
        tile_status_tracker_wop_clean_col = 'b0;
        tile_status_tracker_wop_update = 'b0;
        tile_status_tracker_busy = 'b0;

        // BIG state
        case (phase)
            PHASE_RST: begin
                phase_next = PHASE_CLR_TILE_STAT_TRCKERS;
                init_tiles_next = 'b0;
                pending_tiles_next = 'b0;
                err_tiles_next = 'b0;
                cfg_rst = 'b1;
                cfg_e = 'b1;
                tile_status_tracker_rd_xpos = 'b0;
            end
            PHASE_CLR_TILE_STAT_TRCKERS: begin
                init_tiles_next = 'b0;
                pending_tiles_next = 'b0;
                err_tiles_next = 'b0;
                cfg_rst = 'b1;
                cfg_e = 'b1;
                tile_status_tracker_rd_xpos = tile_status_tracker_rd_xpos_f + 1;
                tile_status_tracker_wop_clean_col = 'b1;

                if (tile_status_tracker_rd_xpos_f == `PRGA_PKTCHAIN_X_TILES - 1) begin
                    phase_next = PHASE_STANDBY;
                end
            end
            PHASE_STANDBY: begin
                wrdy = 'b1;
                cfg_rst = 'b1;
                cfg_e = 'b1;

                if (pkt_st == ST_IDLE && bsframe_val && bsframe == {`PRGA_PKTCHAIN_MSG_TYPE_SOB,
                    {`PRGA_PKTCHAIN_POS_WIDTH{1'b0}}, {`PRGA_PKTCHAIN_POS_WIDTH{1'b0}}, {`PRGA_PKTCHAIN_PAYLOAD_WIDTH{1'b0}}}
                ) begin
                    phase_next = PHASE_PROG;
                end
            end
            PHASE_PROG: begin
                wrdy = 'b1;
                cfg_e = 'b1;

                if (pkt_st == ST_IDLE && bsframe_val && bsframe == {`PRGA_PKTCHAIN_MSG_TYPE_EOB,
                    {`PRGA_PKTCHAIN_POS_WIDTH{1'b0}}, {`PRGA_PKTCHAIN_POS_WIDTH{1'b0}}, {`PRGA_PKTCHAIN_PAYLOAD_WIDTH{1'b0}}}
                ) begin
                    phase_next = PHASE_STBLIZ;
                end
            end
            PHASE_STBLIZ: begin
                if (pending_tiles == 0) begin
                    if (init_tiles) begin   // initialized yet not completed tiles
                        errfifo_wr = 'b1;
                        errfifo_data[`PRGA_ERR_TYPE_INDEX] = `PRGA_ERR_TYPE_BITSTREAM;
                        errfifo_data[`PRGA_ERR_BITSTREAM_SUBTYPE_INDEX] = `PRGA_ERR_BITSTREAM_SUBTYPE_INCOMPLETE_TILES;
                        errfifo_data[0 +: `PRGA_PKTCHAIN_POS_WIDTH * 2] = init_tiles;
                        
                        if (~errfifo_full) begin
                            phase_next = PHASE_FAIL;
                        end
                    end else if (err_tiles) begin   // some tiles had errors
                        errfifo_wr = 'b1;
                        errfifo_data[`PRGA_ERR_TYPE_INDEX] = `PRGA_ERR_TYPE_BITSTREAM;
                        errfifo_data[`PRGA_ERR_BITSTREAM_SUBTYPE_INDEX] = `PRGA_ERR_BITSTREAM_SUBTYPE_ERROR_TILES;
                        errfifo_data[0 +: `PRGA_PKTCHAIN_POS_WIDTH * 2] = err_tiles;
                        
                        if (~errfifo_full) begin
                            phase_next = PHASE_FAIL;
                        end
                    end else begin
                        phase_next = PHASE_SUCCESS
                    end
                end else begin
                    cfg_e = 'b1;
                end
            end
            PHASE_SUCCESS: begin
                success = 'b1;
            end
            PHASE_FAIL: begin
                fail = 'b1;
            end
        endcase

        // put this before pkt_st so resources are allocated to response
        // handling first
        resp_st_next = resp_st;
        resp_payload_next = resp_payload;
        bsresp_op = OP_INVAL;
        errfifo_data_resp = 'b0;

        case (resp_st)
            ST_IDLE: begin
                case (phase)    // we only accept response in certain phases
                    PHASE_PROG,
                    PHASE_STBLIZ: begin
                        if (bsresp_val) begin   // response header
                            if (bsresp[`PRGA_PKTCHAIN_XPOS_INDEX] >= `PRGA_PKTCHAIN_X_TILES
                                || bsresp[`PRGA_PKTCHAIN_YPOS_INDEX] >= `PRGA_PKTCHAIN_Y_TILES
                                || bsresp[`PRGA_PKTCHAIN_PAYLOAD_INDEX] > 0
                                || ~(bsresp[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_DATA_ACK
                                    || bsresp[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_ERROR_UNKNOWN_MSG_TYPE
                                    || bsresp[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_ERROR_ECHO_MISMATCH
                                    || bsresp[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_ERROR_CHECKSUM_MISMATCH
                                    || bsresp[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_ERROR_FEEDTHRU_PACKET)
                            ) begin
                                // bad header
                                errfifo_data_resp[`PRGA_ERR_TYPE_INDEX] = `PRGA_ERR_TYPE_BITSTREAM;
                                errfifo_data_resp[`PRGA_ERR_BITSTREAM_SUBTYPE_INDEX] = `PRGA_ERR_BITSTREAM_SUBTYPE_INVAL_RESP;
                                errfifo_data_resp[0 +: `PRGA_PKTCHAIN_FRAME_SIZE] = bsresp;

                                {{ try_send_error(true)|indent(24) }}
                            end else begin
                                // good header
                                if (~tile_status_tracker_busy) begin
                                    tile_status_tracker_busy = 'b1;
                                    tile_status_tracker_rd_xpos = bsresp[`PRGA_PKTCHAIN_XPOS_INDEX];
                                    tile_status_tracker_rd_ypos = bsresp[`PRGA_PKTCHAIN_YPOS_INDEX];
                                    resp_st_next = ST_HDR;
                                end
                            end
                        end
                    end
                endcase
            end
            ST_HDR: begin
                errfifo_data_resp[`PRGA_ERR_TYPE_INDEX] = `PRGA_ERR_TYPE_BITSTREAM;
                errfifo_data_resp[`PRGA_ERR_BITSTREAM_SUBTYPE_INDEX] = `PRGA_ERR_BITSTREAM_SUBTYPE_ERR_RESP;
                errfifo_data_resp[0 +: `PRGA_PKTCHAIN_FRAME_SIZE] = bsresp;
                errfifo_data_resp[`PRGA_PKTCHAIN_FRAME_SIZE +: `PRGA_TILE_STATUS_TRACKER_WIDTH] = tile_status_tracker_dout;

                case (tile_status_tracker_dout)
                    `PRGA_TILE_STATUS_PENDING: begin
                        if (bsresp[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_DATA_ACK) begin
                            tile_status_tracker_wop_update = 'b1;
                            tile_status_tracker_din = `PRGA_TILE_STATUS_DONE;
                            pending_tiles_next = pending_tiles - 1;
                            resp_st_next = ST_IDLE;
                            bsresp_op = OP_DROP;
                        end else begin
                            tile_status_tracker_wop_update = 'b1;
                            tile_status_tracker_din = `PRGA_TILE_STATUS_ERROR;
                            pending_tiles_next = pending_tiles - 1;
                            err_tiles_next = err_tiles + 1;

                            {{ try_send_error(true)|indent(20) }}
                        end
                    end
                    `PRGA_TILE_STATUS_ERROR: begin
                        resp_st_next = ST_IDLE;
                        bsresp_op = OP_DROP;
                    end
                    default: begin
                        tile_status_tracker_wop_update = 'b1;
                        tile_status_tracker_din = `PRGA_TILE_STATUS_ERROR;
                        err_tiles_next = err_tiles + 1;

                        if (tile_status_tracker_dout == `PRGA_TILE_STATUS_PROGRAMMING) begin
                            init_tiles_next = init_tiles - 1;
                        end

                        {{ try_send_error(true)|indent(16) }}
                    end
                endcase
            end
            ST_DUMP_PLD: begin
                if (bsresp_val) begin
                    bsresp_op = OP_DROP;
                    resp_payload_next = resp_payload - 1;

                    if (resp_payload == 1) begin
                        resp_st_next = ST_IDLE;
                    end
                end
            end
            ST_ERR: begin
                errfifo_data_resp = errfifo_data_resp_f;

                {{ try_send_error(true)|indent(8) }}
            end
        endcase

        pkt_st_next = pkt_st;
        pkt_payload_next = pkt_payload;
        bsframe_op = OP_INVAL;
        errfifo_data_pkt = 'b0;

        case (pkt_st)
            ST_IDLE: begin
                case (phase)    // we only accept incoming bitstream frames in certain phases
                    PHASE_STANDBY: begin    // expecting SOB packet
                        if (bsframe_val) begin
                            if (bsframe == {`PRGA_PKTCHAIN_MSG_TYPE_SOB,
                                {`PRGA_PKTCHAIN_POS_WIDTH{1'b0}},
                                {`PRGA_PKTCHAIN_POS_WIDTH{1'b0}},
                                {`PRGA_PKTCHAIN_PAYLOAD_WIDTH{1'b0}}}
                            ) begin         // start of bitstream
                                bsframe_op = OP_DROP;
                            end else begin
                                errfifo_data[`PRGA_ERR_TYPE_INDEX] = `PRGA_ERR_BITSTREAM;
                                errfifo_data[`PRGA_ERR_BITSTREAM_SUBTYPE_INDEX] = `PRGA_ERR_BITSTREAM_SUBTYPE_EXPECTING_SOB;
                                errfifo_data[0 +: `PRGA_PKTCHAIN_FRAME_SIZE] = bsframe;

                                {{ try_send_error(false)|indent(24) }}
                            end
                        end
                    end
                    PHASE_PROG: begin       // expecting non-SOB packet
                        if (bsframe_val) begin
                            if (bsframe == {`PRGA_PKTCHAIN_MSG_TYPE_EOB,
                                {`PRGA_PKTCHAIN_POS_WIDTH{1'b0}},
                                {`PRGA_PKTCHAIN_POS_WIDTH{1'b0}},
                                {`PRGA_PKTCHAIN_PAYLOAD_WIDTH{1'b0}}}
                            ) begin         // end of bitstream
                                bsframe_op = OP_DROP;
                            end else if (bsframe[`PRGA_PKTCHAIN_XPOS_INDEX] >= `PRGA_PKTCHAIN_X_TILES
                                || bsframe[`PRGA_PKTCHAIN_YPOS_INDEX] >= `PRGA_PKTCHAIN_Y_TILES
                                || ~(bsframe[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_DATA
                                    || bsframe[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_DATA_INIT
                                    || bsframe[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_DATA_CHECKSUM
                                    || bsframe[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_DATA_INIT_CHECKSUM)
                            ) begin
                                // bad header
                                errfifo_data_pkt[`PRGA_ERR_TYPE_INDEX] = `PRGA_ERR_TYPE_BITSTREAM;
                                errfifo_data_pkt[`PRGA_ERR_BITSTREAM_SUBTYPE_INDEX] = `PRGA_ERR_BITSTREAM_SUBTYPE_INVAL_PKT;
                                errfifo_data_pkt[0 +: `PRGA_PKTCHAIN_FRAME_SIZE] = bsframe;

                                {{ try_send_error(false)|indent(24) }}
                            end else begin
                                // good header
                                if (~tile_status_tracker_busy) begin
                                    tile_status_tracker_busy = 'b1;
                                    tile_status_tracker_rd_xpos = bsframe[`PRGA_PKTCHAIN_XPOS_INDEX];
                                    tile_status_tracker_rd_ypos = bsframe[`PRGA_PKTCHAIN_YPOS_INDEX];
                                    pkt_st_next = ST_HDR;
                                end
                            end
                        end
                    end
                endcase
            end
            ST_HDR: begin
                errfifo_data_pkt[`PRGA_ERR_TYPE_INDEX] = `PRGA_ERR_TYPE_BITSTREAM;
                errfifo_data_pkt[`PRGA_ERR_BITSTREAM_SUBTYPE_INDEX] = `PRGA_ERR_BITSTREAM_SUBTYPE_ERR_PKT;
                errfifo_data_pkt[0 +: `PRGA_PKTCHAIN_FRAME_SIZE] = bsframe;
                errfifo_data_pkt[`PRGA_PKTCHAIN_FRAME_SIZE +: `PRGA_TILE_STATUS_TRACKER_WIDTH] = tile_status_tracker_dout;

                case (tile_status_tracker_dout)
                    `PRGA_TILE_STATUS_RESET: begin
                        case (bsframe[`PRGA_PKTCHAIN_MSG_TYPE_INDEX])
                            `PRGA_PKTCHAIN_MSG_TYPE_DATA_INIT,
                            `PRGA_PKTCHAIN_MSG_TYPE_DATA_INIT_CHECKSUM: begin
                                // good. tile initialized
                                if (bsframe[`PRGA_PKTCHAIN_MSG_TYPE_INDEX] == `PRGA_PKTCHAIN_MSG_TYPE_DATA_INIT) begin
                                    init_tiles_next = init_tiles + 1;
                                    tile_status_tracker_din = `PRGA_TILE_STATUS_PROGRAMMING;
                                end else begin
                                    pending_tiles_next = pending_tiles + 1;
                                    tile_status_tracker_din = `PRGA_TILE_STATUS_PENDING;
                                end
                                tile_status_tracker_wop_update = 'b1;

                                bsframe_op = OP_ACCEPT;
                            end
                            `PRGA_PKTCHAIN_MSG_TYPE_DATA,
                            `PRGA_PKTCHAIN_MSG_TYPE_DATA_CHECKSUM: begin
                                // bad. tile not initialized yet
                                err_tiles_next = err_tiles + 1;
                                tile_status_tracker_din = `PRGA_TILE_STATUS_ERROR;
                                tile_status_tracker_wop_update = 'b1;

                                {{ try_send_error(false)|indent(24) }}
                            end
                        endcase
                    end
                    `PRGA_TILE_STATUS_PROGRAMMING: begin
                        case (bsframe[`PRGA_PKTCHAIN_MSG_TYPE_INDEX])
                            `PRGA_PKTCHAIN_MSG_TYPE_DATA: begin
                                // good.
                                bsframe_op = OP_ACCEPT;
                            end
                            `PRGA_PKTCHAIN_MSG_TYPE_DATA_CHECKSUM: begin
                                // good.
                                init_tiles_next = init_tiles - 1;
                                pending_tiles_next = pending_tiles + 1;
                                tile_status_tracker_din = `PRGA_TILE_STATUS_PENDING;
                                tile_status_tracker_wop_update = 'b1;

                                bsframe_op = OP_ACCEPT;
                            end
                            `PRGA_PKTCHAIN_MSG_TYPE_DATA_INIT,
                            `PRGA_PKTCHAIN_MSG_TYPE_DATA_INIT_CHECKSUM: begin
                                // bad. tile already initialized
                                err_tiles_next = err_tiles + 1;
                                tile_status_tracker_din = `PRGA_TILE_STATUS_ERROR;
                                tile_status_tracker_wop_update = 'b1;

                                {{ try_send_error(false)|indent(24) }}
                            end
                        endcase
                    end
                    `PRGA_TILE_STATUS_PENDING,
                    `PRGA_TILE_STATUS_ERROR,
                    `PRGA_TILE_STATUS_DONE: begin
                        // bad.
                        {{ try_send_error(false)|indent(16) }}
                    end
                endcase

                if (bsframe_op == OP_ACCEPT) begin
                    if (~bsframe_fifo_full) begin
                        pkt_payload_next = bsframe[`PRGA_PKTCHAIN_PAYLOAD_INDEX];
                    end else begin
                        pkt_payload_next = bsframe[`PRGA_PKTCHAIN_PAYLOAD_INDEX] + 1;
                    end

                    if (pkt_payload_next > 0) begin
                        pkt_st_next = ST_FWD_PLD;
                    end else begin
                        pkt_st_next = ST_IDLE;
                    end
                end
            end
            ST_FWD_PLD: begin
                if (bsframe_val) begin
                    bsframe_op = OP_ACCEPT;

                    if (~bsframe_fifo_full) begin
                        pkt_payload_next = pkt_payload - 1;

                        if (pkt_payload == 1) begin
                            pkt_st_next = ST_IDLE;
                        end
                    end
                end
            end
            ST_DUMP_PLD: begin
                if (bsframe_val) begin
                    bsframe_op = OP_DROP;
                    pkt_payload_next = pkt_payload - 1;

                    if (pkt_payload == 1) begin
                        pkt_st_next = ST_IDLE;
                    end
                end
            end
            ST_ERR: begin
                errfifo_data_pkt = errfifo_data_pkt_f;

                {{ try_send_error(false)|indent(8) }}
            end
        endcase
    end

endmodule
