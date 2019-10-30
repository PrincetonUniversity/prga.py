// Automatically generated by PRGA's RTL generator
`define CLOCK_INVERSION 0
`define CE_INVERSION 1
`define SR_INVERSION 2
`define LUT5A_DATA 34:3
`define LUT5B_DATA 66:35
`define LUT6_ENABLE 67
`define CARRY_SOURCE_G 68
`define CARRY_SOURCE_CIN 70:69
`define FFA_SOURCE 72:71
`define FFA_ENABLE_CE 73
`define FFA_ENABLE_SR 74
`define FFA_SR_SET 75
`define FFB_SOURCE 77:76
`define FFB_ENABLE_CE 78
`define FFB_ENABLE_SR 79
`define FFB_SR_SET 80
`define OB_SEL 82:81
`define NUM_CFG_BITS 83

module fraclut6sffc (
    // user-accessible ports
    input wire [0:0] clk,   // clock
    input wire [0:0] ce,    // clock enable
    input wire [0:0] sr,    // set/reset
    input wire [5:0] ia,    // input A
    input wire [0:0] ib,    // input B
    input wire [0:0] cin,   // carry in
    output wire [0:0] cout, // carry out
    output reg [0:0] oa,    // output A
    output reg [0:0] ob,    // output B
    output reg [0:0] q,     // output Q

    // config ports
    input wire [0:0] cfg_clk,
    input wire [0:0] cfg_e,
    input wire [0:0] cfg_we,
    input wire [0:0] cfg_i,
    output wire [0:0] cfg_o
    );

    // selector for the carry in of the carry chain
    localparam CARRY_CIN_CIN = 2'd0;
    localparam CARRY_CIN_IB = 2'd2;
    localparam CARRY_CIN_O5 = 2'd3;

    // selector for the input 'g' of carry chain
    localparam CARRY_G_IB = 1'd0;
    localparam CARRY_G_O5 = 1'd1;

    // selector for the source of flip-flop A
    localparam FFA_COUT = 2'd0;
    localparam FFA_S = 2'd1;
    localparam FFA_O6 = 2'd2;
    localparam FFA_O5 = 2'd3;

    // selector for the source of flip-flop B
    localparam FFB_COUT = 2'd0;
    localparam FFB_S = 2'd1;
    localparam FFB_IB = 2'd2;
    localparam FFB_O5 = 2'd3;

    // selector for output OB
    localparam OB_COUT = 2'd0;
    localparam OB_S = 2'd1;
    localparam OB_QB = 2'd2;
    localparam OB_O5 = 2'd3;

    // ----------------------------------------------------------------------
    // -- Configuration -----------------------------------------------------
    // ----------------------------------------------------------------------
    reg [`NUM_CFG_BITS - 1:0] cfg_d;

    always @(posedge cfg_clk) begin
        if (cfg_e && cfg_we) begin    // configuring
            cfg_d <= {cfg_d, cfg_i};
        end
    end

    assign cfg_o = cfg_d[`NUM_CFG_BITS - 1];

    // ----------------------------------------------------------------------
    // -- invert clock, CE & SR ---------------------------------------------
    // ----------------------------------------------------------------------
    wire internal_clk, internal_ce, internal_sr;
    assign internal_clk = cfg_d[`CLOCK_INVERSION] ? ~clk : clk;
    assign internal_ce = cfg_d[`CE_INVERSION] ? ~ce : ce;
    assign internal_sr = cfg_d[`SR_INVERSION] ? ~sr : sr;

    // ----------------------------------------------------------------------
    // -- LUTs --------------------------------------------------------------
    // ----------------------------------------------------------------------
    // decode prog bits
    wire [31:0] lut_data [0:1];
    assign lut_data[0] = cfg_d[`LUT5A_DATA];
    assign lut_data[1] = cfg_d[`LUT5B_DATA];

    // convert 'x' inputs to '0' in simulation
    reg [5:0] internal_in;

    always @* begin
        internal_in = ia;

        // synopsys translate off
        {%- for i in range(6) %}
        if (ia[{{ i }}] === 1'bx || ia[{{ i }}] === 1'bz) begin
            internal_in[{{ i }}] = 1'b0;
        end
        {%- endfor %}
        // synopsys translate on
    end

    // lut5 output
    reg [1:0] internal_lut5;
    {%- for i in range(2) %}
    always @* begin
        case (internal_in[4:0])  // synopsys infer_mux
            {%- for j in range(32) %}
            5'd{{ j }}: internal_lut5[{{ i }}] = lut_data[{{ i }}][{{ j }}];
            {%- endfor %}
        endcase
    end
    {%- endfor %}

    // lut6 output
    always @* begin
        if (cfg_d[`LUT6_ENABLE]) begin
            case (internal_in[5]) // synopsys infer_mux
                1'b0: oa = internal_lut5[0];
                1'b1: oa = internal_lut5[1];
            endcase
        end else begin
            oa = internal_lut5[0];
        end
    end

    // ----------------------------------------------------------------------
    // -- Carry Chain -------------------------------------------------------
    // ----------------------------------------------------------------------
    // input g
    reg internal_carry_g;

    always @* begin
        internal_carry_g = ib;

        case (cfg_d[`CARRY_SOURCE_G])
            CARRY_G_IB: internal_carry_g = ib;
            CARRY_G_O5: internal_carry_g = internal_lut5[1];
        endcase
    end

    // carry in
    reg internal_carry_cin;

    always @* begin
        internal_carry_cin = cin;

        case (cfg_d[`CARRY_SOURCE_CIN])
            CARRY_CIN_CIN: internal_carry_cin = cin;
            CARRY_CIN_IB: internal_carry_cin = ib;
            CARRY_CIN_O5: internal_carry_cin = internal_lut5[1];
        endcase
    end

    // carry
    wire s;
    assign cout = internal_carry_g || (oa && internal_carry_cin);
    assign s = oa ^ internal_carry_cin;

    // ----------------------------------------------------------------------
    // -- Flip-flop A -------------------------------------------------------
    // ----------------------------------------------------------------------
    always @(posedge internal_clk) begin
        if (cfg_d[`FFA_ENABLE_SR] && internal_sr && cfg_d[`FFA_SR_SET]) begin
            q <= 1'b1;
        end else if (cfg_d[`FFA_ENABLE_SR] && internal_sr && ~cfg_d[`FFA_SR_SET]) begin
            q <= 1'b0;
        end else if (~cfg_d[`FFA_ENABLE_CE] || internal_ce) begin
            case (cfg_d[`FFA_SOURCE])
                FFA_COUT: q <= cout;
                FFA_S: q <= s;
                FFA_O6: q <= oa;
                FFA_O5: q <= internal_lut5[1];
            endcase
        end
    end

    // ----------------------------------------------------------------------
    // -- Flip-flop B -------------------------------------------------------
    // ----------------------------------------------------------------------
    reg ffb;
    always @(posedge internal_clk) begin
        if (cfg_d[`FFB_ENABLE_SR] && internal_sr && cfg_d[`FFB_SR_SET]) begin
            ffb <= 1'b1;
        end else if (cfg_d[`FFB_ENABLE_SR] && internal_sr && ~cfg_d[`FFB_SR_SET]) begin
            ffb <= 1'b0;
        end else if (~cfg_d[`FFB_ENABLE_CE] || internal_ce) begin
            case (cfg_d[`FFB_SOURCE])
                FFB_COUT: ffb <= cout;
                FFB_S: ffb <= s;
                FFB_IB: ffb <= ib;
                FFB_O5: ffb <= internal_lut5[1];
            endcase
        end
    end

    // ----------------------------------------------------------------------
    // -- OB ----------------------------------------------------------------
    // ----------------------------------------------------------------------
    always @* begin
        case (cfg_d[`OB_SEL])
            OB_COUT: ob = cout;
            OB_S: ob = s;
            OB_QB: ob = ffb;
            OB_O5: ob = internal_lut5[1];
        endcase
    end

endmodule

