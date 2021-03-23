import os
ADDITIONAL_TEMPLATE_SEARCH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'templates')

from .softregs import SoftRegType, SoftReg, SoftRegIntf
__all__ = ["SoftRegType", "SoftReg", "SoftRegIntf"]
