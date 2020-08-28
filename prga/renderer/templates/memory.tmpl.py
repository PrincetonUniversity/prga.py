{%- set dualport = "addr1" in module.ports %}
{%- set data_width = module.ports.data1|length -%}
{%- set mem_width = 2**module.ports.addr1|length -%}
import cocotb
from cocotb.triggers import Timer,RisingEdge,Edge,First,NextTimeStep
from cocotb.clock import Clock
import random
import math
from cocotb.result import TestFailure,TestSuccess
from bitarray import bitarray
from cocotb.binary import BinaryValue
from cocotb.scoreboard import Scoreboard

def clock_generation(clk,clock_period=10,test_time=100000):
    c= Clock(clk,clock_period)
    cocotb.fork(c.start(test_time//clock_period))

{%- if dualport %}
@cocotb.test()
def simple_test(dut):

    clk = dut.clk
    clock_generation(clk)

    dut.we1 <= 1
    yield RisingEdge(dut.clk)
    
    for i in range({{mem_width}}):
        dut.addr1 <= i
        dut.data1 <= i
        yield RisingEdge(dut.clk)
    
    dut.we1 <= 0
    yield RisingEdge(dut.clk)


    for i in range({{mem_width}}):
        dut.addr1 <= i
        dut.data1 <= i
        yield RisingEdge(clk)
        yield NextTimeStep()
        if dut.out1.value.integer != i%{{2**data_width}}:
            print("ERROR at addr input "+str(i))
    

    dut.we2 <= 1
    yield RisingEdge(dut.clk)
    
    for i in range({{mem_width}}):
        dut.addr2 <= i
        dut.data2 <= i
        yield RisingEdge(dut.clk)
    
    dut.we2 <= 0
    yield RisingEdge(dut.clk)


    for i in range({{mem_width}}):
        dut.addr2 <= i
        dut.data2 <= i
        yield RisingEdge(clk)
        yield NextTimeStep()
        if dut.out2.value.integer != i%{{2**data_width}}:
            print("ERROR at addr input "+str(i))

{% else %}
@cocotb.test()
def simple_test(dut):

    clk = dut.clk
    clock_generation(clk)

    dut.we <= 1
    yield RisingEdge(dut.clk)
    
    for i in range({{mem_width}}):
        dut.addr <= i
        dut.data <= i
        yield RisingEdge(dut.clk)
    
    dut.we <= 0
    yield RisingEdge(dut.clk)

    max_data = {{2**data_width}}%{{mem_width}} 

    for i in range({{mem_width}}):
        dut.addr <= i
        yield RisingEdge(clk)
        # print(dut.out.value.integer)
        # print(i%{{2**data_width}})
        # print()
        if dut.out.value.integer != i%{{2**data_width}}:
            print("ERROR at addr input "+str(i))
{% endif -%}
