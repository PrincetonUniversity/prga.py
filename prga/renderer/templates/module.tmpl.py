{%- set cfg_bitcount = module.cfg_bitcount -%}
import cocotb
from cocotb.triggers import Timer,RisingEdge,Edge,First,NextTimeStep
from cocotb.clock import Clock
import random
import math
from cocotb.result import TestFailure
from bitarray import bitarray
from cocotb.binary import BinaryValue
from cocotb.scoreboard import Scoreboard
cfg_d = bitarray([0]*{{cfg_bitcount}})

def clock_generation(clk,clock_period=10,test_time=10000):
    c= Clock(clk,clock_period)
    cocotb.fork(c.start(test_time//clock_period))

{% for port in module.input_ports %}
@cocotb.coroutine
def initialise_{{port.name}}(dut):
    while True:
        for i in range(2**{{port._width}}):
            yield RisingEdge(dut.clk)
            dut.{{port.name}} <= i
            print(dut.{{port.name}}.value)
{% endfor %}
@cocotb.test()
def simple_test(dut):

    {% for clock in module.clocks %}
    {{clock.name}} = dut.{{clock.name}}
    clock_generation({{clock.name}})
    {% endfor %}

    test_clk = dut.test_clk 
    clock_generation(test_clk,clock_period = 2,test_time = 10000)
    
    {% for port in module.input_ports %}
    cocotb.fork(initialise_{{port.name}}(dut))
    {% endfor %}

    {% for src_var,src,sink_var,sink in module.connections %}
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

    while True:
        yield Edge(dut.test_clk)
        {%- for src_var,src,sink_var,sink in module.connections %}
        # print("{{src}}",{{src_var}}.value[{{src.index.start}}],"{{sink}}",{{sink_var}}.value[{{sink.index.start}}])
        if {{src_var}}.value[{{src.index.start}}] != 'x' and {{src_var}}.value[{{src.index.start}}] != 'z' and {{sink_var}}.value[{{sink.index.start}}] != 'x' and {{sink_var}}.value[{{sink.index.start}}!='z':  
            # print({{src_var}}.value[{{src.index.start}}],{{sink_var}}.value[{{sink.index.start}}])
            if int({{src_var}}.value[{{src.index.start}}]) != int({{sink_var}}.value[{{sink.index.start}}]):
                raise TestFailure("Error at connection {{src}} -> {{sink}}")
    {% endfor -%}