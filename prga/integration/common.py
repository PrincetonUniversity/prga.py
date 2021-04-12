# -*- encoding: ascii -*-

from ..util import Enum, Object
from ..exception import PRGAAPIError
from abc import abstractproperty, abstractmethod

__all__ = ["SystemIntf", "FabricIntf", "ProgIntf",
        "FabricMemIntfTrxTypeSet", "FabricMemIntfAMOTypeSet", "FabricMemIntfTrxSizeSet", "FabricIntfECCType"]

# ----------------------------------------------------------------------------
# -- Interface Enumerations --------------------------------------------------
# ----------------------------------------------------------------------------
class MemIntfTrxTypeSet(Enum):
    """The transaction type set of the memory interface."""

    # Feature Flags
    feature_nc = 1          #: Add non-cacheable variations to the basic load-store requests
    feature_amo = 2         #: Add atomic request types to the basic load-store requests
    feature_subword = 4     #: Add support for sub-word requests
    feature_cacheinv = 8    #: Add private cache invalidations to the responses

    # Composed types
    basic = 0                                               #: Basic load-store requests
    piton_v0 = feature_nc | feature_amo | feature_subword   #: Support non-cacheable, sub-word, and atomic requests
    piton_v1 = piton_v0 | feature_cacheinv                  #: Support private cache invalidations on top of v0

    def __getattr__(self, attr):
        if attr.startswith("support_"):
            try:
                flag = type(self)["feature_" + attr[8:]]
            except KeyError:
                raise PRGAAPIError("Unknown feature: {}".format(attr[8:]))
            return bool(self & flag)
        return super().__getattr__(attr)

class MemIntfTrxSizeSet(Enum):
    """Memory transaction sub-word size specs."""

    none = 0                #: No `size` field included in the interface
    basic = 1               #: 0 for 1B, 1 for 2B, 2 for 4B, etc.
    piton = 2               #: Special encoding for openpiton

class MemIntfAMOTypeSet(Enum):
    """AMO type set."""

    none = 0                #: No atomic operations
    piton = 1               #: OpenPiton x Ariane

class FabricIntfECCType(Enum):
    """Error correction/check code type for the fabric interface."""

    none = 0                #: No ECC Check
    parity_odd = 1          #: Odd parity check (ECC = ^ payload)
    parity_even = 2         #: Even parity check (ECC = ~^payload)

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

    @property
    def name(self):
        """:obj:`str`: Name of the type of this interface."""
        return type(self).__name__

class _AbstractByteAddressedIntf(_BaseIntf):
    """Abstract base class for byte-addressable interfaces."""

    @abstractproperty
    def addr_width(self):
        """:obj:`int`: Number of bits of the address bus."""
        raise NotImplementedError

    @abstractproperty
    def data_bytes_log2(self):
        """:obj:`int`: log2 of the number of bytes in the data bus."""
        raise NotImplementedError

class _AbstractMemoryIntf(_AbstractByteAddressedIntf):
    """Abstract base class for memory interfaces."""

    @abstractproperty
    def trx_type_set(self):
        """`MemIntfTrxTypeSet`: Transaction types."""
        raise NotImplementedError

    @abstractproperty
    def trx_size_set(self):
        """`MemIntfTrxSizeSet`: Transaction sizes."""
        raise NotImplementedError

    @abstractproperty
    def amo_type_set(self):
        """`MemIntfAMOTypeSet`: Atomic operation codes."""
        raise NotImplementedError

    @abstractproperty
    def mthread_width(self):
        """:obj:`int`: Memory thread, or transaction ID, or memory space ID, etc."""
        raise NotImplementedError

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

    class _reg_piton(_AbstractByteAddressedIntf):

        def __repr__(self):
            return "SystemIntf[reg_piton](id={})".format(repr(self.id_))

        @property
        def addr_width(self):
            return 12

        @property
        def data_bytes_log2(self):
            return 3

    class _memory_piton(_AbstractMemoryIntf):

        def __repr__(self):
            return "SystemIntf[memory_piton](id={})".format(repr(self.id_))

        @property
        def addr_width(self):
            return 40

        @property
        def data_bytes_log2(self):
            return 3

        @property
        def trx_type_set(self):
            return MemIntfTrxTypeSet.piton_v0

        @property
        def trx_size_set(self):
            return MemIntfTrxSizeSet.piton

        @property
        def amo_type_set(self):
            return MemIntfAMOTypeSet.piton

        @property
        def mthread_width(self):
            return 1

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

    class _reg_piton(_AbstractByteAddressedIntf):

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

    class _softreg(_AbstractByteAddressedIntf):

        __slots__ = ['ecc_type', 'addr_width', 'data_bytes_log2', 'strb']

        def __init__(self, id_ = None,
                ecc_type = FabricIntfECCType.parity_even,
                addr_width = 12,
                data_bytes_log2 = 3,
                strb = False
                ):
            super().__init__(id_)
            
            self.ecc_type = FabricIntfECCType.construct(ecc_type)
            self.addr_width = addr_width
            self.data_bytes_log2 = data_bytes_log2
            self.strb = strb

        def __repr__(self):
            return "FabricIntf[softreg](id={}, ecc={}, addr_width={}, data_bytes_log2={}, strb={})".format(
                    repr(self.id_), self.ecc_type.name, self.addr_width, self.data_bytes_log2,
                    'y' if self.strb else 'n')

    class _memory_piton(_AbstractMemoryIntf):

        __slots__ = ['trx_type_set', 'axi4']

        # AXI4 interface for coherent memory access
        #  - Do not support:
        #      * AWPROT, AWQOS, AWREGION, AWLOCK:  all tied to constant zero
        #      * ARPROT, ARQOS, ARREGION:          all tied to constant zero
        #  - Support AWID, ARID, BID, RID (PITON threads)
        #  - Non-standard use of ARLOCK:
        #      * ARLOCK marks the load as an atomic operation. AMO type and data in ARUSER
        #  - Non-standard use of AWCACHE and ARCACHE:
        #      * |AxCache[3:2]:    coherent (cacheable) read/write
        #      * other value:      non-coherent (non-cacheable) read/write
        #      * Device, bufferability, write-through/write-back, and allocatioin strategy are not respected
        #  - Additional use of AWUSER:
        #      * ECC bit(s)
        #  - Additional use of ARUSER:
        #      * ECC bit(s)
        #      * AMO opcode
        #      * AMO data

        def __init__(self, id_ = None, trx_type_set = MemIntfTrxTypeSet.piton_v0, axi4 = False):
            super().__init__(id_)

            self.trx_type_set = MemIntfTrxTypeSet.construct(trx_type_set)
            self.axi4 = axi4

        @property
        def addr_width(self):
            return 12

        @property
        def data_bytes_log2(self):
            return 3

        @property
        def ecc_type(self):
            """`FabricIntfECCType`"""
            return FabricIntfECCType.parity_even

        @property
        def trx_size_set(self):
            return MemIntfTrxSizeSet.piton

        @property
        def amo_type_set(self):
            return MemIntfAMOTypeSet.piton

        @property
        def mthread_width(self):
            return 1

        def __repr__(self):
            return "FabricIntf[memory_piton](id={}, trx={}, axi4={})".format(
                    repr(self.id_), self.trx_type_set.name, 'y' if self.axi4 else 'n')

FabricIntf.syscon = FabricIntf._syscon()
FabricIntf.softreg = FabricIntf._softreg()
FabricIntf.memory_piton = FabricIntf._memory_piton()
