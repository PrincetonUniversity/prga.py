# -*- encoding: ascii -*-

from ..util import Enum, Object
from ..exception import PRGAAPIError
from abc import abstractproperty, abstractmethod

__all__ = ["SystemIntf", "FabricIntf", "ProgIntf", "FabricIntfECCType"]

# ----------------------------------------------------------------------------
# -- Interface Enumerations --------------------------------------------------
# ----------------------------------------------------------------------------
class FabricIntfECCType(Enum):
    """Error correction/check code type for the fabric interface."""

    none = 0                #: No ECC Check
    parity_odd = 1          #: Odd parity check (ECC = ^ payload)
    parity_even = 2         #: Even parity check (ECC = ~^payload)

    @property
    def ecc_bits(self):
        return self.case(0, 1, 1)

# ----------------------------------------------------------------------------
# -- Base and Common Interfaces ----------------------------------------------
# ----------------------------------------------------------------------------
class _BaseIntf(Object):
    """Base interface.
    
    Args:
        id_ (:obj:`str`): Identifier of this interface
    """
    
    __slots__ = ["_id"]

    def __init__(self, id_ = None):
        self._id = id_

    def __call__(self, *args, **kwargs):
        return type(self)(*args, **kwargs)

    def __eq__(self, other):
        return type(other) is type(self) and other.id_ == self.id_

    def __hash__(self):
        return hash( (type(self).__name__, self.id_) )

    def __ne__(self, other):
        return not self.__eq__(other)

    def __getattr__(self, attr):
        if attr.startswith("is_"):
            return attr[2:] == type(self).__name__
        raise AttributeError(attr)

    @property
    def id_(self):
        """:obj:`str`: Identifier of this interface.
        
        This is used when the fabric has multiple of the same interfaces, such as when multiple memory interfaces
        are supported.
        """
        return self._id

class _AbstractByteAddressedIntf(Object):
    """Abstract base class for byte-addressable interfaces."""

    @abstractproperty
    def addr_width(self):
        """:obj:`int`: Number of bits of the address bus."""
        raise NotImplementedError

    @abstractproperty
    def data_bytes_log2(self):
        """:obj:`int`: log2 of the number of bytes in the data bus."""
        raise NotImplementedError

class _BaseFabricIntf(_BaseIntf):
    """Base class for fabric interfaces.

    Args:
        id_ (:obj:`str`): Identifier of this interface
        ecc_type (`FabricIntfECCType`):
    """

    __slots__ = ['ecc_type']

    def __init__(self, id_ = None, ecc_type = FabricIntfECCType.parity_even):
        super().__init__(id_)
        self.ecc_type = FabricIntfECCType.construct(ecc_type)

    def __repr__(self):
        return "FabricIntf[{}](id={}, ecc={})".format(
                type(self).__name__.lstrip('_'), repr(self.id_), self.ecc_type.name)

# ----------------------------------------------------------------------------
# -- System Interfaces Collection --------------------------------------------
# ----------------------------------------------------------------------------
class SystemIntf(Object):
    """System interfaces collection.
    
    Currently all system interfaces are hardcoded.
    """

    class _syscon(_BaseIntf):

        def __repr__(self):
            return "SystemIntf[syscon](id={})".format(repr(self.id_))

    class _reg_piton(_BaseIntf, _AbstractByteAddressedIntf):

        def __repr__(self):
            return "SystemIntf[reg_piton](id={})".format(repr(self.id_))

        @property
        def addr_width(self):
            return 12

        @property
        def data_bytes_log2(self):
            return 3

    class _memory_piton(_BaseIntf):

        def __repr__(self):
            return "SystemIntf[memory_piton](id={})".format(repr(self.id_))

SystemIntf.syscon = SystemIntf._syscon()
SystemIntf.reg_piton = SystemIntf._reg_piton()
SystemIntf.memory_piton = SystemIntf._memory_piton()

# ----------------------------------------------------------------------------
# -- Programming Interfaces Collection ---------------------------------------
# ----------------------------------------------------------------------------
class ProgIntf(Object):
    """Programming interfaces collection.
    
    Currently all programming interfaces are hardcoded.
    """

    class _reg_piton(_BaseIntf, _AbstractByteAddressedIntf):

        def __repr__(self):
            return "ProgIntf[reg_piton](id={})".format(repr(self.id_))

        @property
        def addr_width(self):
            return 12

        @property
        def data_bytes_log2(self):
            return 3

ProgIntf.reg_piton = ProgIntf._reg_piton()

# ----------------------------------------------------------------------------
# -- Fabric Interfaces Collection --------------------------------------------
# ----------------------------------------------------------------------------
class FabricIntf(Object):
    """Fabric interfaces collection."""

    class _syscon(_BaseIntf):

        def __repr__(self):
            return "FabricIntf[syscon](id={})".format(repr(self.id_))

    class _softreg(_BaseFabricIntf, _AbstractByteAddressedIntf):

        __slots__ = ['addr_width', 'data_bytes_log2', 'strb']

        def __init__(self, id_ = None,
                ecc_type = FabricIntfECCType.parity_even,
                addr_width = 12,
                data_bytes_log2 = 3,
                strb = False
                ):
            super().__init__(id_, ecc_type)
            
            self.addr_width = addr_width
            self.data_bytes_log2 = data_bytes_log2
            self.strb = strb

        def __repr__(self):
            return "FabricIntf[softreg](id={}, ecc={}, addr_width={}, data_bytes_log2={}, strb={})".format(
                    repr(self.id_), self.ecc_type.name, self.addr_width, self.data_bytes_log2,
                    'y' if self.strb else 'n')

    class _memory_piton(_BaseFabricIntf):

        pass

    class _memory_piton_axi4r(_BaseFabricIntf):

        # AXI4 AR & R interfaces for coherent memory access
        #  - Do not support:
        #      * ARPROT, ARQOS, ARREGION:          all tied to constant zero
        #  - Support ARID, RID (PITON threads)
        #  - Non-standard use of ARLOCK:
        #      * ARLOCK marks the load as an atomic operation. AMO type and data in ARUSER
        #  - Non-standard use of ARCACHE:
        #      * |ARCache[3:2]:    coherent (cacheable) read
        #      * other value:      non-coherent (non-cacheable) read
        #      * Device, bufferability, write-through/write-back, and allocatioin strategy are not respected
        #  - Additional use of ARUSER:
        #      * ECC bit(s)
        #      * AMO opcode
        #      * AMO data

        pass

    class _memory_piton_axi4w(_BaseFabricIntf):

        # AXI4 AW, W & B interfaces for coherent memory access
        #  - Do not support:
        #      * AWPROT, AWQOS, AWREGION, AWLOCK:  all tied to constant zero
        #  - Support AWID, BID (PITON threads)
        #  - Non-standard use of AWCACHE:
        #      * |AWCache[3:2]:    coherent (cacheable) write
        #      * other value:      non-coherent (non-cacheable) write
        #      * Device, bufferability, write-through/write-back, and allocatioin strategy are not respected
        #  - Additional use of AWUSER:
        #      * ECC bit(s)

        pass

FabricIntf.syscon = FabricIntf._syscon()
FabricIntf.softreg = FabricIntf._softreg()
FabricIntf.memory_piton = FabricIntf._memory_piton()
FabricIntf.memory_piton_axi4r = FabricIntf._memory_piton_axi4r()
FabricIntf.memory_piton_axi4w = FabricIntf._memory_piton_axi4w()
