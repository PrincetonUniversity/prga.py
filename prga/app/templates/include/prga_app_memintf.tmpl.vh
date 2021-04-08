`ifndef PRGA_APP_MEMINTF_VH
`define PRGA_APP_MEMINTF_VH

`define PRGA_APP_MEMINTF_ADDR_WIDTH {{ memintf.addr_width }}
`define PRGA_APP_MEMINTF_DATA_BYTES_LOG2 {{ memintf.data_bytes_log2 }}

`define PRGA_APP_MEMINTF_SIZE_WIDTH {{ memintf.size_width }}
{%- for i in range(memintf.data_bytes_log2 + 1) %}
`define PRGA_APP_MEMINTF_SIZE_{{ 2 ** i }}B `PRGA_APP_MEMINTF_SIZE_WIDTH'd{{ memintf.size_values[i] }}
{%- endfor %}

`define PRGA_APP_MEMINTF_DATA_BYTES (1 << PRGA_APP_MEMINTF_DATA_BYTES_LOG2)
`define PRGA_APP_MEMINTF_DATA_WIDTH (`PRGA_APP_MEMINTF_DATA_BYTES * 8)

`endif /* `ifdnef PRGA_APP_MEMINTF_VH */
