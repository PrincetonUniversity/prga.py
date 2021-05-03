# -*- encoding: ascii -*-

from ..prog.magic.lib import Magic
from ..prog.frame.lib import Frame
from ..prog.scanchain.lib import Scanchain
from ..prog.pktchain.lib import Pktchain
from ..exception import PRGAAPIError
from .base import AbstractPass

__all__ = ['Materialization']

# ----------------------------------------------------------------------------
# -- Context Materialization Pass --------------------------------------------
# ----------------------------------------------------------------------------
class Materialization(AbstractPass):
    """Materialize an abstract architecture context with a programming protocol.
    
    Args:
        protocol (:obj:`str`): Programming protocol. Currently supported protocols are: ``Magic``, ``Scanchain``,
            ``Pktchain``, ``Frame``

    Keyword Args:
        **kwargs: Arguments specific to the selected protocol. Please refer to the ``materialize`` method of each
            programming protocol for more information
    """

    __slots__ = ['protocol', '_kwargs']
    _protocols = {
            "magic": Magic,
            "frame": Frame,
            "scanchain": Scanchain,
            "pktchain": Pktchain,
            }

    def __init__(self, protocol, **kwargs):
        if (p := self._protocols.get(protocol.lower())) is None:
            raise PRGAAPIError("Unknown programming protocol: {}".format(protocol))
        self.protocol = p
        self._kwargs = kwargs

    @property
    def key(self):
        return "materialization"

    @property
    def passes_after_self(self):
        return ("rtl", )

    def run(self, context):
        self.protocol.materialize( context, inplace = True, **self._kwargs )
