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

# config.cfg_d = bitarray([0]*{{module.cfg_bitcount}})

def clock_generation(clk,clock_period=10,test_time=100000):
    c= Clock(clk,clock_period)
    cocotb.fork(c.start(test_time//clock_period))


{%- for instance,test_hierarchy,offset in module.primitives %}
{%- if instance.model.module_class.is_primitive and instance.model.primitive_class.is_lut %}
@cocotb.coroutine
def test_{{'_'.join(test_hierarchy)}}(dut): 
    {% set bitcount = instance.model.cfg_bitcount %}
    input_{{'_'.join(test_hierarchy)}} = dut.{{'.'.join(test_hierarchy)}}.bits_in
    out = dut.{{'.'.join(test_hierarchy)}}.out
    while True:
        for i in range(0,{{bitcount}}):
            input_{{'_'.join(test_hierarchy)}} <= i
            yield RisingEdge(dut.{{'.'.join(test_hierarchy)}}.cfg_clk)
            output = out.value.integer
            yield NextTimeStep()
            # Check this step
            if output != config.cfg_d[{{offset}}+i]:
                raise TestFailure("[ERROR]")  

    {% endif -%}
    
    {%- if instance.model.module_class.is_primitive and instance.model.primitive_class.is_flipflop %}
@cocotb.coroutine
def test_{{'_'.join(test_hierarchy)}}(dut): 
    {% if module._allow_multisource %}
        {%- if test_hierarchy|length > 1 %}
    D = dut.{{'.'.join(test_hierarchy[:-1])}}.{{'.'.join(NetUtils.get_multisource(instance.pins['D']).node[::-1])}} 
        {% else %}
    D = dut.{{'.'.join(NetUtils.get_multisource(instance.pins['D']).node[::-1])}} 
        {% endif -%}
    {% else %}
        {%- if test_hierarchy|length > 1 %}
    D = dut.{{'.'.join(test_hierarchy[:-1])}}.{{'.'.join(NetUtils.get_source(instance.pins['D']).node[::-1])}} 
        {% else %}
    D = dut.{{'.'.join(NetUtils.get_source(instance.pins['D']).node[::-1])}} 
        {% endif -%}
    {% endif %}

    Q = dut.{{'.'.join(test_hierarchy)}}.Q
    cfg_e = dut.{{'.'.join(test_hierarchy)}}.cfg_e
    while True:
        prev_d = D.value
        yield RisingEdge(dut.{{'.'.join(test_hierarchy)}}.clk)
        if not cfg_e.value.integer:       
            if Q.value.binstr != 'x' and Q.value.binstr != 'z':
                if Q.value.binstr != prev_d.binstr:
                    dut._log.info("Error "+str(i))
                    # raise TestFailure("Test Failed at "+str(i)+"iteration when D="+D.value.binstr+" and Q="+Q.value.binstr)
                    
{% endif -%}
{% endfor -%}

{%- for stack_connections in module.stack %}
@cocotb.test()
def simple_test_{{loop.index}}(dut):

    {%- for clock in module.clocks %}
    {{clock.name}} = dut.{{clock.name}}
    clock_generation({{clock.name}})
    {% endfor -%} 
    test_clk = dut.test_clk 
    clock_generation(test_clk,clock_period = 2,test_time=100000)
    
    
    {% for instance,test_hierarchy,offset in module.primitives %}
    {%- if instance.model.module_class.is_primitive and instance.model.primitive_class.is_lut %}
    {%- set bitcount = instance.model.cfg_bitcount -%}
    input_{{'_'.join(test_hierarchy)}} = dut.{{'.'.join(test_hierarchy)}}.bits_in
    config.cfg_d[{{offset+bitcount-1}}:{{offset}}] = 0
    config.cfg_d[{{offset+bitcount-1}}] = 1
    # {% elif instance.model.module_class == 9 %}
    # {%- set bitcount = instance.model.cfg_bitcount -%}
    # config.cfg_d[{{offset+bitcount-1}}:{{offset}}] = 0
    # config.cfg_d[{{offset+bitcount-1}}] = 1    
    {% endif -%}
    {% endfor %}

    {%- for src_var,src,sink_var,sink,cfg_bits in stack_connections %}
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
    config.cfg_d[{{bits}}] = 1
    {% endfor -%}
    {% endfor -%}


    cfg_e = dut.cfg_e
    cfg_we = dut.cfg_we
    cfg_i = dut.cfg_i
   
    cfg_e <= 1
    cfg_we <= 1
    
    yield RisingEdge(dut.cfg_clk)
    
    for i in range( {{module.cfg_bitcount}} -1,-1,-1):
        cfg_i <= config.cfg_d[i]
        yield RisingEdge(dut.cfg_clk)
    
    cfg_e <= 0
    cfg_we <= 0

    yield RisingEdge(dut.cfg_clk)

    {%- for instance,test_hierarchy,offset in module.primitives %}
    {%- if instance.model.module_class.is_primitive and instance.model.primitive_class.is_lut %}
    {% set bitcount = instance.model.cfg_bitcount %}
    cfg_d_{{'_'.join(test_hierarchy)}} = dut.{{'.'.join(test_hierarchy)}}.cfg_d.value.binstr[::-1]
    for i in range({{offset+bitcount-1}},{{offset-1}},-1):
        if int(config.cfg_d[i])!= int(cfg_d_{{'_'.join(test_hierarchy)}}[i-{{offset}}]):
            raise TestFailure("cfg_d not properly setup for {{'->'.join(test_hierarchy)}}")
    # {% elif instance.model.module_class == 9 %}
    # {%- set bitcount = instance.model.cfg_bitcount -%}
    # cfg_d_{{'_'.join(test_hierarchy)}} = dut.{{'.'.join(handle_names_with_underscore(test_hierarchy))}}.cfg_d.value.binstr[::-1]
    # # cfg_d__sw_o = dut._HierarchyObject__get_sub_handle_by_name("_sw_o").cfg_d.value.binstr[::-1]
    # for i in range({{offset+bitcount-1}},{{offset-1}},-1):
    #     if int(config.cfg_d[i])!= int(cfg_d_{{'_'.join(test_hierarchy)}}[i-{{offset}}]):
    #         raise TestFailure("cfg_d not properly setup for {{'->'.join(test_hierarchy)}}")
    {% endif -%}
    {%- if instance.model.module_class.is_primitive and (instance.model.primitive_class.is_lut or instance.model.primitive_class.is_flipflop) %}
    cocotb.fork(test_{{'_'.join(test_hierarchy)}}(dut))
    {% endif -%}
    {% endfor -%}


    for _ in range(1000):
        yield Edge(dut.test_clk)
        {% for src_var,src,sink_var,sink,cfg_bits in stack_connections %}
        # print({{src_var}}.value[{{src.index.start}}],{{sink_var}}.value[{{sink.index.start}}])
        if str({{src_var}}.value.binstr[::-1][{{src.index.start}}]) not in ['x','z'] and str({{sink_var}}.value.binstr[::-1][{{sink.index.start}}]) not in  ['x','z']:
            if str({{src_var}}.value.binstr[::-1][{{src.index.start}}]) != str({{sink_var}}.value.binstr[::-1][{{sink.index.start}}]):
                # print("{{src}}",str({{src_var}}.value[{{src.index.start}}]),"{{sink}}",str({{sink_var}}.value[{{sink.index.start}}]))
                raise TestFailure("Error at connection {{src}} -> {{sink}}")
        {% endfor %}

    raise TestSuccess("simple_test_{{loop.index}}")
{% endfor -%}