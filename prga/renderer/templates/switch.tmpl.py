{% set width = module.ports.i|length -%}
{% set cfg_bitcount = module.cfg_bitcount -%}
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
def initialise_i(dut):
    while True:
        for i in range(2**{{width}}):
            yield RisingEdge(dut.cfg_clk)
            dut.i <= i


@cocotb.test()
def simple_test(dut):

    cfg_d = bitarray([0]*{{cfg_bitcount}})

    cfg_clk = dut.cfg_clk 
    clock_generation(cfg_clk)

    test_clk = dut.test_clk 
    clock_generation(test_clk,clock_period = 2,test_time=100000)
    

    cfg_e = dut.cfg_e
    cfg_we = dut.cfg_we
    cfg_i = dut.cfg_i
    cfg_o = dut.cfg_o

    cfd = random.choice(range({{width}}))
    loop_cfd = cfd
    for i in range({{cfg_bitcount}}):
        cfg_d[i] = loop_cfd%2
        loop_cfd//=2

    cfg_e <= 1
    cfg_we <= 1
    
    yield RisingEdge(dut.cfg_clk)
    
    for i in range( {{cfg_bitcount}} -1,-1,-1):
        cfg_i <= cfg_d[i]
        yield RisingEdge(dut.cfg_clk)
    
    cfg_e <= 0
    cfg_we <= 0

    yield RisingEdge(dut.cfg_clk)

    cocotb.fork(initialise_i(dut))
    
    cfg_d_dut = dut.cfg_d.value.binstr[::-1]
    for i in range({{cfg_bitcount-1}},-1,-1):
        if int(cfg_d[i])!= int(cfg_d_dut[i]):
            raise TestFailure("cfg_d not properly setup")

    for _ in range(1000):
        yield Edge(dut.test_clk)
        if str(dut.i.value.binstr[::-1][cfd]) != str(dut.o.value.binstr):
            print("Error at input "+str(dut.i.value.integer))

    raise TestSuccess("simple_test")
