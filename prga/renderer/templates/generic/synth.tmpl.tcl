# get the path to the current dir
set generic_script_root [file dirname [file normalize [info script]]]

# bring yosys commands into our script!
yosys -import

# coarse synthesis
synth -flatten -noalumacc -run coarse

# print coarse synthesis report
stat -width

# memory map
{%- if memory_techmap is defined %}
    {%- if memory_techmap.rule %}
memory_bram -rules [file join $generic_script_root {{ memory_techmap.rule }}]
    {%- endif %}
    {%- for command in memory_techmap.premap_commands|sort(reverse=true,attribute="order") %}
{{ command.commands }}
    {%- endfor %}
    {%- if memory_techmap.techmap %}
techmap -map [file join $generic_script_root {{ memory_techmap.techmap }}]
    {%- endif %}
{%- endif %}
opt -full
memory_map

# print memory map report
stat -width

# techmap onto library cells read with `read_verilog` above
{%- for entry in techmaps|sort(reverse=true,attribute="order") if entry.order >= 0 %}
    {%- if entry.premap_commands %}
{{ entry.premap_commands }}
    {%- endif %}
    {%- if entry.techmap %}
techmap -map [file join $generic_script_root {{ entry.techmap }}]
    {%- endif %}
{%- endfor %}
opt -full

# print techmap report
stat -width

# LUT map
techmap     ;# generic techmap onto basic logic elements
{%- set comma = joiner(",") %}
abc9 -luts {% for size in lut_sizes|sort %}{{ comma() }}{{ size }}:{{ size }}{% endfor %}
opt -full

# print LUT map report
stat -width

# post-LUTmap commands
{%- for entry in techmaps|sort(reverse=true,attribute="order") if entry.order < 0 %}
    {%- if entry.premap_commands %}
{{ entry.premap_commands }}
    {%- endif %}
    {%- if entry.techmap %}
techmap -map [file join $generic_script_root {{ entry.techmap }}]
    {%- endif %}
{%- endfor %}
opt -full
clean

# print post-LUTmap report
stat -width

# convert unsupported FFs to supported FFs
dfflegalize -cell \$_DFF_P_ x -cell \$_DFFE_PP_ x -cell \$_DFFE_PN_ x

# print final report
stat -width

# final check
check -noinit
