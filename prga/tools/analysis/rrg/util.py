# -*- encoding: ascii -*-

import networkx as nx
import lxml.etree as et

__all__ = ['read_vpr_rrg']

class _VPRRRGTarget(object):

    def __init__(self, g, ignore_iopin, keep_srcsink, info_level):
        self.g = g
        self.ignore_iopin = ignore_iopin
        self.keep_srcsink = keep_srcsink
        self.info_level = info_level
        self.path = []
        self._cur_node = None

    def start(self, tag, attrs, nsmap = None):
        if tag == "node":
            if ((attrs["type"] in ("SOURCE", "SINK") and self.keep_srcsink) or
                    (attrs["type"] in ("IPIN", "OPIN") and not self.ignore_iopin) or
                    (attrs["type"] in ("CHANX", "CHANY"))):
                i = self._cur_node = int(attrs["id"])
                if "direction" in attrs and self.info_level == 1:
                    self.g.add_node(i, **{"type": attrs["type"], "direction": attrs["direction"]})
                else:
                    self.g.add_node(i, **{"type": attrs["type"]})
        elif self.path and self.path[-1] == "node" and self.info_level == 1 and self._cur_node is not None:
                self.g.nodes[self._cur_node][tag] = attrs
        elif tag == "edge":
            src_node = int(attrs["src_node"])
            sink_node = int(attrs["sink_node"])
            if src_node in self.g and sink_node in self.g:
                if self.info_level == 1:
                    self.g.add_edge(src_node, sink_node, switch_id = attrs["switch_id"])
                else:
                    self.g.add_edge(src_node, sink_node)
        self.path.append( tag )

    def end(self, tag):
        self.path.pop()

    def data(self, data):
        pass

    def close(self):
        pass

def read_vpr_rrg(istream, ignore_iopin = False, keep_srcsink = False, info_level = 0):
    """Read VPR's RRG graph and extract the connection graph.

    Args:
        ignore_iopin (:obj:`bool`): If set, IPIN/OPIN nodes are omitted in the graph
        keep_srcsink (:obj:`bool`): If set, SOURCE/SINK nodes are added to the graph. This argument is overriden when
            ``ignore_iopin`` is set
        info_level (:obj:`int`): Level of information stored in the graph:
                - [0] no information is stored. only the abstract graph structure is preserved
                - [1] all information is stored in the graph

    Returns:
        ``networkx.DiGraph``
    """
    g = nx.DiGraph()
    et.parse(istream, parser = et.XMLParser(target = _VPRRRGTarget(g,
        ignore_iopin, not ignore_iopin and keep_srcsink, info_level)))
    return g
