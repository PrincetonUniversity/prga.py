# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.net.common import PortDirection
from prga.algorithm.util.array import get_external_port
from prga.config.bitchain.algorithm.bitstream import get_config_bit_count, get_config_bit_offset
from prga.flow.context import ArchitectureContext
from prga.exception import PRGAAPIError
from prga.util import enable_stdout_logging

from prga_tools.util.verilog import find_verilog_top, parse_io_bindings

import jinja2 as jj
import os
import re
import logging

_logger = logging.getLogger(__name__)
_reprog_width = re.compile('^.*?\[\s*(?P<start>\d+)\s*:\s*(?P<end>\d+)\s*\].*?$')

__all__ = ['generate_testbench_wrapper']

def _update_config_list(context, module, config, prefix = '', base = 0):
    config_bit_offset = get_config_bit_offset(context, module)
    cur = module.physical_ports['cfg_o']
    while True:
        prev = cur.source
        if not prev.net_type.is_pin:
            break
        if prev.parent.model.is_leaf_module:
            global_base = base + config_bit_offset[prev.parent.name]
            local_base = 0
            length = get_config_bit_count(context, prev.parent.model)
            while local_base < length:
                addr = global_base // 64
                low = global_base % 64
                high = min(low + length - local_base, 64)
                num_bits = high - low
                config.append( (
                    '{}{}.cfg_d[{}:{}]'.format(prefix, prev.parent.name, local_base + num_bits - 1, local_base),
                    addr, low, high - 1) )
                global_base += num_bits
                local_base += num_bits
        else:
            _update_config_list(context, prev.parent.model, config,
                    prefix + prev.parent.name + '.', base + config_bit_offset[prev.parent.name])
        cur = prev.parent.physical_pins['cfg_i']

def generate_testbench_wrapper(context, ostream, tb_top, behav_top, io_bindings):
    """Generate simulation testbench wrapper.

    Args:
        context (`ArchitectureContext`): The architecture context of the custom FPGA
        ostream (file-like object): Output file
        tb_top (``VerilogModule``): Top-level module of the testbench of the behavioral model
        behav_top (``VerilogModule``): Top-level module of the behavioral model
        io_bindings (:obj:`Mapping` [:obj:`tuple` [:obj:`int`, :obj:`int`, :obj:`int`], :obj:`str` ]): Mapping from
            \(x, y, subblock\) to port name in the behavioral model

    See `hdlparse <//kevinpt.github.io/hdlparse/apidoc/hdlparse.html#hdlparse.verilog_parser.VerilogModule>`_ for info
    on ``VerilogModule``.
    """
    # get verilog template
    env = jj.Environment(loader=jj.FileSystemLoader(
        os.path.join(os.path.abspath(os.path.dirname(__file__)), 'templates')))

    # configuration bits
    config_info = {}
    total_config_bits = config_info['bs_total_size'] = context.config_circuitry_delegate.total_config_bits
    last_bit_index = config_info['bs_last_bit_index'] = (total_config_bits - 1) % 64
    num_qwords = total_config_bits // 64
    if last_bit_index != 63:
        num_qwords += 1
    config_info['bs_num_qwords'] = num_qwords

    # extract testbench information
    tb_info = {'name': tb_top.name, 'parameters': {}}

    # extract behavioral model information
    behav_info = {'name': behav_top.name, 'parameters': {}}
    ports = behav_info['ports'] = {}
    for port in behav_top.ports:
        ports[port.name] = {'name': port.name, 'direction': port.mode.strip()}
        matched = _reprog_width.match(port.data_type)
        if matched is not None:
            ports[port.name]['width'] = abs(int(matched.group('start')) - int(matched.group('end'))) + 1

    # extract io bindings
    impl_info = {'name': context.top.name, 'config': []}
    ports = impl_info['ports'] = {}
    for name, (x, y, subblock) in iteritems(io_bindings):
        direction = 'input'
        if name.startswith('out:'):
            name = name[4:]
            direction = 'output'
        # 1. is it a valid port in the behavioral model?
        behav_port = behav_info['ports'].get(name)
        if behav_port is None:
            raise PRGAAPIError("Port '{}' is not found in design '{}'"
                    .format(name, behav_top.name))
        elif behav_port['direction'] != direction:
            raise PRGAAPIError("Direction mismatch: port '{}' is {} in behavioral model but {} in IO bindings"
                    .format(name, behav_port.direction, direction))
        # 2. is (x, y, subblock) an IO block?
        port = get_external_port(context.top, (x, y), subblock,
                PortDirection.input_ if direction == 'input' else PortDirection.output)
        if port is None:
            raise PRGAAPIError("No {} IO port found at position ({}, {}, {})"
                    .format(direction, x, y, subblock))
        # 3. bind
        ports[port.name] = behav_port

    # configuration info
    _update_config_list(context, context.top, impl_info['config'])

    # generate testbench wrapper
    env.get_template('tb.tmpl.v').stream({
        "config": config_info,
        "behav": behav_info,
        "tb": tb_info,
        "impl": impl_info,
        "iteritems": iteritems,
        "itervalues": itervalues,
        }).dump(ostream)

import argparse
parser = argparse.ArgumentParser(
        description="Testbench generator for bitchain-style configuration circuitry")

parser.add_argument('context', type=argparse.FileType(OpenMode.r),
        help="Pickled architecture context object")
parser.add_argument('io', type=str,
        help="IO assignment constraint")
parser.add_argument('wrapper', type=argparse.FileType('w'),
        help="Generated Verilog testbench wrapper")
parser.add_argument('-t', '--testbench', type=str, nargs='+', dest="testbench",
        help="Testbench file(s) for behavioral model")
parser.add_argument('-m', '--model', type=str, nargs='+', dest="model",
        help="Source file(s) for behavioral model")
parser.add_argument('--testbench_top', type=str,
        help="Top-level module name of the testbench. Required if the testbench comprises multiple files/modules")
parser.add_argument('--model_top', type=str,
        help="Top-level module name of the behavioral model. Required if the model comprises multiple files/modules")

if __name__ == '__main__':
    args = parser.parse_args()
    enable_stdout_logging(__name__, logging.INFO)
    context = ArchitectureContext.unpickle(args.context)
    tb_top = find_verilog_top(args.testbench, args.testbench_top)
    behav_top = find_verilog_top(args.model, args.model_top)
    io_bindings = parse_io_bindings(args.io)
    generate_testbench_wrapper(context, args.wrapper, tb_top, behav_top, io_bindings)
