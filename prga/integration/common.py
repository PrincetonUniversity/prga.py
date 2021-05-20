# -*- encoding: ascii -*-

from ..util import Enum, Object
from ..exception import PRGAAPIError
from abc import abstractproperty, abstractmethod

__all__ = ["SystemIntf", "FabricIntf", "FabricIntfECCType"]

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

class _ByteAddressableMixin(Object):
    """Mixin class for byte-addressable interfaces."""

    @abstractproperty
    def addr_width(self):
        """:obj:`int`: Number of bits of the address bus."""
        raise NotImplementedError

    @abstractproperty
    def data_bytes_log2(self):
        """:obj:`int`: log2 of the number of bytes in the data bus."""
        raise NotImplementedError

class _ECCMixin(Object):
    """Mixin class for fabric interfaces."""

    @property
    def ecc_type(self):
        """`FabricIntfECCType`: Error detection/correction code type."""
        return FabricIntfECCType.parity_odd

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

    class _reg_piton(_BaseIntf, _ByteAddressableMixin):

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

    class _rxi(_BaseIntf, _ByteAddressableMixin):

        __slots__ = ['addr_width', 'data_bytes_log2', "num_yami"]

        def __init__(self, id_ = None, addr_width = 9, data_bytes_log2 = 2, num_yami = 1):

            # validate
            if data_bytes_log2 not in (2, 3):
                raise PRGAAPIError("Only 4B/8B data width are supported (data_bytes_log2 = {})"
                        .format(data_bytes_log2))
            elif addr_width - data_bytes_log2 < 6:
                raise PRGAAPIError("Addr width ({}) less than `data_bytes_log2 + 6` ({})"
                        .format(addr_width, data_bytes_log2 + 6))

            super().__init__(id_)
            self.addr_width = addr_width
            self.data_bytes_log2 = data_bytes_log2
            self.num_yami = num_yami

        def __repr__(self):
            return "SystemIntf[RXI](id={}, aw={}, dw={}B, {} YAMIs)".format(
                    repr(self.id_), self.addr_width, 2 ** self.data_bytes_log2, self.num_yami)

    class _yami(_BaseIntf):

        __slots__ = ['fmc_addr_width', 'fmc_data_bytes_log2',
                'mfc_addr_width', 'mfc_data_bytes_log2',
                'cacheline_bytes_log2']

        def __init__(self, id_ = None,
                fmc_addr_width = 40,
                fmc_data_bytes_log2 = 2,    # 4B interface by default
                mfc_addr_width = 16,        # up to 8KB cache
                mfc_data_bytes_log2 = 2,    # 4B interface as well
                cacheline_bytes_log2 = 4,   # 16B cacheline
                ):

            # validate
            if fmc_addr_width < mfc_addr_width:
                raise PRGAAPIError("fmc_addr_width ({}) must be larger than or equal to mfc_addr_width ({})"
                        .format(fmc_addr_width, mfc_addr_width))
            elif mfc_addr_width < cacheline_bytes_log2:
                raise PRGAAPIError("mfc_addr_width ({}) must be larger than or equal to cacheline_bytes_log2 ({})"
                        .format(mfc_addr_width, cacheline_bytes_log2))
            elif fmc_data_bytes_log2 not in (2, 3):
                raise PRGAAPIError("Invalid fmc_data_bytes_log2 ({}). Valid values are: [2, 3]"
                        .format(fmc_data_bytes_log2))
            elif mfc_data_bytes_log2 not in (2, 3, 4, 5):
                raise PRGAAPIError("Invalid mfc_data_bytes_log2 ({}). Valid values are: [2, 3, 4, 5]"
                        .format(mfc_data_bytes_log2))
            elif cacheline_bytes_log2 not in (2, 3, 4, 5):
                raise PRGAAPIError("Invalid cacheline_bytes_log2 ({}). Valid values are: [2, 3, 4, 5]"
                        .format(cacheline_bytes_log2))
            elif mfc_data_bytes_log2 < fmc_data_bytes_log2:
                raise PRGAAPIError("mfc_data_bytes_log2 ({}) must be larger than or equal to fmc_data_bytes_log2 ({})"
                        .format(mfc_data_bytes_log2, fmc_data_bytes_log2))
            elif cacheline_bytes_log2 < mfc_data_bytes_log2:
                raise PRGAAPIError("cacheline_bytes_log2 ({}) must be larger than or equal to mfc_data_bytes_log2 ({})"
                        .format(cacheline_bytes_log2, mfc_data_bytes_log2))

            super().__init__(id_)
            self.fmc_addr_width = fmc_addr_width
            self.fmc_data_bytes_log2 = fmc_data_bytes_log2
            self.mfc_addr_width = mfc_addr_width
            self.mfc_data_bytes_log2 = mfc_data_bytes_log2
            self.cacheline_bytes_log2 = cacheline_bytes_log2

        def __repr__(self):
            return "SystemIntf[YAMI](id={}, FMC(aw={}, dw={}B), MFC(aw={}, dw={}B), $={}B)".format(
                    self.id_, self.fmc_addr_width, 2 ** self.fmc_data_bytes_log2,
                    self.mfc_addr_width, 2 ** self.mfc_data_bytes_log2, self.cacheline_bytes_log2)

