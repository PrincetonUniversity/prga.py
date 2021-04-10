# -*- encoding: ascii -*-

from ..util import Enum, Object
from abc import abstractproperty, abstractmethod

__all__ = ["SystemIntf", "FabricIntf", "ProgIntf",
        "FabricMemIntfTrxTypeSet", "FabricMemIntfAMOTypeSet", "FabricMemIntfTrxSizeSet", "FabricIntfECCType"]

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

class _BaseByteAddressedIntf(_BaseIntf):
    """Base interface for byte-addressed interfaces.

    Args:
        addr_width (:obj:`int`): 
        data_bytes_log2 (:obj:`int`):
    """

    __slots__ = ["addr_width", "data_bytes_log2"]

    def __init__(self, id_ = None, addr_width = 12, data_bytes_log2 = 3):
        super().__init__(id_)

        self.addr_width = addr_width
        self.data_bytes_log2 = data_bytes_log2

# ----------------------------------------------------------------------------
# -- System Interfaces Collection --------------------------------------------
# ----------------------------------------------------------------------------
class SystemIntf(Object):
    """System interfaces collection.
    
    Currently all system interfaces are hardcoded.
    """

    class _syscon(_BaseIntf):

        def __repr__(self):
            return "SystemIntf[syscon](id={:s})".format(self.id_)

    class _reg_openpiton(_BaseIntf):

        def __repr__(self):
            return "SystemIntf[reg_openpiton](id={:s})".format(self.id_ or "")

        @property
        def addr_width(self):
            """:obj:`int`: Number of bits in the address bus. Also determines address space."""
            return 12

        @property
        def data_bytes_log2(self):
            """:obj:`int`: Base-2 log of the number of bytes in the data bus."""
            return 3

    class _ccm_openpiton(_BaseIntf):

        def __repr__(self):
            return "SystemIntf[ccm_openpiton](id={:s})".format(self.id_)

        @property
        def addr_width(self):
            """:obj:`int`: Number of bits in the address bus. Also determines address space."""
            return 40

        @property
        def data_bytes_log2(self):
            """:obj:`int`: Base-2 log of the number of bytes in the data bus."""
            return 3

SystemIntf.syscon = SystemIntf._syscon()
SystemIntf.reg_openpiton = SystemIntf._reg_openpiton()
SystemIntf.ccm_openpiton = SystemIntf._ccm_openpiton()

# ----------------------------------------------------------------------------
# -- Programming Interfaces Collection ---------------------------------------
# ----------------------------------------------------------------------------
class ProgIntf(Object):
    """Programming interfaces collection.
    
    Currently all programming interfaces are hardcoded.
    """

    class _openpiton(_BaseIntf):

        def __repr__(self):
            return "ProgIntf[openpiton](id={:s})".format(self.id_)

ProgIntf.openpiton = ProgIntf._openpiton()

# ----------------------------------------------------------------------------
# -- Fabric Interfaces Collection --------------------------------------------
# ----------------------------------------------------------------------------
class FabricMemIntfTrxTypeSet(Enum):
    """The transaction type set of the memory interface of the fabric."""

    basic = 0           #: 0 for load and 1 for store
    basic_nc = 1        #: 0 for load, 1 for store, 2 for nc_load, 3 for nc_store
    basic_nc_amo = 2    #: 0 for load, 1 for store, 2 for nc_load, 3 for nc_store, 4 for amo

class FabricMemIntfAMOTypeSet(Enum):
    """The amo operation type set of the memory interface of the fabric."""

    none = 0            #: no AMO support
    openpiton = 1       #: OpenPiton-style AMO operation types

class FabricMemIntfTrxSizeSet(Enum):
    """The memory request size set of the memory interface of the fabric."""

    none = 0            #: fixed transaction size
    basic = 1           #: 0 for 1B, 1 for 2B, 2 for 4B, ...
    openpiton = 2       #: OpenPiton-style ``size`` field

class FabricIntfECCType(Enum):
    """ECC type of the fabric interface."""

    none = 0            #: no ECC
    parity_odd = 1      #: odd parity check
    parity_even = 2     #: even parity check

