# -*- encoding: ascii -*-

from .softregs import SoftRegSpace
from ..util import Object, ReadonlyMappingProxy
from ..exception import PRGAAPIError

import os

__all__ = ['AppContext']

# ----------------------------------------------------------------------------
# -- App Context -------------------------------------------------------------
# ----------------------------------------------------------------------------
class AppContext(Object):
    """The context for application wrapping.

    Args:
        intfs (:obj:`dict` [:obj:`str`, :obj:`dict` [:obj:`str`, `FabricIntf` ]]): 
        template_search_paths (:obj:`str` or :obj:`Container` [:obj:`str` ]): Additional search paths other than the
            default ones

    Keyword Args:
        **kwargs: Custom attributes assigned to the context 
    """

    __slots__ = [
            '_intfs',                   # fabric interfaces
            '_verilog_headers',         # Verilog header rendering tasks
            '_modules',                 # name to module mapping
            '_top',                     # top-level module
            '_used_intfs',              # used interfaces
            '_softregs',                # soft register space
            'template_search_paths',    # File renderer template search paths
            ]

    def __init__(self, intfs, template_search_paths = None):
        self._intfs = intfs
        self._modules = {}
        self._top = None
        self._used_intfs = set()
        self._softregs = None

        if template_search_paths is None:
            self.template_search_paths = []
        elif isinstance(template_search_paths, str):
            self.template_search_paths = [template_search_paths]
        else:
            self.template_search_paths = list(iter(template_search_paths))

        self.template_search_paths.append(
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')
                )

        SoftRegSpace._register_cells(self)

    @property
    def modules(self):
        """:obj:`dict` [:obj:`str`, `Module`]: Mapping from module names to modules."""
        return ReadonlyMappingProxy(self._modules)

    @property
    def top(self):
        """:obj:`Module`: Top-level, i.e. wrapped, application."""
        return self._top

    def add_module(self, module):
        """Add ``module`` into this context.

        Args:
            module (`Module`):

        Returns:
            `Module`:
        """
        if d := self._modules.get( module.key, None ):
            raise PRGAAPIError("Module with key '{}' already created: {}"
                    .format(module.key, d))
        self._modules[module.key] = module
        return module

    def add_verilog_header(self, f, template, *deps,
            key = None, **parameters):
        """Add a Verilog header.
        
        Args:
            f (:obj:`str`): Name of the output file
            template (:obj:`str`): Name of the template or source file
            *deps (:obj:`str`): Other header files that this one depends on

        Keyword Args:
            key (:obj:`str`): A key to index this verilog header. Default to ``f``
            **parameters: Extra parameters for the template
        """
        self._verilog_headers[uno(key, f)] = f, template, set(deps), parameters

    def initialize_softregspace(self, type_ = None, id_ = None):
        """Initialize soft register space.
        
        Args:
            type_ (:obj:`str`): Explicitly specify the type of the interface. Currently supported values are 'rxi' and
                'softreg'
            id_ (:obj:`str`): Explicitly specify the ID of the interface

        Returns:
            `SoftRegSpace`:
        """

        if self._softregs is not None:
            raise PRGAAPIError("Soft register space already initialized")

        # find the proper fabric interface for this
        candidates = None
        if type_ is not None:
            if candidates := self._intfs.get(type_):
                pass
            else:
                raise PRGAAPIError("Interface of type '{}' not found".format(type_))
        else:
            if candidates := self._intfs.get("rxi"):
                pass
            elif candidates := self._intfs.get("softreg"):
                pass
            else:
                raise PRGAAPIError("Interface not found that supports soft registers")

        intf = None
        if id_ is not None:
            if intf := candidates.get(id_):
                pass
            else:
                raise PRGAAPIError("Interface of ID '{}' not found".format(id_))
        elif len(candidates) == 0:
            raise PRGAAPIError("Interface not found that supports soft registers")
        else:
            intf = next(iter(candidates.values()))

        if intf.id_ in self._used_intfs:
            raise PRGAAPIError("Interface '{}' is aleady in use".format(repr(intf))
        self._used_intfs.add(intf.id_)

        # initialize softregspace
        s = self._softregs = SoftRegSpace(intf)
