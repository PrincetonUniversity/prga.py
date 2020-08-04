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

def clock_generation(clk,clock_period=10,test_time=100000):
    c= Clock(clk,clock_period)
    cocotb.fork(c.start(test_time//clock_period))

{% for port in module.input_ports %}
@cocotb.coroutine
def initialise_{{port.name}}(dut):
    while True:
        for i in range(2**{{port._width}}):
            yield RisingEdge(dut.cfg_clk)
            dut.{{port.name}} <= i
            # print(dut.{{port.name}}.value)
{% endfor %}

@cocotb.test()
def simple_test(dut):

    {% for clock in module.clocks %}
    {{clock.name}} = dut.{{clock.name}}
    clock_generation({{clock.name}})
    {% endfor %}

    test_clk = dut.test_clk 
    clock_generation(test_clk,clock_period = 2,test_time=100000)
    
    cfg_e = dut.cfg_e
    cfg_we = dut.cfg_we
    cfg_i = dut.cfg_i
    
    for i in range({{cfg_bitcount}}):
        cfg_d[i] = random.choice([0,1])
   
    cfg_e <= 1
    cfg_we <= 1
    
    yield RisingEdge(dut.cfg_clk)
    
    for i in range( {{module.cfg_bitcount}} -1,-1,-1):
        cfg_i <= cfg_d[i]
        yield RisingEdge(dut.cfg_clk)
    
    cfg_e <= 0
    cfg_we <= 0

    yield RisingEdge(dut.cfg_clk)

    
    {% for port in module.input_ports %}
    cocotb.fork(initialise_{{port.name}}(dut))
    {% endfor %}



    {%- for instance,test_hierarchy,offset in module.primitives %}
    # Switches need to be check
    # Do not use random testing for switches
    {%- if instance.model.module_class.is_primitive and instance.model.primitive_class.is_lut %}
    {% set bitcount = instance.model.cfg_bitcount %}
    cfg_d_{{'_'.join(test_hierarchy)}} = dut.{{'.'.join(test_hierarchy)}}.i_cfg_data.cfg_d.value.binstr[::-1]
    for i in range({{offset+bitcount-1}},{{offset-1}},-1):
        if int(cfg_d[i])!= int(cfg_d_{{'_'.join(test_hierarchy)}}[i-{{offset}}]):
            raise TestFailure("cfg_d not properly setup for {{'->'.join(test_hierarchy)}}")
    {% endif -%}
    {% endfor -%}

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
        # print({{src_var}}.value[{{src.index.start}}],{{sink_var}}.value[{{sink.index.start}}])
        if str({{src_var}}.value[{{src.index.start}}]) not in ['x','z'] and str({{sink_var}}.value[{{sink.index.start}}]) not in  ['x','z']:
            if str({{src_var}}.value[{{src.index.start}}]) != str({{sink_var}}.value[{{sink.index.start}}]):
                # print("{{src}}",str({{src_var}}.value[{{src.index.start}}]),"{{sink}}",str({{sink_var}}.value[{{sink.index.start}}]))
                raise TestFailure("Error at connection {{src}} -> {{sink}}")
    {% endfor -%}
