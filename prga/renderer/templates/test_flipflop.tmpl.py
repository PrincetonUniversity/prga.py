import cocotb
from cocotb.triggers import Timer,RisingEdge,Edge,First,NextTimeStep
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
    clk = dut.clk
    clock_generation(clk)
    # Signals
    D = dut.D
    Q = dut.Q
    cfg_e = dut.cfg_e
    
    for _ in range(3):
        yield RisingEdge(clk)
        cfg_e <= 1

    D <= 0
    cfg_e <= 0
    yield RisingEdge(clk)

    for i in range(100):
        prev_d = D.value.integer
        D <= random.choice([0,1])
        yield RisingEdge(clk)
        if not cfg_e.value.integer:       
            if Q.value.binstr != 'x' and Q.value.binstr != 'z':
                if Q.value.integer != prev_d:
                    dut._log.info("Error "+str(i))
                    # raise TestFailure("Test Failed at "+str(i)+"iteration when D="+D.value.binstr+" and Q="+Q.value.binstr)

