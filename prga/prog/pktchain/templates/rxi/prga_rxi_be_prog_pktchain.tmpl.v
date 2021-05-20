// Automatically generated by PRGA's RTL generator

`include "prga_rxi.vh"
`include "prga_rxi_pktchain.vh"

module prga_rxi_be_prog_pktchain (
    input wire                                      clk
    , input wire                                    rst_n

    // == CTRL <-> PROG =======================================================
    , output wire                                   prog_req_rdy
    , input wire                                    prog_req_vld
    , input wire [`PRGA_RXI_PROG_REG_ID_WIDTH-1:0]  prog_req_addr
    , input wire [`PRGA_RXI_DATA_BYTES-1:0]         prog_req_strb
    , input wire [`PRGA_RXI_DATA_WIDTH-1:0]         prog_req_data

    , output reg                                    prog_resp_vld
    , input wire                                    prog_resp_rdy
    , output reg                                    prog_resp_err
    , output reg [`PRGA_RXI_DATA_WIDTH-1:0]         prog_resp_data

    // == PROG <-> FABRIC =====================================================
    , output wire                                   prog_rst
    , output wire                                   prog_done

    // configuration output
    , input wire                                    phit_o_full
    , output wire                                   phit_o_wr
    , output wire [`PRGA_PKTCHAIN_PHIT_WIDTH - 1:0] phit_o

    // configuration input
    , output wire                                   phit_i_full
    , input wire                                    phit_i_wr
    , input wire [`PRGA_PKTCHAIN_PHIT_WIDTH - 1:0]  phit_i
    );

    // =======================================================================
    // -- Timing-decoupled Input ---------------------------------------------
    // =======================================================================
    wire req_rdy_p, req_vld_f;
    wire [`PRGA_RXI_PROG_REG_ID_WIDTH-1:0] req_addr_f;
    wire [`PRGA_RXI_DATA_BYTES-1:0]        req_strb_f;
    wire [`PRGA_RXI_DATA_WIDTH-1:0]        req_data_f;

    prga_valrdy_buf #(
        .REGISTERED             (1)
        ,.DECOUPLED             (1)
        ,.DATA_WIDTH            (
            `PRGA_RXI_PROG_REG_ID_WIDTH
            + `PRGA_RXI_DATA_BYTES
            + `PRGA_RXI_DATA_WIDTH
        )
    ) req_valrdy_buf (
        .clk                (clk)
        ,.rst               (~rst_n)
        ,.rdy_o             (prog_req_rdy)
        ,.val_i             (req_val)
        ,.data_i            ({
            prog_req_addr
            , prog_req_strb
            , prog_req_data
        })
        ,.rdy_i             (req_rdy_p)
        ,.val_o             (req_vld_f)
        ,.data_o            ({
            req_addr_f
            , req_strb_f
            , req_data_f
        })
        );

    wire resp_rdy_f;
    reg resp_vld_p, resp_err_p;
    reg [`PRGA_RXI_DATA_WIDTH-1:0] resp_data_p;

    prga_valrdy_buf #(
        .REGISTERED         (1)
        ,.DECOUPLED         (1)
        ,.DATA_WIDTH        (`PRGA_RXI_DATA_WIDTH + 1)
    ) resp_valrdy_buf (
        .clk                (clk)
        ,.rst               (~rst_n)
        ,.rdy_o             (resp_rdy_f)
        ,.val_i             (resp_vld_p)
        ,.data_i            ({resp_err_p, resp_data_p})
        ,.rdy_i             (prog_resp_rdy)
        ,.val_o             (prog_resp_vld)
        ,.data_o            ({prog_resp_err, prog_resp_data})
        );

    // =======================================================================
    // -- Error Flags --------------------------------------------------------
    // =======================================================================

    wire err_resp_inval, err_bitstream_corrupted, err_bitstream_incomplete, err_bitstream_redundant;
    wire any_err;
    reg err_unsynced;

    assign any_err = err_resp_inval
                     || err_bitstream_corrupted
                     || err_bitstream_incomplete
                     || err_bitstream_redundant;

    always @(posedge clk) begin
        if (~rst_n) begin
            err_unsynced <= 1'b0;
        end else if (any_err) begin
            err_unsynced <= 1'b1;
        end else if (resp_vld_p && resp_rdy_f && resp_err_p) begin
            err_unsynced <= 1'b0;
        end
    end

    // =======================================================================
    // -- Bitstream Frame Input ----------------------------------------------
    // =======================================================================

    // == Register Frame ==
    wire [`PRGA_PKTCHAIN_FRAME_SIZE - 1:0] frame_i;
    wire frame_i_empty, frame_i_full, frame_i_rd;
    reg frame_i_wr;

    // use a FIFO resizer if RXI data size is 8B
    generate if (`PRGA_RXI_DATA_BYTES_LOG2 == 3) begin

        // == raw data fifo ==
        wire [`PRGA_RXI_DATA_WIDTH + `PRGA_RXI_DATA_BYTES - 1:0] rawq_din, rawq_dout;
        wire rawq_full, rawq_empty, rawq_rd;

        // put byte enable close to each byte (so the resizer can grab those correctly)
        genvar disasm_i;
        for (disasm_i = 0; disasm_i < `PRGA_RXI_DATA_BYTES; disasm_i = disasm_i + 1) begin: raw_disasm
            assign rawq_din[disasm_i * 9 +: 9] = {req_strb_f[disasm_i], req_data_f[disasm_i * 8 +: 8]};
        end

        prga_fifo #(
            .DATA_WIDTH             (`PRGA_RXI_DATA_WIDTH + `PRGA_RXI_DATA_BYTES)
            ,.LOOKAHEAD             (0)
        ) i_rawq (
            .clk                    (clk)
            ,.rst                   (~rst_n)
            ,.full                  (frame_i_full)
            ,.wr                    (frame_i_wr)
            ,.din                   (rawq_din)
            ,.empty                 (rawq_empty)
            ,.rd                    (rawq_rd)
            ,.dout                  (rawq_dout)
            );

        // == Resizer ==
        localparam  FRAME_BYTES = 1 << (`PRGA_PKTCHAIN_FRAME_SIZE_LOG2 - 3);

        wire [`PRGA_PKTCHAIN_FRAME_SIZE + FRAME_BYTES - 1:0] resizer_dout;
        wire resizer_empty, resizer_rd;

        prga_fifo_resizer #(
            .DATA_WIDTH             (`PRGA_PKTCHAIN_FRAME_SIZE + FRAME_BYTES)
            ,.INPUT_MULTIPLIER      (`PRGA_RXI_DATA_WIDTH / `PRGA_PKTCHAIN_FRAME_SIZE)
            ,.INPUT_LOOKAHEAD       (0)
            ,.OUTPUT_LOOKAHEAD      (1)
        ) i_resizer (
            .clk                    (clk)
            ,.rst                   (~rst_n)
            ,.empty_i               (rawq_empty)
            ,.rd_i                  (rawq_rd)
            ,.dout_i                (rawq_dout)
            ,.empty                 (resizer_empty)
            ,.rd                    (resizer_rd)
            ,.dout                  (resizer_dout)
            );

        // re-assemble bitstream frame
        wire [FRAME_BYTES - 1:0] frame_tmp_mask;
        wire [`PRGA_PKTCHAIN_FRAME_SIZE - 1:0] frame_tmp;

        genvar asm_i;
        for (asm_i = 0; asm_i < FRAME_BYTES; asm_i = asm_i + 1) begin: bsframe_asm
            assign {frame_tmp_mask[asm_i], frame_tmp[asm_i * 8 +: 8]} = resizer_dout[asm_i * 9 +: 9];
        end

        // == Register Frame ==
        reg [`PRGA_PKTCHAIN_FRAME_SIZE - 1:0] frame_if;
        reg frame_i_empty_f;

        always @(posedge clk) begin
            if (~rst_n) begin
                frame_i_empty_f <= 1'b1;
                frame_if <= { `PRGA_PKTCHAIN_FRAME_SIZE {1'b0} };
            end else if (frame_i_empty_f || frame_i_rd) begin
                if (~resizer_empty && (&frame_tmp_mask)) begin
                    frame_i_empty_f <= 1'b0;
                    frame_i <= frame_tmp;
                end else begin
                    frame_i_empty_f <= 1'b1;
                end
            end
        end

        assign resizer_rd = ~( (&frame_tmp_mask) && frame_i_val && frame_i_stall );
        assign frame_i = frame_if;
        assign frame_i_empty = frame_i_empty_f;

    end else begin

        prga_fifo #(
            .DATA_WIDTH             (`PRGA_RXI_DATA_WIDTH)
            ,.LOOKAHEAD             (1)
        ) i_frame_iq (
            .clk                    (clk)
            ,.rst                   (~rst_n)
            ,.full                  (frame_i_full)
            ,.wr                    (frame_i_wr && &req_strb_f)
            ,.din                   (req_data_f)
            ,.empty                 (frame_i_empty)
            ,.rd                    (frame_i_rd)
            ,.dout                  (frame_i)
            );

    end endgenerate

    // =======================================================================
    // -- RXI Interface ------------------------------------------------------
    // =======================================================================

    reg rxi_stall;

    localparam  ST_RXI_WIDTH                = 2;
    localparam  ST_RXI_RST                  = 2'h0,
                ST_RXI_NORMAL               = 2'h1,
                ST_RXI_ERR_SENT             = 2'h2;

    reg [ST_RXI_WIDTH-1:0]      rxi_state, rxi_state_next;

    always @(posedge clk) begin
        if (~rst_n) begin
            rxi_state    <= ST_RXI_RST;
        end else begin
            rxi_state    <= rxi_state_next;
        end
    end

    assign req_rdy_p = rst_n && ~rxi_stall;

    // == Main FSM ==
    always @* begin
        rxi_state_next = rxi_state;
        rxi_stall = 1'b1;

        frame_i_wr = 1'b0;
        resp_vld_p = 1'b0;
        resp_err_p = 1'b0;
        resp_data_p = {`PRGA_RXI_DATA_WIDTH {1'b0} };

        case (rxi_state)
            ST_RXI_RST: begin
                rxi_state_next = ST_RXI_NORMAL;
            end
            ST_RXI_NORMAL: if (err_unsynced) begin
                resp_vld_p = 1'b1;
                resp_err_p = 1'b1;
                resp_data_p = err_resp_inval ? `PRGA_RXI_ERRCODE_PKTCHAIN_RESP_INVAL : 
                              err_bitstream_corrupted ? `PRGA_RXI_ERRCODE_PKTCHAIN_BITSTREAM_CORRUPTED :
                              err_bitstream_incomplete ? `PRGA_RXI_ERRCODE_PKTCHAIN_BITSTREAM_INCOMPLETE :
                              err_bitstream_redundant ? `PRGA_RXI_ERRCODE_PKTCHAIN_BITSTREAM_REDUNDANT :
                                                        { `PRGA_RXI_DATA_WIDTH {1'b0} };

                if (resp_rdy_f)
                    rxi_state_next = ST_RXI_ERR_SENT;
            end else begin
                case (req_addr_f)
                    `PRGA_RXI_PROGID_PKTCHAIN_BITSTREAM: begin
                        rxi_stall = req_vld_f && (~resp_rdy_f || (|req_strb_f && frame_i_full));
                        frame_i_wr = req_vld_f && resp_rdy_f && |req_strb_f;
                        resp_vld_p = req_vld_f && ~(|req_strb_f && frame_i_full);
                    end
                    default: begin
                        rxi_stall = ~resp_rdy_f;
                        resp_vld_p = req_vld_f;
                    end
                endcase
            end
            ST_RXI_ERR_SENT: begin
                rxi_stall = ~resp_rdy_f;
                resp_vld_p = req_vld_f;
            end
        endcase
    end

    pktchain_ctrl i_ctrl (
        .clk                        (clk)
        ,.rst_n                     (rst_n)
        ,.frame_i_val               (frame_i_val)
        ,.frame_i                   (frame_i)
        ,.frame_i_stall             (frame_i_stall)
        ,.err_resp_inval            (err_resp_inval)
        ,.err_bitstream_corrupted   (err_bitstream_corrupted)
        ,.err_bitstream_incomplete  (err_bitstream_incomplete)
        ,.err_bitstream_redundant   (err_bitstream_redundant)
        ,.prog_rst                  (prog_rst)
        ,.prog_done                 (prog_done)
        ,.phit_o_full               (phit_o_full)
        ,.phit_o_wr                 (phit_o_wr)
        ,.phit_o                    (phit_o)
        ,.phit_i_full               (phit_i_full)
        ,.phit_i_wr                 (phit_i_wr)
        ,.phit_i                    (phit_i)
        );

endmodule