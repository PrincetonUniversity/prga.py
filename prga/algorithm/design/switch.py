# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.switch.switch import SwitchInstance
from prga.exception import PRGAInternalError
from prga.util import Abstract

from abc import abstractmethod, abstractproperty
from itertools import chain

__all__ = ['SwitchLibraryDelegate', 'switchify']

# ----------------------------------------------------------------------------
# -- Switch Library Delegate -------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchLibraryDelegate(Abstract):
    """Switch library supplying switch modules for instantiation."""

    # == low-level API =======================================================
    # -- properties/methods to be implemented/overriden by subclasses --------
    @abstractmethod
    def get_or_create_switch(self, width, module):
        """Get a switch module with ``width`` input bits for ``module``.

        Args:
            width (:obj:`int`): Number of inputs needed
            module (`AbstractModule`): The module in which connections are to be implemented with switches

        Returns:
            `AbstractSwitch`: Switch module found

        Note:
            The returned switch could have more than ``width`` input bits
        """
        raise NotImplementedError

    @abstractproperty
    def is_empty(self):
        """:obj:`bool`: Test if the library is empty."""
        raise NotImplementedError

# ----------------------------------------------------------------------------
# -- Algorithms for Implementing User-defined Configurable Connections -------
# ----------------------------------------------------------------------------
def _instantiate_switch(module, switch, name, sources, sink):
    """Instantiate an instance of ``switch`` named ``name`` in ``module``, connecting ``sources`` and ``sink``.

    Args:
        module (`AbstractModule`): The module in which switches are to be implemented
        switch (`AbstractSwitch`): The switch used to implement this connection
        name (:obj:`str`): Name of the instantiated switch
        sources (:obj:`Sequence` [`AbstractSourceBit` ]): Source bits to be connected
        sink (`AbstractSinkBit`): Sink bit to be connected

    Returns:
        `SwitchInstance`: Instantiated switch

    The instantiated switch will NOT be added to ``module``. The logical connection between ``sink`` and the switch
    output will NOT be created either.
    """
    if len(sources) < 2 or len(sources) > len(switch.switch_inputs):
        raise PRGAInternalError("Invalid number of source bits ({}). Width of the switch module '{}' is {}"
                .format(len(sources), switch, len(switch.switch_inputs)))
    instance = SwitchInstance(module, switch, name)
    for source, pin_bit in zip(iter(sources), iter(instance.switch_inputs)):
        pin_bit.source = source
        if source.physical_cp is not None:
            pin_bit.physical_cp.physical_source = source.physical_cp
    return instance

def switchify(delegate, module):
    """Implement switches for user-defined connections in ``module`` with switches from ``delegate``.

    Args:
        delegate (`SwitchLibraryDelegate`):
        module (`AbstractModule`):
    """
    muxes = []  # (mux_instance, sink_bit)
    for sinkbus in filter(lambda bus: bus.is_sink, chain(itervalues(module.ports),
            iter(pin for instance in itervalues(module.instances) for pin in itervalues(instance.pins)))):
        for sink in sinkbus:
            if len(sink.user_sources) == 1:
                sink.source = sink.user_sources[0]
                if sink.physical_cp is not None and sink.source.physical_cp is not None:
                    sink.physical_cp.physical_source = sink.source.physical_cp
            elif len(sink.user_sources) > 1:
                name = ('sw_{}_{}_{}'.format(sink.parent.name, sink.bus.name, sink.index) if sink.net_type.is_pin else
                        'sw_{}_{}'.format(sink.bus.name, sink.index))
                mux = _instantiate_switch(module, delegate.get_or_create_switch(len(sink.user_sources), module),
                        name, sink.user_sources, sink)
                muxes.append( (mux, sink) )
    for mux, sink in muxes:
        sink.source = mux.switch_output
        if sink.physical_cp is not None and mux.switch_output.physical_cp is not None:
            sink.physical_cp.physical_source = mux.switch_output.physical_cp
        module._add_instance(mux)
