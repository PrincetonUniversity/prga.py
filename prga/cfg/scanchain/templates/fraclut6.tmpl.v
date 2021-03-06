// Automatically generated by PRGA's RTL generator
{%- set cfg_width = module.ports.cfg_i|length %}
`timescale 1ns/1ps
module fraclut6 (
    // user accessible ports
    input wire [5:0] in,
    output reg [0:0] o5,
    output reg [0:0] o6,

    // configuartion ports
    input wire [0:0] cfg_clk,
    input wire [0:0] cfg_e,
    input wire [0:0] cfg_we,
    input wire [{{ cfg_width - 1 }}:0] cfg_i,
    output wire [{{ cfg_width - 1 }}:0] cfg_o
    );

    wire [64:0] cfg_d;
    reg [5:0] internal_in;
    reg lut5A_out;

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
        if (in[{{ i }}] === 1'bx) begin
            internal_in[{{ i }}] = 1'b0;
        end
        {%- endfor %}
        // synopsys translate_on
    end

    always @* begin
        if (cfg_e) begin    // avoid program-time oscillation
            o5 = 1'b0;
            lut5A_out = 1'b0;
            o6 = 1'b0;
        end else begin
            case (internal_in[4:0])     // synopsys infer_mux
                {%- for i in range(32) %}
                5'd{{ i }}: begin
                    lut5A_out = cfg_d[{{ i }}];
                    o5 = cfg_d[{{ 32 + i }}];
                end
                {%- endfor %}
            endcase

            if (cfg_d[64]) begin
                case (internal_in[5])   // synopsys infer_mux
                    1'b0: o6 = lut5A_out;
                    1'b1: o6 = o5;
                endcase
            end else begin
                o6 = lut5A_out;
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
