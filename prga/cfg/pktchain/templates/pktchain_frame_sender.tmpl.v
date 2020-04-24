// Automatically generated by PRGA's RTL generator
{%- set frame_size = 32 %}
{%- set phit_width = module.phit_width %}
{%- set num_phits_per_frame = frame_size // phit_width %}
`define PHIT_WIDTH {{ phit_width }}
`define FRAME_SIZE {{ frame_size }}
module pktchain_frame_sender #(
    parameter DEPTH_LOG2 = 1
) (
    input wire [0:0] cfg_clk,
    input wire [0:0] cfg_rst,

    output reg [0:0] frame_full,
    input wire [0:0] frame_wr,
    input wire [`FRAME_SIZE - 1:0] frame_i,

    output reg [0:0] phit_wr,
    input wire [0:0] phit_full,
    output reg [`PHIT_WIDTH - 1:0] phit_o
    );

    {% if frame_size % phit_width != 0 %}
    // The frame size ({{ frame_size }}) is not a multiple of phit width ({{ phit_width }})
    __PRGA_RTLGEN_ERROR__ __PKTCHAIN_UNSUPPORTED_PHIT_WIDTH__();
    {%- endif %}
    localparam  NUM_PHITS_PER_FRAME = `FRAME_SIZE / `PHIT_WIDTH;
    localparam  PHIT_COUNTER_WIDTH  = {{ (num_phits_per_frame - 1).bit_length() }}; // $clog2(NUM_PHITS_PER_FRAME)
    localparam  FIFO_DEPTH = 1 << DEPTH_LOG2;

    reg [`FRAME_SIZE - 1:0] data [FIFO_DEPTH - 1:0];
    reg [PHIT_COUNTER_WIDTH - 1:0] phit_counter;
    reg [DEPTH_LOG2:0] wr_ptr, rd_ptr;

    wire [`PHIT_WIDTH - 1:0] phits [NUM_PHITS_PER_FRAME - 1:0];
    {%- for i in range(num_phits_per_frame) %}
    assign phits[{{ i }}] = data[rd_ptr[0 +: DEPTH_LOG2]][{{ num_phits_per_frame - 1 - i }} * `PHIT_WIDTH +: `PHIT_WIDTH];
    {%- endfor %}

    always @(posedge cfg_clk or posedge cfg_rst) begin
        if (cfg_rst) begin
            phit_counter <= 'b0;
            wr_ptr <= 'b0;
            rd_ptr <= 'b0;
        end else begin
            if (~frame_full && frame_wr) begin
                data[wr_ptr[0 +: DEPTH_LOG2]] <= frame_i;
                wr_ptr <= wr_ptr + 1;
            end

            if (~phit_full && phit_wr) begin
                if (phit_counter == NUM_PHITS_PER_FRAME - 1) begin
                    phit_counter <= 'b0;
                    rd_ptr <= rd_ptr + 1;
                end else begin
                    phit_counter <= phit_counter + 1;
                end
            end
        end
    end

    always @* begin
        frame_full = cfg_rst || rd_ptr == {~wr_ptr[DEPTH_LOG2], wr_ptr[0 +: DEPTH_LOG2]};
        phit_wr = cfg_rst ||rd_ptr != wr_ptr;
        phit_o = phits[phit_counter];
    end

endmodule
