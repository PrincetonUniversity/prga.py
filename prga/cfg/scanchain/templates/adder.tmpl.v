// Automatically generated by PRGA's RTL generator
{%- set cfg_width = module.ports.cfg_i|length %}
`timescale 1ns/1ps
module adder (
    // user accessible ports
    input wire [0:0] a,
    input wire [0:0] b,
    input wire [0:0] cin_fabric,
    input wire [0:0] cin,

    output reg [0:0] cout,
    output reg [0:0] s,
    output wire [0:0] cout_fabric,

    // configuartion ports
    input wire [0:0] cfg_clk,
    input wire [0:0] cfg_e,
    input wire [0:0] cfg_we,
    input wire [{{ cfg_width - 1 }}:0] cfg_i,
    output wire [{{ cfg_width - 1 }}:0] cfg_o
    );

    localparam CIN_FABRIC = 0;

    reg [0:0] cfg_d;

    always @* begin
        if (cfg_e) begin    // avoid program-time oscillation
            s = 1'b0;
            cout = 1'b0;
        end else begin
            if (cfg_d[CIN_FABRIC]) begin
                {cout, s} = a + b + cin_fabric;
            end else begin
                {cout, s} = a + b + cin;
            end
        end
    end

    assign cout_fabric = cout;

    wire [{{ 0 + cfg_width }}:0] cfg_d_next;

    always @(posedge cfg_clk) begin
        if (cfg_e && cfg_we) begin
            cfg_d <= cfg_d_next;
        end
    end

    assign cfg_d_next = {{ '{' -}} cfg_d, cfg_i {{- '}' }};
    assign cfg_o = cfg_d_next[{{ 0 + cfg_width }} -: {{ cfg_width }}];

endmodule
