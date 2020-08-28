# get the path to the current dir
set generic_script_root [file dirname [file normalize [info script]]]

# bring yosys commands into our script!
yosys -import

# read blackbox designs
{%- for lib in libraries %}
read_verilog -lib [file join $generic_script_root {{ lib }}]
{%- endfor %}

# coarse synthesis
synth -flatten -run coarse

# memory map
{%- for memmap in memory_techmaps %}
    {%- if memmap.rule %}
memory_bram -rules [file join $generic_script_root {{ memmap.rule }}]
    {%- endif %}
    {%- for command in memmap.premap_commands %}
{{ command }}
    {%- endfor %}
    {%- if memmap.techmap %}
techmap -map [file join $generic_script_root {{ memmap.techmap }}]
    {%- endif %}
{%- endfor %}
opt -full
memory_map

# techmap onto blackboxes read with `read_verilog` above
{%- for entry in techmaps %}
{%- for command in entry.premap_commands %}
{{ command }}
{%- endfor %}
    {%- if entry.techmap %}
techmap -map [file join $generic_script_root {{ entry.techmap }}]
    {%- endif %}
{%- endfor %}
opt -full

# LUT map
techmap     ;# generic techmap onto basic logic elements
{%- set comma = joiner(",") %}
abc9 -luts {% for size in lut_sizes|sort %}{{ comma() }}{{ size }}:{{ size }}{% endfor %}
opt -fast -full
clean

# final check
stat
check -noinit
