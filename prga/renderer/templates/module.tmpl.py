import cocotb
from cocotb.triggers import Timer,RisingEdge,Edge,First
from cocotb.clock import Clock
import random
import math
from cocotb.result import TestFailure
from bitarray import bitarray
from cocotb.binary import BinaryValue
from cocotb.scoreboard import Scoreboard

def clock_generation(clk,clock_period=10,test_time=10000):
    c= Clock(clk,clock_period)
    cocotb.fork(c.start(test_time//clock_period))
    
@cocotb.test()
def simple_test(dut):
    """Test bench from scratch for 4 input LUT"""
    
    cfg_d = bitarray([0]*{{module.cfg_bitcount}})
    {% for clock in module.clocks %}
    {{clock.name}} = dut.{{clock.name}}
    clock_generation({{clock.name}})
    {% endfor %}

    {%  for instance,test_hierarchy,offset in module.primitives %}
    {% if instance.model.module_class.is_primitive and instance.model.primitive_class.is_lut %}
    {% set bitcount = instance.model.cfg_bitcount %}
    input_{{instance.name}} = dut.{{'.'.join(test_hierarchy)}}.bits_in
    out_{{instance.name}} = dut.{{'.'.join(test_hierarchy)}}.out
    cfg_e_{{instance.name}} = dut.{{'.'.join(test_hierarchy)}}.i_cfg_data.cfg_e
    cfg_we_{{instance.name}} = dut.{{'.'.join(test_hierarchy)}}.i_cfg_data.cfg_we
    cfg_i_{{instance.name}} = dut.{{'.'.join(test_hierarchy)}}.i_cfg_data.cfg_i
    cfg_o_{{instance.name}} = dut.{{'.'.join(test_hierarchy)}}.i_cfg_data.cfg_o
    cfg_d[{{offset+bitcount-1}}:{{offset}}] = 0
    cfg_d[{{offset+bitcount-1}}] = 1

    # Setting up LUT
    # Set the value of cfd
    cfg_e_{{instance.name}} <= 1
    cfg_we_{{instance.name}} <= 1
    
    yield RisingEdge({{NetUtils.get_source(instance.pins['cfg_clk']).name}})
    
    for i in range({{offset+bitcount-1}},{{offset-1}},-1):
        cfg_i_{{instance.name}} <= cfg_d[i]
        yield RisingEdge({{NetUtils.get_source(instance.pins['cfg_clk']).name}})
    
    cfg_e_{{instance.name}} <= 0
    cfg_we_{{instance.name}} <= 0

    yield RisingEdge({{NetUtils.get_source(instance.pins['cfg_clk']).name}})
   
    for i in range(0,{{bitcount}}):
        input_{{instance.name}} <= i
        yield RisingEdge(clk)
        # output = out.value.integer

        # if output != cfd[i]:
        #     raise TestFailure("[ERROR]")  

    {% endif %}

    # {% if instance.model.module_class.is_primitive and instance.model.primitive_class.is_flipflop %}
    # cfg_e_{{instance.name}} = dut.{{instance.test_hierarchy}}cfg_e
    # cfg_e_{{instance.name}} <= cfg_d[{{offset}}]
    # yield RisingEdge({{NetUtils.get_source(instance.pins['clk']).name}})

    # {% endif %}
    
    {% endfor %}