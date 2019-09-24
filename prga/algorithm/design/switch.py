# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.module.instance import RegularInstance
from prga.exception import PRGAInternalError
from prga.util import Abstract

from abc import abstractmethod
from itertools import chain

__all__ = ['SwitchLibraryDelegate', 'switchify']

# ----------------------------------------------------------------------------
# -- Switch Library Delegate -------------------------------------------------
# ----------------------------------------------------------------------------
class SwitchLibraryDelegate(Abstract):
    """Switch library supplying switch modules for instantiation."""

    @abstractmethod
    def get_switch(self, width, module):
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
        `RegularInstance`: Instantiated switch

    The instantiated switch will NOT be added to ``module``. The logical connection between ``sink`` and the switch
    output will NOT be created either.
    """
    if len(sources) < 2 or len(sources) > len(switch.switch_inputs):
        raise PRGAInternalError("Invalid number of source bits ({}). Width of the switch module '{}' is {}"
                .format(len(sources), switch, len(switch.switch_inputs)))
    instance = RegularInstance(module, switch, name)
    for source, port_bit in zip(iter(sources), iter(switch.switch_inputs)):
        pin_bit = instance.all_pins[port_bit.bus.key][port_bit.index]
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
                mux = _instantiate_switch(module, delegate.get_switch(len(sink.user_sources), module),
                        name, sink.user_sources, sink)
                muxes.append( (mux, sink) )
    for mux, sink in muxes:
        muxout = mux.all_pins[mux.model.switch_output.bus.key][mux.model.switch_output.index]
        sink.source = muxout
        if sink.physical_cp is not None and muxout.physical_cp is not None:
            sink.physical_cp.physical_source = muxout.physical_cp
        module._add_instance(mux)
