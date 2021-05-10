`ifndef PRGA_UTILS_VH
`define PRGA_UTILS_VH

`define PRGA_CLOG2(x) \
    {%- for i in range(1, 31) %}
    ((x) <= {{ 2 ** i }}) ? {{ i }} : \
    {%- endfor %}
    -1

`define PRGA_MAX2(a,b) ((a) > (b) ? (a) : (b))
`define PRGA_MIN2(a,b) ((a) < (b) ? (a) : (b))

`endif /* PRGA_UTILS_VH */