class FabricIntf(Object):
    """Fabric interfaces collection."""

    class _syscon(_BaseIntf):

        def __repr__(self):
            return "FabricIntf[syscon](id={:s})".format(self.id_)

    class _softreg_simple(_BaseByteAddressedIntf):

        __slots__ = ['ecc_type']

        def __init__(self, id_ = None,
                ecc_type = FabricIntfECCType.parity_even,
                addr_width = 12,
                data_bytes_log2 = 3
                ):
            super().__init__(id_, addr_width, data_bytes_log2)

            self.ecc_type = FabricIntfECCType.construct(ecc_type)

        def __repr__(self):
            return "FabricIntf[softreg_simple](id={:s}, ecc={}, addr_width={}, data_bytes_log2={})".format(
                    self.id_, self.ecc_type.name, self.addr_width, self.data_bytes_log2)

    class _memory_mixin(object):

        @property
        def support_nc(self):
            """:obj:`bool`: Test if this memory interface supports non-coherent requests."""
            return self.trx_type_set in (FabricMemIntfTrxTypeSet.basic_nc, FabricMemIntfTrxSizeSet.basic_nc_amo)

        @property
        def support_amo(self):
            """:obj:`bool`: Test if this memory interface supports atomic requests."""
            return self.trx_type_set in (FabricMemIntfTrxSizeSet.basic_nc_amo, )

        @property
        def support_subword(self):
            """:obj:`bool`: Test if this memory interface supports sub-word requests."""
            return not self.trx_size_set.is_none

        @property
        def support_mthreads(self):
            """:obj:`bool`: Test if this memory interface supports multiple memory threads."""
            return self.mthread_width > 0 and len(self.mthread_values)

    class _ccm_openpiton(_BaseIntf, _memory_mixin):

        @property
        def addr_width(self):
            """:obj:`int`: Number of bits in the address bus."""
            return 12

        @property
        def data_bytes_log2(self):
            """:obj:`int`: log2 of the number of bytes in the data bus."""
            return 12

        @property
        def ecc_type(self):
            """`FabricIntfECCType`"""
            return FabricIntfECCType.parity_even

        @property
        def trx_type_set(self):
            """`FabricMemIntfTrxTypeSet`"""
            return FabricMemIntfTrxTypeSet.basic_nc_amo

        @property
        def trx_size_set(self):
            """`FabricMemIntfTrxSizeSet`"""
            return FabricMemIntfTrxSizeSet.openpiton

        @property
        def amo_type_set(self):
            """`FabricMemIntfAMOTypeSet`"""
            return FabricMemIntfAMOTypeSet.openpiton

        @property
        def mthread_width(self):
            """:obj:`int`: Number of bits in the memory thread fields."""
            return 1

        @property
        def mthread_values(self):
            """:obj:`Container` [:obj:`int` ]: Valid values of the memory thread fields."""
            return set([0, 1])

        def __repr__(self):
            return "FabricIntf[ccm_openpiton](id={:s})".format(self.id_)

    class _ccm_openpiton_axi4(_ccm_openpiton):

        def __repr__(self):
            return "FabricIntf[ccm_openpiton_axi4](id={:s})".format(self.id_)

    class _memory(_BaseByteAddressedIntf, _memory_mixin):

        __slots__ = ["ecc_type", "trx_type_set", "amo_type_set", "trx_size_set", "mthread_width", "mthread_values"]

        def __init__(self, id_ = None,
                ecc_type = FabricIntfECCType.parity_even,
                addr_width = 32,
                data_bytes_log2 = 2,
                trx_type_set = FabricMemIntfTrxTypeSet.basic,
                amo_type_set = FabricMemIntfAMOTypeSet.none,
                trx_size_set = FabricMemIntfTrxSizeSet.none,
                mthread_width = 0,
                mthread_values = set()):
            super().__init__(id_, addr_width, data_bytes_log2)

            self.ecc_type = FabricIntfECCType.construct(ecc_type)
            self.trx_type_set = FabricMemIntfTrxTypeSet.construct(trx_type_set)
            self.amo_type_set = FabricMemIntfAMOTypeSet.construct(amo_type_set)
            self.trx_size_set = FabricMemIntfTrxSizeSet.construct(trx_size_set)
            self.mthread_width = mthread_width
            self.mthread_values = set(iter(mthread_values))

        def __repr__(self):
            return ( ("FabricIntf[memory](id={:s}, addr_width={}, data_bytes_log2={}, "
                "typeset={}, amoset={}, sizeset={}, #mthreads={}")
                .format(self.id_, self.addr_width, self.data_bytes_log2,
                    self.trx_type_set.name, self.amo_type_set.name, self.trx_size_set.name,
                    len(self.mthread_values)) )

    class _memory_axi4(_memory):

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

        def __repr__(self):
            return ( ("FabricIntf[memory_axi4](id={:s}, addr_width={}, data_bytes_log2={}, "
                "typeset={}, amoset={}, sizeset={}, #mthreads={}")
                .format(self.id_, self.addr_width, self.data_bytes_log2,
                    self.trx_type_set.name, self.amo_type_set.name, self.trx_size_set.name,
                    len(self.mthread_values)) )

FabricIntf.syscon = FabricIntf._syscon()
FabricIntf.softreg_simple = FabricIntf._softreg_simple()
FabricIntf.ccm_openpiton = FabricIntf._ccm_openpiton()
FabricIntf.ccm_openpiton_axi4 = FabricIntf._ccm_openpiton_axi4()
FabricIntf.memory = FabricIntf._memory()
FabricIntf.memory_axi4 = FabricIntf._memory_axi4()
