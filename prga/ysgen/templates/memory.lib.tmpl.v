{% macro memport(portsuffix, addr_width) -%}
    , input wire [{{ addr_width - 1 }}:0] addr{{ portsuffix }}
    , input wire [0:0] data{{ portsuffix }}
    , input wire [0:0] we{{ portsuffix }}
    , output reg [0:0] out{{ portsuffix }}
{%- endmacro -%}
module {{ module.name }} (
    input wire [0:0] clk
    {% if module.dualport -%}
        {{ memport('1', module.addr_width) }}
        {{ memport('2', module.addr_width) }}
    {%- else -%}
        {{ memport('', module.addr_width) }}
    {%- endif %}
    );
endmodule

