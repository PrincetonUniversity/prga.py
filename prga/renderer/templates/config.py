from bitarray import bitarray

internal_ff = [0,0]
internal_lut = [0,0]
internal_sum = 0
internal_ce = 0
internal_sr = 0
{%- if module.cfg_bitcount %}
cfg_d = bitarray([0]*{{module.cfg_bitcount}})
{% endif -%}
