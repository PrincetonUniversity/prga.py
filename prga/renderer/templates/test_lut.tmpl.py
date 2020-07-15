import cocotb
from cocotb.triggers import Timer,RisingEdge,Edge,First
from cocotb.clock import Clock
import random
import math
from cocotb.result import TestFailure
from cocotb.binary import BinaryValue
from cocotb.scoreboard import Scoreboard

def clock_generation(clk,clock_period=10,test_time=10000):
    c= Clock(clk,clock_period)
    cocotb.fork(c.start(test_time//clock_period))
    
@cocotb.test()
def simple_test(dut):
    """Test bench from scratch for 4 input LUT"""
    
    clock_generation(dut.cfg_clk)
    clk = dut.cfg_clk
    # Signals
    input = dut.{{instance.test_hierarchy}}bits_in
    out = dut.{{instance.test_hierarchy}}out
    cfg_e = dut.{{instance.test_hierarchy}}i_cfg_data.cfg_e
    cfg_we = dut.{{instance.test_hierarchy}}i_cfg_data.cfg_we
    cfg_i = dut.{{instance.test_hierarchy}}i_cfg_data.cfg_i
    cfg_o = dut.{{instance.test_hierarchy}}i_cfg_data.cfg_o
    
    # No. of input bits
    # n_input = input()
    n_input = int(math.log({{instance.model.cfg_bitcount}},2))

    # Setting up LUT
    # Set the value of cfd
    cfg_e <= 1;
    cfg_we <= 1;
    cfd = []
    n_bits = 2**n_input
    for _ in range(n_bits):
        bit = random.choice([0,1])
        cfd.insert(0,bit)
        cfg_i <= bit
        yield RisingEdge(clk)
    
    cfg_e <= 0;
    cfg_we <= 0;
    yield RisingEdge(clk)

    for i in range(0,n_bits):
        input <= i
        yield RisingEdge(clk)
        output = out.value.integer

        if output != cfd[i]:
            raise TestFailure("[ERROR]")  

@cocotb.test()
def changing_config(dut):
    """This is a test where the configuartion of LUT can randomly change"""
    
    clock_generation(dut.cfg_clk)
    clk = dut.cfg_clk

    # Signals
    input = dut.{{instance.test_hierarchy}}bits_in
    out = dut.{{instance.test_hierarchy}}out
    cfg_e = dut.{{instance.test_hierarchy}}i_cfg_data.cfg_e
    cfg_we = dut.{{instance.test_hierarchy}}i_cfg_data.cfg_we
    cfg_i = dut.{{instance.test_hierarchy}}i_cfg_data.cfg_i
    cfg_o = dut.{{instance.test_hierarchy}}i_cfg_data.cfg_o
    
    # No. of input bits
    n_input = int(math.log({{instance.model.cfg_bitcount}},2))

    # Setting up LUT
    # Set the value of cfd
    cfg_e <= 1;
    cfg_we <= 1;
    cfd = []
    n_bits = 2**n_input
    for _ in range(n_bits):
        bit = random.choice([0,1])
        cfd.append(bit)
        cfg_i <= bit
        yield RisingEdge(clk)
    cfd.reverse()
    
    cfg_e <= 0;
    cfg_we <= 0;
    yield RisingEdge(clk)

    # Set this to true to change the configuration in the middle of the test
    change_config = True
    for i in range(0,n_bits):
        input <= i
        yield RisingEdge(clk)
        output = out.value.integer

        if output != cfd[i]:
            # dut._log.info(str(i))
            # dut._log.info("[ERROR]")
            raise TestFailure("[ERROR]")

        # Change Config 
        if(change_config & random.choice(range(100007)) % 2):
            # dut._log.info("Changing cfd")
            cfg_e <= 1;
            cfg_we <= 1;
            bit = random.choice([0,1])
            cfd.insert(0,bit)
            cfd.pop()
            cfg_i <= bit
            yield RisingEdge(clk)
            cfg_e <= 0;
            cfg_we <= 0;
            yield RisingEdge(clk)    