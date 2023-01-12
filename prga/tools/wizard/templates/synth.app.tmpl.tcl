# bring yosys command into our script!
yosys -import

# read library cells
tcl {{ syn.generic.lib }}

# read verilog sources
{%- for dir_ in app.includes|default([]) %}
verilog_defaults -add -I{{ abspath(dir_) }}
{%- endfor %}
{%- for k, v in (app.defines|default({})).items() %}
{%- if v is none %}
verilog_defines -D{{ k }}
{%- else %}
verilog_defines -D{{ k }}={{ v }}
{%- endif %}
{%- endfor %}
{%- for src in app.sources %}
read_verilog {{ abspath(src) }}
{%- endfor %}

# pre-process
{%- for k, v in (app.parameters|default({})).items() %}
chparam -set {{ k }} {{ v }} {{ app.name }}
{%- endfor %}
hierarchy -check -top {{ app.name }}

# synthesis
tcl {{ syn.generic.syn }}

# output
write_blif -conn -param syn.eblif

{% if tests is defined -%}
# simulateable Verilog output
zinit -all
yosys rename -top postsyn
write_verilog -norename -attr2comment postsyn.v
{%- endif %}
