# bring yosys command into our script!
yosys -import

# read verilog sources
{%- for dir_ in design.includes|default([]) %}
verilog_defaults -I{{ abspath(dir_) }}
{%- endfor %}
{%- for k, v in (design.defines|default({})).items() %}
{%- if none(v) %}
verilog_define -D{{ k }}
{%- else %}
verilog_define -D{{ k }}={{ v }}
{%- endif %}
{%- endfor %}
{%- for src in design.sources %}
read_verilog {{ abspath(src) }}
{%- endfor %}

# pre-process
{%- for k, v in (design.parameters|default({})).items() %}
chparam -set {{ k }} {{ v }} {{ design.name }}
{%- endfor %}
hierarchy -check -top {{ design.name }}

# synthesis
tcl {{ syn.generic }}

# output
write_blif -conn -param syn.eblif

{% if tests is defined -%}
# simulateable Verilog output
zinit -all
yosys rename -top postsyn
write_verilog -norename -attr2comment postsyn.v
{%- endif %}
