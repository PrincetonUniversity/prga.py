`ifndef PRGA_APP_SOFTREGS_VH
`define PRGA_APP_SOFTREGS_VH
{% if softregs.intf.is_softreg %}
`define PRGA_APP_SOFTREG_ADDR_WIDTH {{ softregs.intf.addr_width }}
{%- elif softregs.intf.is_rxi %}
`define PRGA_APP_SOFTREG_ADDR_WIDTH {{ softregs.intf.addr_width - softregs.intf.data_bytes_log2 }}
{%- endif %}
`define PRGA_APP_SOFTREG_DATA_BYTES {{ 2 ** softregs.intf.data_bytes_log2 }}
`define PRGA_APP_SOFTREG_DATA_WIDTH (`PRGA_APP_SOFTREG_DATA_BYTES << 3)
{% for name, r in softregs.regs.items() %}
// {{ r.type_.name }} soft register: {{ name }}
`define PRGA_APP_SOFTREG_VAR_{{ name | upper }}_ADDR        `PRGA_APP_SOFTREG_ADDR_WIDTH'h{{ "%x" % r.addr }}
`define PRGA_APP_SOFTREG_VAR_{{ name | upper }}_DATA_WIDTH  {{ r.width }}
`define PRGA_APP_SOFTREG_VAR_{{ name | upper }}_RSTVAL      `PRGA_APP_SOFTREG_VAR_{{ name | upper }}_DATA_WIDTH'h{{ "%x" % r.rstval }}
{% endfor %}

`endif /* `ifndef PRGA_APP_SOFTREGS_VH */
