# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import PortDirection
from prga.algorithm.util.array import get_external_port
from prga.flow.context import ArchitectureContext
from prga.util import enable_stdout_logging, uno

from prga_tools.util import find_verilog_top, parse_io_bindings, parse_parameters

import jinja2 as jj
import os
import re
import logging
from copy import copy

_logger = logging.getLogger(__name__)
_reprog_bit = re.compile('^(?P<name>.*?)(?:\[(?P<index>\d+)\])?$')

__all__ = ['generate_testbench_wrapper']

def generate_testbench_wrapper(context, template, ostream, tb_top, behav_top, io_bindings):
    """Generate simulation testbench wrapper.

    Args:
        context (`ArchitectureContext`): The architecture context of the custom FPGA
        template (Jinja2 template):
        ostream (file-like object): Output file
        tb_top (`VerilogModule`): Top-level module of the testbench of the behavioral model
        behav_top (`VerilogModule`): Top-level module of the behavioral model
        io_bindings (:obj:`Mapping` [:obj:`str` ], :obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int`]): Mapping from
           port name in the behavioral model to \(x, y, subblock\)
    """
    # configuration info
    config_info = {}
    config_info['magic_sop'] = context.config_circuitry_delegate.magic_sop
    cfg_width = config_info['width'] = context.config_circuitry_delegate.config_width
    bs_size = (48 * context.config_circuitry_delegate.total_hopcount +
            context.config_circuitry_delegate.total_config_bits + 16)
    last_index = bs_size % 64
    config_info['bs_num_qwords'] = bs_size // 64 + (1 if last_index else 0)
    config_info['bs_last_bit_index'] = (last_index + 64 - cfg_width) % 64

    # extract io bindings
    impl_info = {'name': context.top.name}
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
        port = get_external_port(context.top, (x, y), subblock, direction)
        if port is None:
            raise PRGAAPIError("No {} IO port found at position ({}, {}, {})"
                    .format(direction, x, y, subblock))
        # 3. bind
        behav_port = copy(behav_port)
        behav_port.name = name
        ports[port.name] = behav_port

    # generate testbench wrapper
    template.stream({
        "config": config_info,
        "behav": behav_top,
        "tb": tb_top,
        "impl": impl_info,
        "iteritems": iteritems,
        "itervalues": itervalues,
        }).dump(ostream)

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(
            description="Testbench generator for packetized-chain-style configuration circuitry")
    
    parser.add_argument('context', type=argparse.FileType(OpenMode.rb),
            help="Pickled architecture context object")
    parser.add_argument('io', type=str,
            help="IO assignment constraint")
    parser.add_argument('wrapper', type=argparse.FileType('w'),
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
    context = ArchitectureContext.unpickle(args.context)
    tb_top = find_verilog_top(args.testbench, args.testbench_top)
    tb_top.parameters = parse_parameters(args.testbench_parameters)
    behav_top = find_verilog_top(args.model, args.model_top)
    behav_top.parameters =parse_parameters(args.model_parameters) 
    io_bindings = parse_io_bindings(args.io)

    # get verilog template
    env = jj.Environment(loader=jj.FileSystemLoader(
        os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates')))

    generate_testbench_wrapper(context, env.get_template('tb.tmpl.v'), args.wrapper, tb_top, behav_top, io_bindings)
