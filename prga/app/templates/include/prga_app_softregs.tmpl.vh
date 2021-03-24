`ifndef PRGA_APP_SOFTREGS_VH
`define PRGA_APP_SOFTREGS_VH

`define PRGA_APP_SOFTREG_ADDR_WIDTH {{ softregs.addr_width }}
`define PRGA_APP_SOFTREG_DATA_BYTES {{ softregs.align }}
`define PRGA_APP_SOFTREG_DATA_WIDTH (`PRGA_APP_SOFTREG_DATA_BYTES << 3)
{% for name, r in softregs.regs.items() %}
// {{ r.type_.name }} soft register: {{ name }}
`define PRGA_APP_SOFTREG_VAR_{{ name | upper }}_ADDR        `PRGA_APP_SOFTREG_ADDR_WIDTH'h{{ "%x" % r.addr }}
`define PRGA_APP_SOFTREG_VAR_{{ name | upper }}_DATA_WIDTH  {{ r.width }}
{%- if r.type_.is_const %}
`define PRGA_APP_SOFTREG_VAR_{{ name | upper }}_CONSTVAL    `PRGA_APP_SOFTREG_VAR_{{ name | upper }}_DATA_WIDTH'h{{ "%x" % r.rstval }}
{%- elif r.type_.name in ("basic", "pulse", "pulse_ack", "decoupled") %}
`define PRGA_APP_SOFTREG_VAR_{{ name | upper }}_RSTVAL      `PRGA_APP_SOFTREG_VAR_{{ name | upper }}_DATA_WIDTH'h{{ "%x" % r.rstval }}
{%- endif %}
{% endfor %}

`endif /* `ifndef PRGA_APP_SOFTREGS_VH */
