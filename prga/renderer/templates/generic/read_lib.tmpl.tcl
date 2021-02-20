# get the path to the current dir
set generic_script_root [file dirname [file normalize [info script]]]

# bring yosys commands into our script!
yosys -import

# read techmap libraries
{%- for lib in libraries %}
read_verilog -lib [file join $generic_script_root {{ lib }}]
{%- endfor %}

