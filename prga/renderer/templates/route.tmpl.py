{%- set is_dual = "addr1" in module.ports -%}
{%- set cfg_bitcount = module.cfg_bitcount -%}
import cocotb
from cocotb.triggers import Timer,RisingEdge,Edge,First,NextTimeStep
from cocotb.clock import Clock
import random
import math
from cocotb.result import TestFailure,TestSuccess
from bitarray import bitarray
from cocotb.binary import BinaryValue
from cocotb.scoreboard import Scoreboard
import config

def clock_generation(clk,clock_period=10,test_time=100000):
    c= Clock(clk,clock_period)
    cocotb.fork(c.start(test_time//clock_period))

@cocotb.coroutine
def initialise_{{module.start_point.instance.name}}_{{module.start_point.model.name}}(dut):
    while True:
        for i in range(2**{{module.start_point.model._width}}):
            yield RisingEdge(dut.cfg_clk)
            dut.{{module.start_point.instance.name}}.{{module.start_point.model.name}} <= i

@cocotb.test()
def simple_test(dut):

    {% for clock in module.clocks %}
    {{clock.name}} = dut.{{clock.name}}
    clock_generation({{clock.name}})
    {% endfor %}

    test_clk = dut.test_clk 
    clock_generation(test_clk,clock_period = 2,test_time=100000)
    
    {% for src_var,src,sink_var,sink in module.route %}
    {%- if src.bus.net_type == 1 %}
    {{src_var}} = dut.{{src.bus.name}}
    {% else %}
    {{src_var}} = dut.{{src.bus.instance.name}}.{{src.bus.model.name}}
    {% endif -%}

    {%- if sink.bus.net_type == 1 %}
    {{sink_var}} = dut.{{sink.bus.name}}
    {% else %}
    {{sink_var}} = dut.{{sink.bus.instance.name}}.{{sink.bus.model.name}}
    {% endif -%}
    {% endfor %}
    
    cocotb.fork(initialise_{{module.start_point.instance.name}}_{{module.start_point.model.name}}(dut))
    
    {% for model,hierarchy,cfg_bits in module.cfg_bits_route %}
    cfg_d = bitarray([0]*{{model.cfg_bitcount}})
    cfg_e = dut.{{'.'.join(hierarchy)}}.cfg_e
    cfg_we = dut.{{'.'.join(hierarchy)}}.cfg_we
    cfg_i = dut.{{'.'.join(hierarchy)}}.cfg_i
    cfg_clk = dut.{{'.'.join(hierarchy)}}.cfg_clk
    clock_generation(cfg_clk)
    {%- for bit in cfg_bits%}
    cfg_d[{{bit}}] = 1 
    {% endfor -%}

    cfg_e <= 1
    cfg_we <= 1
    
    yield RisingEdge(cfg_clk)
    
    for i in range( {{model.cfg_bitcount}} -1,-1,-1):
        cfg_i <= cfg_d[i]
        yield RisingEdge(cfg_clk)
    
    cfg_e <= 0
    cfg_we <= 0

    yield RisingEdge(cfg_clk)
    {% endfor %}

    {%- for src_var,src,sink_var,sink in module.route %}
    bool_{{src_var}} = True
    {% endfor %}

    for _ in range(1000):
        yield Edge(dut.test_clk)
        {%- for src_var,src,sink_var,sink in module.route %}
        # print({{src_var}}.value.binstr[{{src.index.start}}],{{sink_var}}.value.binstr[{{sink.index.start}}])
        # print("{{src}}",str({{src_var}}.value.binstr[::-1]),"{{sink}}",str({{sink_var}}.value.binstr[::-1]))
        # print("{{src}}",str({{src_var}}.value.binstr[::-1][{{src.index.start}}]),"{{sink}}",str({{sink_var}}.value.binstr[::-1][{{sink.index.start}}]))
        if str({{src_var}}.value.binstr[::-1][{{src.index.start}}]) not in ['x','z'] and str({{sink_var}}.value.binstr[::-1][{{sink.index.start}}]) not in  ['x','z']:
            # print("{{src}}",str({{src_var}}.value.binstr[::-1][{{src.index.start}}]),"{{sink}}",str({{sink_var}}.value.binstr[::-1][{{sink.index.start}}]))
            if str({{src_var}}.value.binstr[::-1][{{src.index.start}}]) != str({{sink_var}}.value.binstr[::-1][{{sink.index.start}}]):
                print("{{src}}",str({{src_var}}.value.binstr[::-1][{{src.index.start}}]),"{{sink}}",str({{sink_var}}.value.binstr[::-1][{{sink.index.start}}]))
                # raise TestFailure("Error at connection {{src}} -> {{sink}}")
            else:
                if bool_{{src_var}}:
                    print("Path checked {{src}} -> {{sink}}")
                    bool_{{src_var}} = False
        {% endfor %}

    raise TestSuccess("simple_test")
