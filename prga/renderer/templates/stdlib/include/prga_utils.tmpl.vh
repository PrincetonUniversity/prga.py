`ifndef PRGA_UTILS_VH
`define PRGA_UTILS_VH

`define CLOG2(x) \
    {%- for i in range(1, 31) %}
    (x <= {{ 2 ** i }}) ? {{ i }} : \
    {%- endfor %}
    -1

`endif /* PRGA_UTILS_VH */
