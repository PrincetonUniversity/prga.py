# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from prga.arch.common import Orientation
from collections import namedtuple

__all__ = ['ChannelCoverage']

# ----------------------------------------------------------------------------
# -- Channel Coverage --------------------------------------------------------
# ----------------------------------------------------------------------------
class ChannelCoverage(namedtuple('ChannelCoverage', 'north east south west')):
    """Tuple used to define if the routing channels are covered by an array. 

    Args:
        north (:obj:`bool`): if routing channel to the north is covered
        east (:obj:`bool`): if routing channel to the east is covered
        south (:obj:`bool`): if routing channel to the south is covered
        west (:obj:`bool`): if routing channel to the west is covered
    """
    def __new__(cls, north = False, east = False, south = False, west = False):
        return super(ChannelCoverage, cls).__new__(cls, north, east, south, west)

    def __getitem__(self, key):
        if isinstance(key, Orientation):
            return key.switch(north = self.north, east = self.east,
                    south = self.south, west = self.west)
        else:
            return super(ChannelCoverage, self).__getitem__(key)
