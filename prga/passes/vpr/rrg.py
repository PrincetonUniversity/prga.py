# -*- encoding: ascii -*-

from ..base import AbstractPass
from ...core.builder.array.array import ArrayBuilder
from ...core.common import (Orientation, ModuleView, Position)
from ...util import uno
from ...netlist import NetType, NetUtils, ModuleUtils
from ...xml import XMLGenerator

import logging
_logger = logging.getLogger(__name__)

import time, os, gzip
from itertools import product
import networkx as nx 

__all__ = ["VPR_RRG_Generation"]

# ----------------------------------------------------------------------------
# -- VPR rrg.xml Generation --------------------------------------------------
# ----------------------------------------------------------------------------
class VPR_RRG_Generation(AbstractPass):
    """Generate VPR's routing resource graph XML.
    
    Args:
        output_file (:obj:`str` of file-like object): The output file. If the file name ends with ".gz", the output
            file will be compressed using gzip

    Keyword Args:
        fasm (`FASMDelegate`): Overwrite the deafult fasm delegate provided by the context
    """

    # timing (`TimingDelegate`): Overwrite the default iming delegate provided by the context

    __slots__ = ['output_file', 'fasm', # 'timing',                       # customizable variables
            # temporary variables:
            'xml', 'tile2id', 'tilepin2ptc', 'switch2id', 'sgmt2id', 'sgmt2ptc',
            'chanx', 'chany', 'conn_graph', 'num_nodes', 'num_edges',
            ]
    def __init__(self, output_file, *, fasm = None):
        # , timing = None):
        self.output_file = output_file
        self.fasm = fasm
        # self.timing = timing

    @property
    def key(self):
        return "vpr.rrg"

    @property
    def dependences(self):
        return ("vpr.arch", )

    @property
    def is_readonly_pass(self):
        return True

    def _analyze_track(self, node):
        """Analyze a track node.

        Args:
            node (:obj:`Sequence` [:obj:`Hashable` ]): A reference node of a switch box pin (coalesced)

        Returns:
            orientation (`Orientation`): Expansion orientation
            lower_position (`Position`): The lower position of starting/ending channel
            higher_position (`Position`): The higher position of starting/ending channel
            ptc_position (:obj:`int`): Used to calculate the PTC for VPR
        """
        segment, ori = node[0].prototype, node[0].orientation
        sbox_position, corner = node[1]
        sbox_position = sum(node[2:], sbox_position)
        virtual_start = sbox_position + node[0].position
        low = high = (sbox_position + corner.case( (0, 0), (-1, 0), (0, -1), (-1, -1) ) +
                ori.case( (0, 1), (1, 0), (0, 0), (0, 0) ))
        dim, dir_ = ori.decompose()
        chan, step = dim.case((self.chanx, (1, 0)), (self.chany, (0, 1)))
        if dir_.is_inc:
            for _ in range(low[dim] - virtual_start[dim] + 1, segment.length):
                pos = high + step
                if chan[pos.x][pos.y]:
                    high = pos
                else:
                    break
        else:
            for _ in range(virtual_start[dim] - low[dim] + 1, segment.length):
                pos = low - step
                if chan[pos.x][pos.y]:
                    low = pos
                else:
                    break
        return ori, low, high, virtual_start[dim] - dir_.case(1, segment.length)

    def _analyze_blockpin(self, pin):
        """Analyze a block pin node.

        Args:
            pin (`Pin`): Hierarchical pin

        Returns:
            channel\_position (`Position`): Position of the routing channel
            orientation (`Orientation`): Orientation of the port
            block\_position (`Position`): Position of the parent block instance, used to calculate the
            xlow/ylow/xhigh/yhigh attributes for the src/sink nodes
        """
        port = pin.model
        block_position = ArrayBuilder.hierarchical_position(pin.instance)
        chan = block_position + port.position
        ori = port.orientation
        if ori is None:
            edges = tuple(ori for ori in Orientation if pin.instance.hierarchy[0].parent.edge[ori])
            if len(edges) != 1:
                raise PRGAInternalError("Unable to deduct orientation of pin {}".format(pin))
            ori = edges[0].opposite
        if ori.is_north:
            return chan, ori, block_position
        elif ori.is_east:
            return chan, ori, block_position
        elif ori.is_south:
            return chan - (0, 1), ori, block_position
        else:
            return chan - (1, 0), ori, block_position

    def _construct_conn_graph(self, top):
        node_id = 0

        def node_key(n):
            if n.net_type.is_port:
                return None
            elif n.instance.model.module_class.is_routing_box:
                if n.model.key.node_type.is_segment:
                    pos = ArrayBuilder.hierarchical_position(n.instance)
                    # adjust for Sbox corner and track orientation
                    pos += n.instance.hierarchy[0].key[1].case( (0, 0), (-1, 0), (0, -1), (-1, -1) )
                    pos += n.model.key.orientation.case( (0, 1), (1, 0), (0, 0), (0, 0) )
                    if not n.model.key.orientation.dimension.case(self.chanx, self.chany)[pos.x][pos.y]:
                        return None
                return NetUtils._reference(n)
            elif n.instance.model.module_class.is_block:
                return NetUtils._reference(n)
            else:
                return None

        def node_attrs(n):
            nonlocal node_id
            if n.instance.model.module_class.is_routing_box:
                if n.model.key.node_type.is_segment:
                    d = {"id": node_id, "type": n.model.key.orientation.dimension.case("CHANX", "CHANY")}
                    node_id += n.model.key.prototype.width
                    return d
                else:
                    return {}
            else:
                d = {"srcsink_id": node_id, "type": n.model.direction.case("IPIN", "OPIN")}
                if getattr(n.model, "vpr_equivalent_pins", False):
                    d.update({"id": node_id + 1, "equivalent": True})
                    node_id += 1 + len(n)
                else:
                    d["id"] = node_id + len(n)
                    node_id += 2 * len(n)
                return d

        _logger.info(" .. Start constructing coarse-grained routing graph for VPR RRG generation")
        t = time.time()
        self.conn_graph = ModuleUtils.reduce_conn_graph(top,
                coalesce_connections = True,
                blackbox_instance = lambda i: i.model.module_class.is_block or i.model.module_class.is_routing_box,
                node_key = node_key,
                node_attrs = node_attrs
                )
        t = time.time() - t
        _logger.info(" .. Completed constructing coarse-grained routing graph for VPR RRG generation")
        _logger.info("   .. Construction took %f seconds", t)

    def _tile_pinlist(self, pin, srcsink_ptc, iopin_ptc):
        subtile_name = pin.parent.name
        if 1 in pin.parent.instances:
            subtile_name += "[{}]".format(pin.instance.key)
        if getattr(pin.model, "vpr_equivalent_pins", False):
            with self.xml.element("pin_class", {"type": pin.model.direction.case("INPUT", "OUTPUT")}):
                for i in range(len(pin)):
                    self.xml.element_leaf("pin", {"ptc": iopin_ptc},
                            '{}.{}[{}]'.format(subtile_name, pin.model.name, i))
                    iopin_ptc += 1
                srcsink_ptc += 1
        else:
            for i in range(len(pin)):
                with self.xml.element("pin_class", {"type": pin.model.direction.case("INPUT", "OUTPUT")}):
                    self.xml.element_leaf("pin", {"ptc": iopin_ptc},
                            '{}.{}[{}]'.format(subtile_name, pin.model.name, i))
                iopin_ptc += 1
                srcsink_ptc += 1
        return srcsink_ptc, iopin_ptc

    def _tile(self, tile):
        tilepin2ptc = self.tilepin2ptc.setdefault( tile.key, [] )
        with self.xml.element("block_type", {
            "name": tile.name, "width": tile.width, "height": tile.height, "id": self.tile2id[tile.key]}):
            srcsink_ptc, iopin_ptc = 0, 0
            for subtile, i in tile.instances.items():
                if not isinstance(subtile, int):
                    continue
                tilepin2ptc.append( {} )
                for pin in i.pins.values():
                    if pin.model.direction.is_input and not pin.model.is_clock:
                        equivalent = getattr(pin.model, "vpr_equivalent_pins", False)
                        tilepin2ptc[subtile][pin.model.key] = srcsink_ptc, equivalent, iopin_ptc
                        srcsink_ptc, iopin_ptc = self._tile_pinlist(pin, srcsink_ptc, iopin_ptc)
                for pin in i.pins.values():
                    if pin.model.direction.is_output:
                        tilepin2ptc[subtile][pin.model.key] = srcsink_ptc, False, iopin_ptc
                        srcsink_ptc, iopin_ptc = self._tile_pinlist(pin, srcsink_ptc, iopin_ptc)
                for pin in i.pins.values():
                    if pin.model.is_clock:
                        tilepin2ptc[subtile][pin.model.key] = srcsink_ptc, False, iopin_ptc
                        srcsink_ptc, iopin_ptc = self._tile_pinlist(pin, srcsink_ptc, iopin_ptc)

    def _grid(self, array):
        for x, y in product(range(array.width), range(array.height)):
            if (instance := ArrayBuilder.get_hierarchical_root(array, Position(x, y))) is None:
                self.xml.element_leaf("grid_loc", {
                    "block_type_id": 0, "x": x, "y": y, "width_offset": 0, "height_offset": 0})
            else:
                rootpos = ArrayBuilder.hierarchical_position(instance)
                if rootpos == (x, y) and instance.model.disallow_segments_passthru:
                    for xx, yy in product(range(instance.model.width), range(instance.model.height - 1)):
                        self.chanx[x + xx][y + yy] = False
                    for xx, yy in product(range(instance.model.width - 1), range(instance.model.height)):
                        self.chany[x + xx][y + yy] = False
                self.xml.element_leaf("grid_loc", {
                    "block_type_id": self.tile2id[instance.model.key], "x": x, "y": y,
                    "width_offset": x - rootpos.x, "height_offset": y - rootpos.y})

    def _node(self, type_, id_, ptc, xlow, ylow, *,
            track_dir = None, port_ori = None, xhigh = None, yhigh = None, segment = None, capacity = 1):
        node_attr = {"capacity": capacity, "id": id_, "type": type_}
        loc_attr = {"xlow": xlow, "ylow": ylow, "ptc": ptc,
                "xhigh": uno(xhigh, xlow), "yhigh": uno(yhigh, ylow)}
        timing_attr = {"C": 0., "R": 0.}
        if type_ in ("CHANX", "CHANY"):
            assert track_dir is not None and segment is not None
            node_attr["direction"] = track_dir.case("INC_DIR", "DEC_DIR")
        elif type_ in ("IPIN", "OPIN"):
            assert port_ori is not None
            loc_attr["side"] = port_ori.case("TOP", "RIGHT", "BOTTOM", "LEFT")
        with self.xml.element("node", node_attr):
            self.xml.element_leaf("loc", loc_attr)
            self.xml.element_leaf("timing", timing_attr)
            if type_ in ("CHANX", "CHANY"):
                self.xml.element_leaf("segment", {"segment_id": self.sgmt2id[segment.name]})

        self.num_nodes += 1
        if self.num_nodes % 1000 == 0:
            _logger.info("   .. {:0>6d}K nodes generated".format(self.num_nodes // 1000))

    def _edge(self, src_id, sink_id, head_pin_bit = None, tail_pin_bit = None,
            delay = 0.0, fasm_features = tuple(), switch_id = None):
        if switch_id is None:
            # FIXME:
            # switch = self.timing.vpr_interblock_routing_switch(head_pin_bit, tail_pin_bit, delay)
            # switch_id = self.switch2id[switch.name]
            switch_id = 1
        attrs = {"src_node": src_id,
                "sink_node": sink_id,
                "switch_id": switch_id,
                }
        if fasm_features:
            with self.xml.element("edge", attrs), self.xml.element("metadata"):
                self.xml.element_leaf("meta", {"name": "fasm_features"}, " ".join(fasm_features))
        else:
            self.xml.element_leaf("edge", attrs)

        self.num_edges += 1
        if self.num_edges % 1000 == 0:
            _logger.info("   .. {:0>6d}K edges generated".format(self.num_edges // 1000))

    def _edge_box_output(self, head_pin_bit, tail_pin_bit, tail_pkg, fasm_features = tuple(), delay = 0.0):
        sink, index, hierarchy = ModuleUtils._analyze_sink(head_pin_bit)
        if index is not None:
            sink = sink[index]
        for src in NetUtils.get_multisource(sink):
            this_fasm = fasm_features + self.fasm.fasm_features_for_interblock_switch(src, sink, hierarchy)
            # FIXME: timing
            # this_delay = delay + self.timing.vpr_delay_of_routing_switch(src_port_bit, sink_port_bit)
            self._edge_box_input(ModuleUtils._attach_hierarchy(src, hierarchy), tail_pin_bit, tail_pkg,
                    this_fasm, delay)

    def _edge_box_input(self, head_pin_bit, tail_pin_bit, tail_pkg, fasm_features = tuple(), delay = 0.0):
        head_idx, head_node, parent = None, None, None

        if head_pin_bit.net_type in (NetType.slice_, NetType.bit):
            head_idx, head_node = NetUtils._reference(head_pin_bit)
            if isinstance(head_idx, slice):
                head_idx = head_idx.start
            parent = head_pin_bit.bus.parent
        else:
            head_idx, head_node = 0, NetUtils._reference(head_pin_bit)
            parent = head_pin_bit.parent

        try:
            predit = self.conn_graph.predecessors(head_node)
            pred_node = next(predit)
        except (nx.NetworkXError, StopIteration):
            return

        head_pin_bus = NetUtils._dereference(parent, pred_node)
        head_pin_bit = head_pin_bus[head_idx]

        pred_data = self.conn_graph.nodes[pred_node]
        if (id_ := pred_data.get("id")) is None:
            self._edge_box_output(head_pin_bit, tail_pin_bit, tail_pkg, fasm_features, delay)
            return

        if tail_pkg[0] in ("CHANX", "CHANY"):                     # ??? -> track
            tail_id, tail_lower, tail_higher, tail_ori = tail_pkg[1:]
            tail_start = tail_ori.direction.case(tail_lower, tail_higher)
            if pred_data["type"] in ("CHANX", "CHANY"):             # track -> track
                head_ori, head_lower, head_higher, _ = self._analyze_track(pred_node)
                if head_ori is tail_ori:                            # straight connection
                    dim, dir_ = tail_ori.decompose()
                    if (head_lower[dim.perpendicular] == tail_start[dim.perpendicular] and
                            head_lower[dim] <= tail_start[dim] + dir_.case(-1, 1) <= head_higher[dim]):
                        self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                        return
                elif head_ori is not tail_ori.opposite:             # not a U-turn
                    from_dim, from_dir = head_ori.decompose()
                    to_dim, to_dir = tail_ori.decompose()
                    if (head_lower[to_dim] + to_dir.case(1, 0) == tail_start[to_dim] and
                            head_lower[from_dim] <= tail_start[from_dim] + from_dir.case(0, 1) <= head_higher[from_dim]):
                        self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                        return
            else:                                                   # block pin -> track
                head_chan, head_ori, _ = self._analyze_blockpin(head_pin_bus)
                dim = head_ori.dimension.perpendicular
                if dim is tail_ori.dimension and head_chan == tail_start:
                    self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                    return
        else:                                                       # ??? -> block pin
            tail_id, tail_chan, dim = tail_pkg[1:]
            if pred_data["type"] in ("CHANX", "CHANY"):             # track -> block pin
                head_ori, head_lower, head_higher, _ = self._analyze_track(pred_node)
                if (dim is head_ori.dimension and head_lower[dim] <= tail_chan[dim] <= head_higher[dim]
                        and tail_chan[dim.perpendicular] == head_lower[dim.perpendicular]):
                    self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                    return
            else:                                                   # block pin -> block pin
                self._edge(id_ + head_idx, tail_id, head_pin_bit, tail_pin_bit, delay, fasm_features)
                return
        _logger.debug("Physical connection {} -> {} ignored due to reachability".format(head_pin_bit, tail_pin_bit))

    def run(self, context):
        # runtime-generated data
        self.tile2id = {}
        self.tilepin2ptc = {}
        # self.blockpin2ptc = {}
        self.switch2id = {}
        self.sgmt2id = {}
        self.sgmt2ptc = {}
        self.chanx = [[(0 < x < context.top.width - 1 and 0 <= y < context.top.height - 1)
            for y in range(context.top.height)] for x in range(context.top.width)]
        self.chany = [[(0 <= x < context.top.width - 1 and 0 < y < context.top.height - 1)
            for y in range(context.top.height)] for x in range(context.top.width)]
        channel_width = context.summary.vpr["channel_width"] = 2 * sum(sgmt.width * sgmt.length
                for sgmt in context.segments.values())
        # update VPR summary
        if isinstance(self.output_file, str):
            f = self.output_file
            os.makedirs(os.path.dirname(f), exist_ok = True)
            context.summary.vpr["rrg"] = f
            if f.endswith(".gz"):
                self.output_file = gzip.open(f, "wb")
            else:
                self.output_file = open(f, "wb")
        else:
            f = self.output_file.name
            os.makedirs(os.path.dirname(f), exist_ok = True)
            context.summary.vpr["rrg"] = f
            if f.endswith(".gz"):
                self.output_file = gzip.open(self.output_file, "wb")
        # FASM 
        if self.fasm is None:
            self.fasm = context.fasm_delegate
        self.fasm.reset()
        # timing
        # if self.timing is None:
        #     self.timing = TimingDelegate()  # fake timing
        # self.timing.reset()
        # routing resource graph generation
        with XMLGenerator(self.output_file, True) as xml, xml.element("rr_graph"):
            self.xml = xml
            _logger.info(" .. Start RRG meta-data generation")
            t = time.time()
            # channels:
            with xml.element("channels"):
                xml.element_leaf("channel", {
                    'chan_width_max':   channel_width,
                    'x_min':            channel_width,
                    'y_min':            channel_width,
                    'x_max':            channel_width,
                    'y_max':            channel_width,
                    })
                for y in range(context.top.height - 1):
                    xml.element_leaf('x_list', {'index': y, 'info': channel_width})
                for x in range(context.top.width - 1):
                    xml.element_leaf('y_list', {'index': x, 'info': channel_width})
            # switches
            with xml.element('switches'):
                with xml.element('switch', {'id': 0, 'type': 'mux', 'name': '__vpr_delayless_switch__', }):
                    xml.element_leaf('timing', {'R': 0., 'Cin': 0., 'Cout': 0., 'Tdel': 0., })
                    xml.element_leaf('sizing', {'mux_trans_size': 0., 'buf_size': 0., })
                # FIXME: fake switches
                with xml.element('switch', {'id': 1, 'type': 'mux', 'name': 'default', }):
                    xml.element_leaf('timing', {'R': 0., 'Cin': 0., 'Cout': 0., 'Tdel': 1e-10, })
                    xml.element_leaf('sizing', {'mux_trans_size': 0., 'buf_size': 0., })
                # for switch in self.timing.vpr_switches:
                #     id_ = self.switch2id[switch.name] = len(self.switch2id) + 1
                #     with xml.element('switch', {'id': id_, 'type': 'mux', 'name': switch.name, }):
                #         xml.element_leaf('timing',
                #                 {'R': switch.R, 'Cin': switch.Cin, 'Cout': switch.Cout, 'Tdel': switch.Tdel, })
                #         xml.element_leaf('sizing',
                #                 {'mux_trans_size': switch.mux_trans_size, 'buf_size': switch.buf_size, })
            # segments
            with xml.element('segments'):
                ptc = 0
                for i, (name, sgmt) in enumerate(context.segments.items()):
                    self.sgmt2id[name] = i
                    self.sgmt2ptc[name] = ptc
                    ptc += 2 * sgmt.width * sgmt.length
                    with self.xml.element("segment", {"name": name, "id": i}):
                        # FIXME: fake segment
                        self.xml.element_leaf("timing", {"R_per_meter": "0.0", "C_per_meter": "0.0"})
                        # sgmt = self.timing.vpr_segment(sgmt)
                        # self.xml.element_leaf("timing", {"R_per_meter": sgmt.Rmetal, "C_per_meter": sgmt.Cmetal})
            # block types
            with xml.element('block_types'):
                xml.element_leaf("block_type", {"id": 0, "name": "EMPTY", "width": 1, "height": 1})
                for tile_key in context.summary.active_tiles:
                    self.tile2id[tile_key] = len(self.tile2id) + 1
                    self._tile(context.database[ModuleView.abstract, tile_key])
            _logger.info(" .. Completed RRG meta-data generation")
            t = time.time() - t
            _logger.info("   .. RRG meta-data generation took %f seconds", t)
            # flatten grid and create coalesced connection graph
            with xml.element("grid"):
                self._grid(context.top)
                self._construct_conn_graph(context.top)
            # nodes
            with xml.element("rr_nodes"):
                _logger.info(" .. Start RRG node generation")
                t = time.time()
                self.num_nodes = 0
                for node, data in self.conn_graph.nodes(data = True):
                    if "id" not in data:
                        continue
                    elif data["type"] in ("CHANX", "CHANY"):    # track
                        ori, lower, higher, ptc_pos = self._analyze_track(node)
                        segment = node[0].prototype
                        ptc = self.sgmt2ptc[segment.name] + ori.direction.case(0, 1)
                        for i in range(segment.width):
                            self._node(data["type"],
                                    data["id"] + i, 
                                    ptc + 2 * (ptc_pos % segment.length) * segment.width + i * 2,
                                    lower.x,
                                    lower.y,
                                    track_dir = ori.direction,
                                    xhigh = higher.x,
                                    yhigh = higher.y,
                                    # segment = self.timing.vpr_segment(segment),
                                    segment = segment,
                                    )
                    else:                                       # block pin
                        pin = data["net"]
                        _, ori, pos = self._analyze_blockpin(pin)
                        blkinst = pin.instance.hierarchy[0]
                        tilepin2ptc = self.tilepin2ptc[blkinst.parent.key]
                        srcsink_ptc, equivalent, iopin_ptc = tilepin2ptc[blkinst.key][pin.model.key]
                        # SOURCE/SINK node
                        if equivalent:
                            self._node(pin.model.direction.case("SINK", "SOURCE"),
                                    data["srcsink_id"],
                                    srcsink_ptc,
                                    pos.x,
                                    pos.y,
                                    capacity = len(pin),
                                    xhigh = pos.x + blkinst.model.width - 1,
                                    yhigh = pos.y + blkinst.model.height - 1)
                        else:
                            for i in range(len(pin)):
                                self._node(pin.model.direction.case("SINK", "SOURCE"),
                                        data["srcsink_id"] + i,
                                        srcsink_ptc + i,
                                        pos.x,
                                        pos.y,
                                        capacity = 1,
                                        xhigh = pos.x + blkinst.model.width - 1,
                                        yhigh = pos.y + blkinst.model.height - 1)
                        # IPIN/OPIN node
                        for i in range(len(pin)):
                            self._node(pin.model.direction.case("IPIN", "OPIN"),
                                    data["id"] + i,
                                    iopin_ptc + i,
                                    pos.x + pin.model.position.x,
                                    pos.y + pin.model.position.y,
                                    port_ori = ori)
                _logger.info(" .. Completed RRG node generation")
                t = time.time() - t
                _logger.info("   .. RRG node generation took %f seconds", t)
                _logger.info("   .. {:0>8.1f}K nodes generated".format(self.num_nodes / 1000))
            # edges
            with xml.element("rr_edges"):
                _logger.info(" .. Start RRG edge generation")
                t = time.time()
                self.num_edges = 0
                for sink_node, sink_data in self.conn_graph.nodes(data = True):
                    if (type_ := sink_data.get("type")) is None:
                        continue
                    elif type_ in ("CHANX", "CHANY"):
                        # 1. get the pin
                        sink_pin = sink_data["net"]
                        # 2. prepare the tail package
                        ori, lower, higher, _ = self._analyze_track(sink_node)
                        # 3. emit edges
                        for i, sink_pin_bit in enumerate(sink_pin):
                            self._edge_box_output(sink_pin_bit, sink_pin_bit,
                                    # tail_type, tail_id,             lower_pos, higher_pos, orientation
                                    (type_,      sink_data["id"] + i, lower,     higher,     ori))
                    elif type_ == "IPIN":
                        # 1. get the pin
                        sink_pin = NetUtils._dereference(context.top, sink_node)
                        # 2. prepare the tail package
                        chan, ori, _ = self._analyze_blockpin(sink_pin)
                        iopin_id = sink_data["id"]
                        srcsink_id = sink_data["srcsink_id"]
                        equivalent = sink_data.get("equivalent", False)
                        # 3. emit edges
                        for i, sink_pin_bit in enumerate(sink_pin):
                            # 3.1 IPIN -> SINK
                            self._edge(iopin_id + i, srcsink_id + (0 if equivalent else i), switch_id = 0)
                            # 3.2 ??? -> IPIN
                            self._edge_box_input(sink_pin_bit, sink_pin_bit,
                                    # tail_type, tail_id,      chan_pos, dimension
                                    (type_,      iopin_id + i, chan,     ori.dimension.perpendicular))
                    elif type_ == "OPIN":
                        # 1. get the pin
                        sink_pin = NetUtils._dereference(context.top, sink_node)
                        # 2. emit SOURCE -> OPIN edges
                        iopin_id = sink_data["id"]
                        srcsink_id = sink_data["srcsink_id"]
                        equivalent = sink_data.get("equivalent", False)
                        for i in range(len(sink_pin)):
                            self._edge(srcsink_id + (0 if equivalent else i), iopin_id + i, switch_id = 0)
                _logger.info(" .. Completed RRG edge generation")
                t = time.time() - t
                _logger.info("   .. RRG edge generation took %f seconds", t)
                _logger.info("   .. {:0>8.1f}K edges generated".format(self.num_edges / 1000))
            del self.xml