SystemIntf.syscon = SystemIntf._syscon()
SystemIntf.reg_piton = SystemIntf._reg_piton()
SystemIntf.memory_piton = SystemIntf._memory_piton()
SystemIntf.rxi = SystemIntf._rxi()
SystemIntf.yami = SystemIntf._yami()

# ----------------------------------------------------------------------------
# -- Fabric Interfaces Collection --------------------------------------------
# ----------------------------------------------------------------------------
class FabricIntf(Object):
    """Fabric interfaces collection."""

    class _syscon(_BaseIntf):

        def __repr__(self):
            return "FabricIntf[syscon](id={})".format(repr(self.id_))

    class _softreg(_BaseIntf, _ECCMixin, _ByteAddressableMixin):

        __slots__ = ["ecc_type", 'addr_width', 'data_bytes_log2', 'strb']

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

    class _memory_piton(_BaseIntf, _ECCMixin):

        def __repr__(self):
            return "FabricIntf[memory_piton](id={})".format(
                    repr(self.id_), self.ecc_type.name)

    class _memory_piton_axi4r(_BaseIntf, _ECCMixin):

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

        def __repr__(self):
            return "FabricIntf[memory_piton_axi4r](id={})".format(
                    repr(self.id_), self.ecc_type.name)

    class _memory_piton_axi4w(_BaseIntf, _ECCMixin):

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

        def __repr__(self):
            return "FabricIntf[memory_piton_axi4w](id={})".format(
                    repr(self.id_), self.ecc_type.name)

    class _rxi(SystemIntf._rxi, _ECCMixin):

        def __repr__(self):
            return "FabricIntf[RXI](id={}, aw={}, dw={}B)".format(
                    repr(self.id_), self.addr_width, 2 ** self.data_bytes_log2)

    class _yami(SystemIntf._yami, _ECCMixin):

        def __repr__(self):
            return "SystemIntf[YAMI](id={}, FMC(aw={}, dw={}B), MFC(aw={}, dw={}B), $={}B)".format(
                    self.id_, self.fmc_addr_width, 2 ** self.fmc_data_bytes_log2,
                    self.mfc_addr_width, 2 ** self.mfc_data_bytes_log2, self.cacheline_bytes_log2)

FabricIntf.syscon = FabricIntf._syscon()
FabricIntf.softreg = FabricIntf._softreg()
FabricIntf.memory_piton = FabricIntf._memory_piton()
FabricIntf.memory_piton_axi4r = FabricIntf._memory_piton_axi4r()
FabricIntf.memory_piton_axi4w = FabricIntf._memory_piton_axi4w()
FabricIntf.rxi = FabricIntf._rxi()
FabricIntf.yami = FabricIntf._yami()
