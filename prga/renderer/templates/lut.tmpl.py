import cocotb
from cocotb.triggers import Timer,RisingEdge,Edge,First
from cocotb.clock import Clock
import random
import math
from cocotb.result import TestFailure
from cocotb.binary import BinaryValue
from cocotb.scoreboard import Scoreboard
from config import *

# cocotb coroutine for driving the clocks
def clock_generation(clk,clock_period=10,test_time=100000):
    c= Clock(clk,clock_period)
    cocotb.fork(c.start(test_time//clock_period))
    
@cocotb.test()
def simple_test(dut):
    """
    cocotb test for testing the primitive look-up table
    """

    # Initialize the clock
    clock_generation(dut.cfg_clk)
    clk = dut.cfg_clk

    # Signals
    input = dut.bits_in
    out = dut.out
    cfg_e = dut.i_cfg_data.cfg_e
    cfg_we = dut.i_cfg_data.cfg_we
    cfg_i = dut.i_cfg_data.cfg_i
    cfg_o = dut.i_cfg_data.cfg_o
    
    # No. of input bits
    n_input = int(math.log({{module.cfg_bitcount}},2))

    # Setting up LUT
    # Set the value of cfg_d
    cfg_e <= 1
    cfg_we <= 1
    cfd = []
    n_bits = 2**n_input
    for _ in range(n_bits):
        bit = random.choice([0,1])
        cfd.insert(0,bit)
        cfg_i <= bit
        yield RisingEdge(clk)
    
    cfg_e <= 0
    cfg_we <= 0
    yield RisingEdge(clk)

    #######################################################
    ## TESTING ############################################
    #######################################################

    # Testing the LUT
    for i in range(0,n_bits):
        input <= i
        yield RisingEdge(clk)
        output = out.value.integer
        print(input.value)
        if output != cfd[i]:
            raise TestFailure("[ERROR]")  