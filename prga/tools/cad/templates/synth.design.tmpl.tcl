# bring yosys command into our script!
yosys -import

# read verilog sources
{%- for dir_ in design.includes %}
verilog_defaults -I{{ dir_ }}
{%- endfor %}
{%- for k, v in design.defines.items() %}
{%- if none(v) %}
verilog_define -D{{ k }}
{%- else %}
verilog_define -D{{ k }}={{ v }}
{%- endif %}
{%- endfor %}
{%- for src in design.sources %}
read_verilog {{ src }}
{%- endfor %}

# pre-process
{%- for k, v in design.parameters.items() %}
chparam -set {{ k }} {{ v }} {{ design.name }}
{%- endfor %}
hierarchy -check -top {{ design.name }}

# synthesis
tcl {{ syn.generic }}

# output
write_blif -conn -param syn.eblif
write_verilog -norename -attr2comment syn.v
