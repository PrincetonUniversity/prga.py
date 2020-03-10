# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.netlist.net.common import PortDirection
from prga.netlist.net.util import NetUtils
from prga.core.common import ModuleView, IOType, ModuleClass
from prga.core.context import Context
from prga.exception import PRGAAPIError
from prga.renderer.renderer import FileRenderer
from prga.util import enable_stdout_logging, uno

from ...util import find_verilog_top, parse_io_bindings, parse_parameters

import os
import re
import logging
from copy import copy

_logger = logging.getLogger(__name__)
_reprog_bit = re.compile('^(?P<name>.*?)(?:\[(?P<index>\d+)\])?$')

__all__ = ['generate_scanchain_testbench_wrapper']

def _update_config_list(module, config, prefix = '', base = 0):
    cur = module.ports['cfg_o']
    while True:
        prev = NetUtils.get_source(cur)
        if not prev.net_type.is_pin:
            break
        instance = prev.hierarchy
        assert not instance.is_hierarchical
        if instance.model.module_class in (ModuleClass.primitive, ModuleClass.switch, ModuleClass.cfg):
            global_base = base + instance.cfg_bitoffset
            local_base = 0
            length = instance.model.cfg_bitcount
            while local_base < length:
                addr = global_base // 64
                low = global_base % 64
                high = min(low + length - local_base, 64)
                num_bits = high - low
                config.append( (
                    '{}{}.cfg_d[{}:{}]'.format(prefix, instance.name, local_base + num_bits - 1, local_base),
                    addr, low, high - 1) )
                global_base += num_bits
                local_base += num_bits
        else:
            _update_config_list(instance.model, config,
                    prefix + instance.name + '.', base + instance.cfg_bitoffset)
        cur = instance.pins['cfg_i']

def generate_scanchain_testbench_wrapper(context, renderer, ostream, tb_top, behav_top, io_bindings):
    """Generate simulation testbench wrapper for scanchain configuration circuitry.

    Args:
        context (`Context`): The architecture context of the custom FPGA
        renderer (`FileRenderer`): File renderer
        ostream (file-like object): Output file
        tb_top (`VerilogModule`): Top-level module of the testbench of the behavioral model
        behav_top (`VerilogModule`): Top-level module of the behavioral model
        io_bindings (:obj:`Mapping` [:obj:`str` ], :obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int`]): Mapping from
           port name in the behavioral model to \(x, y, subblock\)
    """
    fpga_top = context.database[ModuleView.logical, context.top.key]
    # configuration bits
    config_info = {}
    total_config_bits = config_info['bs_total_size'] = fpga_top.cfg_bitcount
    last_bit_index = config_info['bs_last_bit_index'] = (total_config_bits - 1) % 64
    num_qwords = total_config_bits // 64
    if last_bit_index != 63:
        num_qwords += 1
    config_info['bs_num_qwords'] = num_qwords

    # extract io bindings
    impl_info = {'name': fpga_top.name, 'config': []}
    ports = impl_info['ports'] = {}
    for name, (x, y, subblock) in iteritems(io_bindings):
        direction = PortDirection.input_
        if name.startswith('out:'):
            name = name[4:]
            direction = PortDirection.output
        matched = _reprog_bit.match(name)
        port_name = matched.group('name')
        index = matched.group('index')
        if index is not None:
            index = int(index)
        # 1. is it a valid port in the behavioral model?
        behav_port = behav_top.ports.get(port_name)
        if behav_port is None:
            raise PRGAAPIError("Port '{}' is not found in design '{}'"
                    .format(port_name, behav_top.name))
        elif behav_port.direction is not direction:
            raise PRGAAPIError("Direction mismatch: port '{}' is {} in behavioral model but {} in IO bindings"
                    .format(port_name, behav_port.direction.name, direction))
        elif index is None and behav_port.low is not None:
            raise PRGAAPIError("Port '{}' is a bus and requires an index"
                    .format(port_name))
        elif index is not None and (behav_port.low is None or index < behav_port.low or index >= behav_port.high):
            raise PRGAAPIError("Bit index '{}' is not in port '{}'"
                    .format(index, port_name))
        # 2. is (x, y, subblock) an IO block?
        port = fpga_top.ports.get(
                (direction.case(IOType.ipin, IOType.opin), (x, y), subblock) )
        if port is None:
            raise PRGAAPIError("No {} IO port found at position ({}, {}, {})"
                    .format(direction, x, y, subblock))
        # 3. bind
        behav_port = copy(behav_port)
        behav_port.name = name
        ports[port.name] = behav_port

    # configuration info
    _update_config_list(fpga_top, impl_info['config'])

    # generate testbench wrapper
    renderer.add_generic( ostream, "tb.tmpl.v",
            config = config_info, behav = behav_top, tb = tb_top, impl = impl_info,
            iteritems = iteritems, itervalues = itervalues )

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
            description="Testbench generator for scanchain configuration circuitry")
    
    parser.add_argument('context', type=argparse.FileType(OpenMode.rb),
            help="Pickled architecture context object")
    parser.add_argument('io', type=str,
            help="IO assignment constraint")
    parser.add_argument('wrapper', type=argparse.FileType(OpenMode.wb),
            help="Generated Verilog testbench wrapper")

    parser.add_argument('-t', '--testbench', type=str, nargs='+', dest="testbench",
            help="Testbench file(s) for behavioral model")
    parser.add_argument('--testbench_top', type=str,
            help="Top-level module name of the testbench. Required if the testbench comprises multiple files/modules")
    parser.add_argument('--testbench_parameters', type=str, nargs="+", default=[],
            help="Parameters for the testbench: PARAMETER0=VALUE0 PARAMETER1=VALUE1 ...")

    parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
            help="Source file(s) for behavioral model")
    parser.add_argument('--model_top', type=str,
            help="Top-level module name of the behavioral model. Required if the model comprises multiple files/modules")
    parser.add_argument('--model_parameters', type=str, nargs="+", default=[],
            help="Parameters for the behavioral model: PARAMETER0=VALUE0 PARAMETER1=VALUE1 ...")

    args = parser.parse_args()
    enable_stdout_logging(__name__, logging.INFO)
    context = Context.unpickle(args.context)
    if not isinstance(context, Context):
        raise RuntimeError("'{}' is not a pickled context object".format(args.context))
    tb_top = find_verilog_top(args.testbench, args.testbench_top)
    tb_top.parameters = parse_parameters(args.testbench_parameters)
    behav_top = find_verilog_top(args.model, args.model_top)
    behav_top.parameters = parse_parameters(args.model_parameters) 
    io_bindings = parse_io_bindings(args.io)

    # create renderer
    r = FileRenderer(os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates'))
    generate_scanchain_testbench_wrapper(context, r, args.wrapper, tb_top, behav_top, io_bindings)
    r.render()
