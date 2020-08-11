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
def initialise_{{module.start_pin.bus.instance.name}}_{{module.start_pin.bus.model.name}}(dut):
    while True:
        for i in range(2**{{module.start_pin.bus.model._width}}):
            {% if cfg_bitcount %}
            yield RisingEdge(dut.cfg_clk)
            {% else  %}
            yield RisingEdge(dut.test_clk)
            {% endif %}

            dut.{{module.start_pin.bus.instance.name}}.{{module.start_pin.bus.model.name}} <= i

@cocotb.test()
def simple_test(dut):

    {% for clock in module.clocks %}
    {{clock.name}} = dut.{{clock.name}}
    clock_generation({{clock.name}})
    {% endfor %}

    test_clk = dut.test_clk 
    clock_generation(test_clk,clock_period = 2,test_time=100000)
    
    {%- if cfg_bitcount %}
    cfg_d = bitarray([0]*{{cfg_bitcount}})
    cfg_e = dut.cfg_e
    cfg_we = dut.cfg_we
    cfg_i = dut.cfg_i
    {% endif -%}


    {%- for src_var,src,sink_var,sink in module.route %}
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
    {%- for bits in cfg_bits%}
    cfg_d[{{bits}}] = 1
    {% endfor -%}
    {% endfor -%}
    
    cocotb.fork(initialise_{{module.start_pin.bus.instance.name}}_{{module.start_pin.bus.model.name}}(dut))

    {%- for instance,cfg_bits in module.cfg_bits %}
        cfg_d[{{cfg_bits}}] = 1
    {% endfor %}

    cfg_e <= 1
    cfg_we <= 1
    
    yield RisingEdge(dut.cfg_clk)
    
    for i in range( {{module.cfg_bitcount}} -1,-1,-1):
        cfg_i <= cfg_d[i]
        yield RisingEdge(dut.cfg_clk)
    
    cfg_e <= 0
    cfg_we <= 0

    yield RisingEdge(dut.cfg_clk)

    for _ in range(1000):
        yield Edge(dut.test_clk)
        {%- for src_var,src,sink_var,sink in module.route %}
        # print({{src.bus.model.name}}.value[{{src.index.start}}],{{sink.bus.model.name}}.value[{{sink.index.start}}])
        if str({{src.bus.model.name}}.value.binstr[::-1][{{src.index.start}}]) not in ['x','z'] and str({{sink.bus.model.name}}.value.binstr[::-1][{{sink.index.start}}]) not in  ['x','z']:
            if str({{src.bus.model.name}}.value.binstr[::-1][{{src.index.start}}]) != str({{sink.bus.model.name}}.value.binstr[::-1][{{sink.index.start}}]):
            #    print("{{src}}",str({{src.bus.model.name}}.value[::-1][{{src.index.start}}]),"{{sink}}",str({{sink.bus.model.name}}.value[::-1][{{sink.index.start}}]))
                raise TestFailure("Error at connection {{src}} -> {{sink}}")
        {% endfor %}

    raise TestSuccess("simple_test")
