__doc__ = """
Classes for nets and net references.

Notes:
    1. All nets/net references are sequences and can be indexed using integers to get individual bits, or using slices
       \(range specifiers\) to get consecutive subsets.
    2. All nets in PRGA are indexed in a big-endian fashion, so a 4-bit bus is equivalent to ``wire [3:0]`` in
       Verilog. PRGA does not support little-endian indexing so there is no way to express ``wire [0:3]`` as in
       Verilog.
    3. When using a slice to index a net, if the ``stop`` value is equal to or smaller than the ``start`` value, the
       slice is treated as a Verilog-style index. That is, ``n[2:0]`` works the same way as in Verilog and returns the
       lower 3 bits of net ``n``. On the other side, if the ``stop`` value is larger than the ``start`` value, the
       slice is interpretted as a Python-style index, so ``n[0:2]`` returns the lower **2** bits of net ``n``. Note
       the difference in the number of bits returned.
    4. On the contrary to indexing, iteration of nets is little-endian, i.e. starts from the LSB. So ``for bit in
       net:`` visits ``n[0]`` first, then ``n[1]``, then so on so forth. This design decision is motivated by the fact
       that iteration is not really a thing in Verilog but is often used in Python, so we follow the Python
       convention.
"""

from .common import NetType, PortDirection, TimingArcType, Const
from .bus import Port, Pin, HierarchicalPin
from .util import NetUtils

__all__ = ['NetType', 'PortDirection', 'TimingArcType', 'Const', 'Port', 'Pin', 'HierarchicalPin', 'NetUtils']
