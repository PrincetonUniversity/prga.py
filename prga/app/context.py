# -*- encoding: ascii -*-

from .util import AppUtils
from .common import AppCommonMixin
from .mem import AppMemMixin
from .softregs import SoftRegSpace
from .kernel import KernelBuilder
from ..netlist import Module, ModuleUtils
from ..renderer import FileRenderer
from ..util import Object, ReadonlyMappingProxy, uno
from ..exception import PRGAAPIError

import os

__all__ = ['AppContext']

# ----------------------------------------------------------------------------
# -- App Context -------------------------------------------------------------
# ----------------------------------------------------------------------------
class AppContext(Object, AppMemMixin, AppCommonMixin):
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
            '_softregs',                # soft register space
            'template_search_paths',    # File renderer template search paths
            ]

    def __init__(self, intfs, template_search_paths = None):
        self._intfs = intfs
        self._verilog_headers = {}
        self._modules = {}
        self._top = None
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

    @classmethod
    def construct_from_arch_context(cls, context, template_search_paths = None):
        """Create an `AppContext` from a `Context`.

        Args:
            context (`Context`):
            template_search_paths (:obj:`str` or :obj:`Container` [:obj:`str` ]): Additional search paths other than
                the default ones

        Returns:
            `AppContext`:
        """

        intfs = {}
        for intf in context.summary.integration["fabric_intfs"]:
            intfs.setdefault(intf.type_, {})[intf.id_] = intf

        return cls(intfs, template_search_paths)

    @property
    def modules(self):
        """:obj:`dict` [:obj:`str`, `Module`]: Mapping from module names to modules."""
        return ReadonlyMappingProxy(self._modules)

    @property
    def top(self):
        """:obj:`Module`: Top-level, i.e. wrapped, application."""
        return self._top

    def get_intf(self, type_, id_ = None):
        """Get the specified interface.

        Args:
            type_ (:obj:`str`): Interface type. "rxi", "yami", "syscon", etc.
            id_ (:obj:`str`): Explicitly specify one of the interfaces of the same type. Use ``None`` as a wildcard

        Returns:
            `FabricIntf`:
        """

        if (intfs := self._intfs.get(type_)) is None:
            return None

        if intf := intfs.get(id_):
            return intf
        elif id_ is not None:
            return None
        else:
            try:
                return next(iter(intfs.values()))
            except StopIteration:
                return None

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
        intf = None
        if type_ is not None:
            if intf := self.get_intf(type_, id_):
                pass
            else:
                raise PRGAAPIError("Interface of type '{}' not found".format(type_))

        else:
            if intf := self.get_intf("rxi", id_):
                pass
            elif intf := self.get_intf("softreg", id_):
                pass
            else:
                raise PRGAAPIError("No interface found supporting soft registers")

        # initialize softregspace
        s = self._softregs = SoftRegSpace(intf)
        return s

    def build_kernel(self, name, verilog_src, **kwargs):
        """Build a kernel module for the accelerator.

        Args:
            name (:obj:`str`): Name of the kernel
            verilog_src (:obj:`str`): Source file of the kernel

        Returns:
            `KernelBuilder`:
        """
        return KernelBuilder(self,
                self.add_module(KernelBuilder.new(name, verilog_src, **kwargs)))
        
    def create_top(self, name = "app_top", **kwargs):
        """Create the top-level module for the accelerator.

        Args:
            name (:obj:`str`): Name of the top-level module.

        Keyword Args:
            **kwargs: Custom key-value arguments. These attributes are added to ``__dict__`` of the top-level module
                and accessible as dynamic attributes
        """
        m = self._top = self.add_module(Module(name,
            portgroups = {},
            **kwargs))

        # short aliases
        u = lambda x: "" if x is None else (x + "_")
        mcp = lambda n, w, d: ModuleUtils.create_port(m, n, w, d)

        # create ports that match the interfaces
        for type_, intfs in self._intfs.items():
            for id_, intf in intfs.items():

                if intf.is_syscon:
                    d = {}
                    d["clk"] = ModuleUtils.create_port(m, u(id_) + "clk", 1, "input", is_clock = True)
                    d["rst_n"] = mcp(u(id_) + "rst_n", 1, "input")
                    m.portgroups.setdefault("syscon", {})[id_] = d

                elif intf.is_rxi:
                    m.portgroups.setdefault("rxi", {})[id_] = AppUtils.create_rxi_ports(
                            m, intf, slave = True, prefix = "rxi_" + u(id_)) 

                elif intf.is_yami:
                    m.portgroups.setdefault("yami", {})[id_] = AppUtils.create_yami_ports(
                            m, intf, slave = False, prefix = "yami_" + u(id_))

                else:
                    raise NotImplementedError("Unsupported interface: {}".format(repr(intf)))
                
        return m
