// Automatically generated by PRGA's RTL generator
{%- set cfg_width = module.ports.cfg_i|length %}
`timescale 1ns/1ps
module fle6 (
    // user accessible ports
    input wire [0:0] clk,
    input wire [5:0] bits_in,
    output reg [1:0] out,
    input wire [0:0] cin,
    output reg [0:0] cout,

    // configuartion ports
    input wire [0:0] cfg_clk,
    input wire [0:0] cfg_e,
    input wire [0:0] cfg_we,
    input wire [{{ cfg_width - 1 }}:0] cfg_i,
    output wire [{{ cfg_width - 1 }}:0] cfg_o,
    
    // Variables for testbench files
    input wire test_clk
    );

    // 3 modes:
    //  1. LUT6 + optional DFF
    //  2. 2x (LUT5 + optional DFF)
    //  3. 2x LUT => adder => optional DFF for sum & cout_fabric
    
    localparam LUT5A_DATA_WIDTH = 32;
    localparam LUT5B_DATA_WIDTH = 32;
    localparam MODE_WIDTH = 2;

    localparam MODE_LUT6X1 = 2'd0;
    localparam MODE_LUT5X2 = 2'd1;
    localparam MODE_ARITH = 2'd3;

    localparam LUT5A_DATA = 0;
    localparam LUT5B_DATA = LUT5A_DATA + LUT5A_DATA_WIDTH;
    localparam DISABLE_FFA = LUT5B_DATA + LUT5B_DATA_WIDTH;
    localparam DISABLE_FFB = DISABLE_FFA + 1;
    localparam MODE = DISABLE_FFB + 1;
    localparam CIN_FABRIC = MODE + MODE_WIDTH;
    localparam CFG_BITCOUNT = CIN_FABRIC + 1;
    
    wire [CFG_BITCOUNT - 1:0] cfg_d;
    reg [5:0] internal_in;
    reg [1:0] internal_lut;
    reg [1:0] internal_ff;

    // synopsys translate_off
    // in case the sensitivity list is never triggered
    initial begin
        internal_in = 6'b0;
    end
    // synopsys translate_on

    always @* begin
        internal_in = in;

        // synopsys translate_off
        // in simulation, force unconnected LUT input to be zeros
        {%- for i in range(6) %}
        if (bits_in[{{ i }}] === 1'bx) begin
            internal_in[{{ i }}] = 1'b0;
        end
        {%- endfor %}
        // synopsys translate_on
    end

    wire [1:0] internal_sum;
    assign internal_sum = internal_lut[0] + internal_lut[1] + (cfg_d[CIN_FABRIC] ? internal_in[5] : cin);

    wire [MODE_WIDTH-1:0] mode;
    assign mode = cfg_d[MODE +: MODE_WIDTH];

    always @(posedge clk) begin
        if (cfg_e) begin
            internal_ff <= 2'b0;
        end else if (mode == MODE_ARITH) begin
            internal_ff <= internal_sum;
        end else if (mode == MODE_LUT6X1) begin
            internal_ff[0] <= internal_in[5] ? internal_lut[1] : internal_lut[0];
            internal_ff[1] <= 1'b0;
        end else begin
            internal_ff <= internal_lut;
        end
    end

    always @* begin
        if (cfg_e) begin    // avoid program-time oscillating
            internal_lut = 2'b0;
        end else begin
            case (internal_in[4:0])     // synopsys infer_mux
                {%- for i in range(32) %}
                5'd{{ i }}: begin
                    internal_lut[0] = cfg_d[LUT5A_DATA + {{ i }}];
                    internal_lut[1] = cfg_d[LUT5B_DATA + {{ i }}];
                end
                {%- endfor %}
            endcase
        end
    end

    always @* begin
        if (cfg_e) begin    // avoid program-time oscillating
            out = 2'b0;
            cout = 1'b0;
        end else begin
            if (mode == MODE_ARITH) begin
                cout = internal_sum[1];
            end else begin
                cout = 1'b0;
            end

            if (cfg_d[DISABLE_FFA]) begin
                out[0] = 'b0;

                case (mode)
                    MODE_LUT6X1: begin
                        out[0] = internal_in[5] ? internal_lut[1] : internal_lut[0];
                    end
                    MODE_LUT5X2: begin
                        out[0] = internal_lut[0];
                    end
                    MODE_ARITH: begin
                        out[0] = internal_sum[0];
                    end
                endcase
            end else begin
                out[0] = internal_ff[0];
            end

            if (cfg_d[DISABLE_FFB]) begin
                out[1] = 'b0;

                case (mode)
                    MODE_LUT5X2: begin
                        out[1] = internal_lut[1];
                    end
                    MODE_ARITH: begin
                        out[1] = internal_sum[1];
                    end
                endcase
            end else begin
                out[1] = internal_ff[1];
            end
        end
    end

    {{ module.instances.i_cfg_data.model.name }} i_cfg_data (
        .cfg_clk            (cfg_clk)
        ,.cfg_e             (cfg_e)
        ,.cfg_we            (cfg_we)
        ,.cfg_i             (cfg_i)
        ,.cfg_o             (cfg_o)
        ,.cfg_d             (cfg_d)
        );

endmodule
