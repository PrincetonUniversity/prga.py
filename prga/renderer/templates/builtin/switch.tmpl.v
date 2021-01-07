// Automatically generated by PRGA's RTL generator
{% set width = module.ports.i|length -%}
{% set sel_width = module.ports.prog_data|length -%}
`timescale 1ns/1ps
module {{ module.name }} (
    input wire [{{ width - 1 }}:0] i
    , output reg [0:0] o

    , input wire [0:0] prog_done
    , input wire [{{ sel_width - 1}}:0] prog_data
    );

    always @* begin
        if (~prog_done) begin
            o = 1'b0;
        end else begin
            o = 1'b0;   // if ``prog_data == 0`` or ``prog_data`` out of bound, output 0
            case (prog_data)
                {%- for i in range(width) %}
                {{ sel_width }}'d{{ i + 1 }}: o = i[{{ i }}];
                {%- endfor %}
            endcase
        end
    end

endmodule