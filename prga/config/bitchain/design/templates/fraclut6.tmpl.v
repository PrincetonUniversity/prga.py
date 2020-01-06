// Automatically generated by PRGA's RTL generator
module fraclut6 (
    // user-accessible ports
    input wire [5:0] in,
    output reg [0:0] o6,
    output reg [0:0] o5,

    // config ports
    input wire [0:0] cfg_clk,
    input wire [0:0] cfg_e,
    input wire [0:0] cfg_we,
    input wire [0:0] cfg_i,
    output wire [0:0] cfg_o
    );

    // mode enum
    localparam MODE_LUT6 = 1'd0;
    localparam MODE_LUT5X2 = 1'd1;

    // prog bits
    reg [64:0] cfg_d;

    // decode prog bits
    wire mode;
    wire [63:0] data;

    assign mode = cfg_d[64];
    assign data = cfg_d[63:0];

    // convert 'x' inputs to '0' in simulation
    reg [5:0] internal_in;

    always @* begin
        internal_in = in;

        // synopsys translate_off
        {%- for i in range(6) %}
        if (in[{{ i }}] === 1'bx || in[{{ i }}] === 1'bz) begin
            internal_in[{{ i }}] = 1'b0;
        end
        {%- endfor %}
        // synopsys translate_on
    end

    // lut5 output
    reg [1:0] internal_lut5;
    {%- for i in range(2) %}
    always @* begin
        case (internal_in[4:0])  // synopsys infer_mux
            {%- for j in range(32) %}
            5'd{{ j }}: begin
                internal_lut5[{{ i }}] = data[{{ 32 * i + j }}];
            end
            {%- endfor %}
        endcase
    end
    {%- endfor %}

    // lut6 and lut5
    always @* begin
        o5 = internal_lut5[1];
        case (mode)             // synopsys infer_mux
            MODE_LUT5X2: begin
                o6 = internal_lut5[0];
            end
            MODE_LUT6: begin
                case (internal_in[5])    // synopsys infer_mux
                    1'b0: begin
                        o6 = internal_lut5[0];
                    end
                    1'b1: begin
                        o6 = internal_lut5[1];
                    end
                endcase
            end
        endcase
    end

    always @(posedge cfg_clk) begin
        if (cfg_e && cfg_we) begin    // configuring
            cfg_d <= {cfg_d, cfg_i};
        end
    end

    assign cfg_o = cfg_d[64];

endmodule

