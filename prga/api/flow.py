# -*- encoding: ascii -*-
"""`Flow` and common passes."""

# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.flow.flow import Flow
from prga.flow.design import CompleteRoutingBox, CompleteSwitch, CompleteConnection, CompletePhysical
from prga.flow.rtlgen import GenerateVerilog
from prga.flow.vprgen import GenerateVPRXML
from prga.flow.ysgen import GenerateYosysResources
from prga.flow.opt import ZeroingBRAMWriteEnable, ZeroingBlockPins, ZeroingUnusedLUTInputs

__all__ = [
        "Flow",
        "CompleteRoutingBox",
        "CompleteSwitch",
        "CompleteConnection",
        "CompletePhysical",
        "GenerateVerilog",
        "GenerateVPRXML",
        "GenerateYosysResources",
        "ZeroingBRAMWriteEnable",
        "ZeroingBlockPins",
        "ZeroingUnusedLUTInputs",
        ]

