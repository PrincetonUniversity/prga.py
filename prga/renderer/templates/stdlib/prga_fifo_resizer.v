// Automatically generated by PRGA's RTL generator
`include "prga_utils.vh"
module prga_fifo_resizer #(
    parameter DATA_WIDTH = 32,
    parameter INPUT_MULTIPLIER = 1,
    parameter OUTPUT_MULTIPLIER = 1,
    parameter INPUT_LOOKAHEAD = 0,
    parameter OUTPUT_LOOKAHEAD = 0
) (
    input wire [0:0] clk,
    input wire [0:0] rst,

    input wire [0:0] empty_i,
    output wire [0:0] rd_i,
    input wire [DATA_WIDTH * INPUT_MULTIPLIER - 1:0] dout_i,

    output wire [0:0] empty,
    input wire [0:0] rd,
    output reg [DATA_WIDTH * OUTPUT_MULTIPLIER - 1:0] dout
    );

    generate if (INPUT_MULTIPLIER == 1 && OUTPUT_MULTIPLIER == 1) begin
        if (INPUT_LOOKAHEAD == OUTPUT_LOOKAHEAD) begin
            // Do nothing
            assign rd_i = rd;
            assign empty = empty_i;
            assign dout = dout_i;
        end else begin
            prga_fifo_lookahead_buffer #(
                .DATA_WIDTH         (DATA_WIDTH)
                ,.REVERSED          (INPUT_LOOKAHEAD)
            ) buffer (
                .clk                (clk)
                ,.rst               (rst)
                ,.empty_i           (empty_i)
                ,.rd_i              (rd_i)
                ,.dout_i            (dout_i)
                ,.empty             (empty)
                ,.rd                (rd)
                ,.dout              (dout)
                );
        end
    end else if ((INPUT_MULTIPLIER <= 0 || INPUT_MULTIPLIER > 1) && (OUTPUT_MULTIPLIER <= 0 || OUTPUT_MULTIPLIER > 1)) begin
        // At least one of INPUT_MULTIPLIER and OUTPUT_MULTIPLIER must be 1 and the other must be a positive integer.
        __PRGA_PARAMETERIZATION_ERROR__ __error__();
    end else begin
        // convert input to look-ahead
        wire empty_i_internal;
        wire [DATA_WIDTH * INPUT_MULTIPLIER - 1:0] dout_i_internal;
        wire rd_i_internal;

        if (INPUT_LOOKAHEAD) begin
            assign empty_i_internal = empty_i;
            assign dout_i_internal = dout_i;
            assign rd_i = rd_i_internal;
        end else begin
            prga_fifo_lookahead_buffer #(
                .DATA_WIDTH         (INPUT_MULTIPLIER * DATA_WIDTH)
                ,.REVERSED          (0)
            ) buffer (
                .clk                (clk)
                ,.rst               (rst)
                ,.empty_i           (empty_i)
                ,.rd_i              (rd_i)
                ,.dout_i            (dout_i)
                ,.empty             (empty_i_internal)
                ,.rd                (rd_i_internal)
                ,.dout              (dout_i_internal)
                );
        end

        // build shift pipeline
        reg [DATA_WIDTH * (INPUT_MULTIPLIER + OUTPUT_MULTIPLIER - 1) - 1:0] pipebuf;
        reg [`CLOG2(INPUT_MULTIPLIER + OUTPUT_MULTIPLIER):0] counter;

        always @(posedge clk) begin
            if (rst) begin
                pipebuf <= 'b0;
                counter <= 'b0;
            end else begin
                case ({~empty_i_internal && rd_i_internal, ~empty && rd})
                    2'b01: begin
                        pipebuf <= pipebuf << (DATA_WIDTH * OUTPUT_MULTIPLIER);
                        counter <= counter - OUTPUT_MULTIPLIER;
                    end
                    2'b10: begin
                        pipebuf <= {pipebuf, dout_i_internal};
                        counter <= counter + INPUT_MULTIPLIER;
                    end
                    2'b11: begin
                        pipebuf <= {pipebuf, dout_i_internal};
                        counter <= counter + INPUT_MULTIPLIER - OUTPUT_MULTIPLIER;
                    end
                endcase
            end
        end

        assign empty = counter < OUTPUT_MULTIPLIER;
        assign rd_i_internal = counter < OUTPUT_MULTIPLIER || (counter == OUTPUT_MULTIPLIER && rd);

        if (OUTPUT_LOOKAHEAD) begin
            always @* begin
                dout = pipebuf[DATA_WIDTH * (INPUT_MULTIPLIER + OUTPUT_MULTIPLIER - 1) - 1 -: DATA_WIDTH * OUTPUT_MULTIPLIER];
            end
        end else begin
            always @(posedge clk) begin
                dout <= pipebuf[DATA_WIDTH * (INPUT_MULTIPLIER + OUTPUT_MULTIPLIER - 1) - 1 -: DATA_WIDTH * OUTPUT_MULTIPLIER];
            end
        end
    end endgenerate

endmodule
