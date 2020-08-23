# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.builder.array.array import ArrayBuilder,_ArrayInstancesMapping
from ..core.common import ModuleView,ModuleClass,PrimitiveClass,Position, SegmentID,BridgeID
from ..util import Object, uno
from ..exception import PRGAInternalError
from collections import OrderedDict
import os
from os import path
from prga.compatible import *
from itertools import chain
from prga.netlist.net.util import NetUtils
import networkx as nx
import numpy as np
import random

__all__ = ['Tester']

# ----------------------------------------------------------------------------
# -- Tester Pass ------------------------------------------------------
# ----------------------------------------------------------------------------
class Tester(Object, AbstractPass):
    """Collecting Unit Tests rendering data and tasks
    
    Args:
        src_output_dir (:obj:`str`): Verilog source files are generated in the specified directory by the VerilogCollection pass. 
        The directory name provided for both VerilogCollection pass and Tester pass must be the same. Default value is the current working directory.
        tests_output_dir (:obj:`str`): Multiple Unit Tests are generated in this directory. Each test has its own individual directory. 
        Default value is a "unit_tests"
        
    Keyword Args:
        header_output_dir (:obj:`str`): Verilog header files are generated in the specified directory. Default value
            is "{src_output_dir}/include"
    """

    __slots__ = ['renderer', 'src_output_dir', 'header_output_dir', 'visited']
    def __init__(self, src_output_dir = ".", tests_output_dir = "unit_tests",  header_output_dir = None):
        self.src_output_dir = os.path.abspath(src_output_dir) 
        self.tests_dir = os.path.abspath(tests_output_dir)
        self.header_output_dir = os.path.abspath(uno(header_output_dir, os.path.join(src_output_dir, "include")))
        self.visited = {}

    def get_instance_file(self,module):
        """
        Collecting Data for Makefile VERILOG_SOURCES argument
        
        Args:
            module (`AbstractModule`):
        
        Returns:
            :obj:List : a list of :obj:`str` which contain the path of source verilog files 

        """
        instance_files = [path.join(self.src_output_dir,module.name+".v")] #This list stores all the paths for the source files
        queue = []
        for temp in itervalues(module.instances):
            queue.append(temp.model)
        
        while len(queue)!=0: # This loop is iterative BFS 
            curr = queue.pop(0)
            curr_file = path.join(self.src_output_dir,curr.name+".v")
            if curr_file not in instance_files:
                instance_files.append(curr_file)
            for temp in itervalues(curr.instances):
                queue.append(temp.model)

        return instance_files
    
    def get_primitives(self,module):
        """
        Collecting Data regarding primitive modules and Switch module such as the hierarchy and cfg_bitoffset
        
        Args:
            module (`AbstractModule`):
        
        Returns:
            :obj:List : a list of :obj:`tuples` which contain instance, heirarchy and the offset 
        """
        
        queue = []
        primitives = [] 

        for instance in itervalues(module.instances):
            try:
                queue.append([instance,[str(instance.name)],instance.cfg_bitoffset])
            except:
                queue.append([instance,[str(instance.name)],0])
        
        while len(queue)!=0: # This loop is iterative BFS 
            parent, heirarchy,offset = queue.pop(0)

            if parent.model.module_class.is_primitive or parent.model.module_class == ModuleClass.switch:
                try:
                    primitives.append((parent,heirarchy,offset+parent.cfg_bitcount))
                except:
                    primitives.append((parent,heirarchy,offset))

            for instance in itervalues(parent.model.instances):
                try:
                    queue.append([instance,heirarchy+[str(instance.name)],offset+instance.cfg_bitoffset])
                except:
                    queue.append([instance,heirarchy+[str(instance.name)],offset])
          
        return primitives
  
    def get_input_ports(self,module):
        """
        Helper Function to get all the input ports of a Verilog Module.

        Args:
            module (`AbstractModule`):
        
        Returns:
            :obj:List : a list of `Port` objects representing the input ports of a module  
        """

        ports = [] 
        try:
            module = self.context.database[ModuleView.user,module.key]
            if module.module_class == ModuleClass.io_block:
                module = self.context.database[ModuleView.logical,module.key]

            for k,v in iteritems(module.ports):
                if v.direction.is_input and not v.is_clock:
                    ports.append(v)
                    # print(v)
            # print(module.ports)
        except:
            x = 0+0
        return ports
    
    def get_clocks(self,module):
        """
        Helper Function to get all the pins/ports driving the clocks inside a Verilog Module.
    
        Args:
            module (`AbstractModule`):
        
        Returns:
            :obj:List : a list of `Port` objects representing the input ports of a module which drive the clocks 
        """
        clocks = []
        if module.module_class == ModuleClass.io_block:
            module = self.context.database[ModuleView.logical,module.key]

        for x in iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input and ipin.model.is_clock):
            if module._allow_multisource:
                source = NetUtils.get_multisource(x)
                if source not in clocks:
                    clocks.append(source) 
            else:
                source = NetUtils.get_source(x)
                if source not in clocks:
                    clocks.append(source)
        
        return clocks

    def get_name(self,bus_index):
        """
        Helper function for generating variable names which will be used in templatings
      
        Args:
            module (`Bit`):
        
        Returns:
            :obj:str : Unique name for the Bit of a pin/port 
        """

        var_name = "" 
        if bus_index.bus.net_type == 1:
            var_name = bus_index.bus.name+ "_" + str(bus_index.index.start) + "_port"
        else:
            var_name = bus_index.bus.model.name+ "_" + str(bus_index.index.start) + "_"+bus_index.bus.instance.name

        return var_name

    def switch_connections(self,module):
        """
        Generate the connections along with their corresponding cfg_bits

        Args:
            module (`AbstractModule`):
        
        Returns:
            stack : List of lists where each sublist contains a set of connections 
            which have to be tested in a single test
            G : A networkx graph containing the connections between instance pins 
            and ports of the module
        """

        module = self.context.database[ModuleView.user,module.key]

        num_tests = 0
        for port in module.ports.values():
            if port.is_sink:
                for sink in port:
                    if module._allow_multisource:
                        num_tests = max(len(NetUtils.get_multisource(sink)),num_tests)
        
        stack = [[] for i in range(num_tests+1)]
        G = nx.DiGraph()
        for port in module.ports.values():
            if port.is_sink:
                for sink in port:
                    if module._allow_multisource:
                        for i,src in enumerate(NetUtils.get_multisource(sink)):
                            if src.net_type == 0:
                                continue
                            src_var_name = self.get_name(src) 
                            sink_var_name = self.get_name(sink) 
                            conn = NetUtils.get_connection(src,sink)
                            stack[i].append((src_var_name,src,sink_var_name,sink,conn.get("cfg_bits",tuple())))
                            G.add_edge(NetUtils._reference(src), NetUtils._reference(sink), cfg_bits =conn.get("cfg_bits",tuple()))
                    else:
                        src = NetUtils.get_source(sink)
                        if src.net_type == 0:
                            continue
                        src_var_name = self.get_name(src) 
                        sink_var_name = self.get_name(sink) 
                        conn = NetUtils.get_connection(src,sink)
                        stack[0].append((src_var_name,src,sink_var_name,sink,conn.get("cfg_bits",tuple())))
                        G.add_edge(NetUtils._reference(src), NetUtils._reference(sink), cfg_bits =conn.get("cfg_bits",tuple()))
        
        return stack,G

    def get_connections(self,module):
        """
        Generate the connections for modules like CLB, Subarray, iob, etc. (the ones not used for switch_connections function)

        Args:
            module (`AbstractModule`):
        
        Returns:
            connections : List of connections present between instance pins 
            and ports of the module
            G : A networkx graph containing the connections between instance pins 
            and ports of the module
        """
        connections = []
        G = nx.DiGraph()
        try:
            module = self.context.database[ModuleView.user,module.key]
            for sink_bus in chain(iter(oport for oport in itervalues(module.ports) if oport.direction.is_output),
                        iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input and not ipin.model.is_clock)):
                for sink_net in sink_bus:
                    if module._allow_multisource:
                        for src_net in NetUtils.get_multisource(sink_net):
                            if src_net.net_type == 0:
                                continue
                            src_var_name = self.get_name(src_net) 
                            sink_var_name = self.get_name(sink_net)
                            connections.append((src_var_name,src_net,sink_var_name,sink_net,tuple()))
                            G.add_edge(NetUtils._reference(src_net), NetUtils._reference(sink_net), cfg_bits = tuple())
        
                    else:
                        src_net = NetUtils.get_source(sink_net)
                        if src_net.net_type == 0:
                            continue

                        src_var_name = self.get_name(src_net) 
                        sink_var_name = self.get_name(sink_net) 
                        
                        connections.append((src_var_name,src_net,sink_var_name,sink_net,tuple()))
                        G.add_edge(NetUtils._reference(src_net), NetUtils._reference(sink_net), cfg_bits = tuple())
        except:
            x= 0
        return connections,G

    def _process_module(self, module):
        """
        Function for processing module for generating tests 

        Args:
            module (`AbstractModule`):
        """
        if module.key in self.visited:
            return
        
        f = os.path.join(self.tests_dir, "test_" + module.name)
        
        self.visited[module.key] = f

        if not hasattr(module, "test_dir"):
            setattr(module,"test_dir",f)
        
        print(module.name)

        if module.module_class == ModuleClass.switch_box or module.module_class == ModuleClass.connection_box or module.module_class.is_cluster:
            stack,nx_graph = self.switch_connections(module)
            setattr(module,"stack",stack)
            self.graphs[module.name] = {'graph':nx_graph,'module':module}
            
        else:
            connections,nx_graph = self.get_connections(module)
            setattr(module,"stack",[connections])
            self.graphs[module.name] = {'graph':nx_graph,'module':module}

        
        input_ports = self.get_input_ports(module)
        setattr(module,"input_ports",input_ports)
        
        clocks = self.get_clocks(module)
        setattr(module,"clocks",clocks)
       
        setattr(module,"verilog_file",path.join(self.src_output_dir,module.name+".v"))
        
        primitives = self.get_primitives(module)
        setattr(module,"primitives",primitives)
 
        instance_files  = self.get_instance_file(module)
        setattr(module,"files",' '.join(instance_files))
        setattr(module,"top_level",module.name)
        
        if module.module_class == ModuleClass.cluster:
            self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "cluster.tmpl.py")
        elif module.module_class == ModuleClass.switch:
            self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "switch.tmpl.py")
        elif not module.module_class.is_primitive:
            self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "module.tmpl.py")
        else:
            if module.primitive_class == PrimitiveClass.memory:
                self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "memory.tmpl.py")
            else:
                self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), getattr(module,"test_python_template","module.tmpl.py"))

        self.renderer.add_top_level_makefile(module, path.join(f,"Makefile"), "test_base.tmpl")
        self.renderer.add_top_level_python_test(module, path.join(f,"config.py"), "config.py")
        print()
        
        for instance in itervalues(module.instances):
            self._process_module(instance.model)

    def route_L(self,top,G):
        """
        An example route which takes the shape L along the FPGA Fabric 
        """
        # | | | | | | | |
        # | - - - - - - |
        # | | | | | | - |
        # | | | | | | - |
        # | | | | | | - |
        # | | | | | | - |
        # | | | | | | - |
        # | | | | | | | |
        # - represents the route on the FPGA fabric


        height = top.height
        width = top.width
        path = []
        
        # Horizontal Path
        for i in range(1,width-1):
            path.append((1,i))
 
        # Vertical Path
        for i in range(2,height-1):
            path.append((i,width-2))
        
        path.reverse()
            
        print(path)
        
        # Get Inter Tile Connections Eg- Connection between tile(1,1) and tile(1,2)
        connections = [[] for i in range(len(path))]
        for i in range(1,len(path)):
            sink = path[i-1]
            src = path[i]
            srcs = []
            sinks = []
            tile_src = top._instances[Position(src[0],src[1])]
            tile_sink = top._instances[Position(sink[0],sink[1])]
            
            for _,src_pin in iteritems(tile_src.pins):
                if src_pin.model.direction.is_output and not src_pin.model.is_clock and not 'cu' in src_pin.model.name:
                    for net in src_pin:
                        srcs.append(NetUtils._reference(net))
            
            for _,sink_pin in iteritems(tile_sink.pins):
                if sink_pin.model.direction.is_input and not sink_pin.model.is_clock and not 'cu' in sink_pin.model.name:
                    for net in sink_pin:
                        sinks.append(NetUtils._reference(net))

            for src_net in srcs:
                for sink_net in sinks:
                    if nx.has_path(G,src_net,sink_net):
                        connections[i-1].append((src_net,sink_net))

        # Get Intra Tile Connections of the start point i.e connections between inports and outports of a tile
        sink = path[len(path)-1]
        src = path[len(path)-1]
        srcs = []
        sinks = []
        tile_src = top._instances[Position(src[0],src[1])]
        tile_sink = top._instances[Position(sink[0],sink[1])]

        for _,src_pin in iteritems(tile_src.src_pins):
            if src_pin.model.direction.is_input and not src_pin.model.is_clock and not 'cu' in src_pin.model.name:
                for net in src_pin:
                    srcs.append(NetUtils._reference(net))

        for _,sink_pin in iteritems(tile_sink.sink_pins):
            if sink_pin.model.direction.is_output and not sink_pin.model.is_clock and not 'cu' in sink_pin.model.name:
                for net in sink_pin:
                    sinks.append(NetUtils._reference(net))
        
        for src_net in srcs:
            for sink_net in sinks:
                if nx.has_path(G,src_net,sink_net):
                    connections[len(path)-1].append((src_net,sink_net))
        
        # Return the individual connections which form the route 
        route = [] # Final Route
        for index in range(1,len(connections)):
            # print(index)
            connection_found = False
            for i in range(len(connections[index])):
                for j in range(len(connections[index-1])):
                    if nx.has_path(G,connections[index][i][1],connections[index-1][j][0]):
                        connection_found = True
                        route.append((NetUtils._dereference(top,connections[index-1][j][0]),NetUtils._dereference(top,connections[index-1][j][1])))
                        if index == (len(connections)-1): 
                            route.append((NetUtils._dereference(top,connections[index][i][0]),NetUtils._dereference(top,connections[index][i][1])))
                        else:
                            route.append((NetUtils._dereference(top,connections[index][i][1]),NetUtils._dereference(top,connections[index-1][j][0])))
                        
                    if connection_found:
                        break
                if connection_found:
                    break
            if not connection_found:
                print("PATH DOESNT EXIST BETWEEN path index ",index,"and path index",index-1)

        route_vars = [] # Extra data to be used for templating
        cfg_bits_route = [] # All the cfg_bits which need to set up for the route
        for i in range(len(route)):
            path = nx.shortest_path(G,NetUtils._reference(route[i][0]),NetUtils._reference(route[i][1]))
            src = route[i][0]
            sink = route[i][1]
            src_var_name = self.get_name(src)
            sink_var_name = self.get_name(sink)
            route_vars.append((src_var_name,src,sink_var_name,sink))
            
            for i in range(1,len(path)):
                cfg_bits = G[path[i-1]][path[i]]['cfg_bits'] 
                if len(cfg_bits) !=0 :
                    hierarchy = [inst.name for inst in reversed(NetUtils._dereference(top,path[i-1]).bus.instance._hierarchy)]
                    model = NetUtils._dereference(top,path[i-1]).bus.instance._hierarchy[0].model
                    model_logical = self.context.database[1,model.key]
                    cfg_bits_route.append((model_logical,hierarchy,cfg_bits))
           
        for x in route_vars:
            print(x)
        print()
        
        top_logical = self.context.database[ModuleView.logical,top.key]

        start_point = route_vars[len(route_vars)-1][1]

        # route_vars.pop(len(route_vars)-1)
        
        setattr(top_logical,"route",route_vars)
        setattr(top_logical,"cfg_bits_route",cfg_bits_route)
        setattr(top_logical,"start_point",start_point.bus)
    
    def helper(self,pins,G):
        """
        Helper Function for Adding Heirarchial Instance
        This function adds the connections between instances pins and ports of module present at Position(i,j)
        """
        for key,pin,instance in pins:
            for index in range(len(pin)):
                hier_pin_bit = instance.pins[key][index]
                hier_src_bit = None # the one we want
                # 1.
                hierarchy, leaf_sink = None, None
                if hier_pin_bit.bus.model.is_source:
                    hierarchy = instance.shrink_hierarchy(slice(1, None))
                    leaf_sink = instance.hierarchy[0].pins[key][index]
                else:
                    hierarchy = instance
                    leaf_sink = instance.model.ports[key][index]
                #2.
                leaf_src = None
                if hierarchy and hierarchy.model._allow_multisource:
                    leaf_src = NetUtils.get_multisource(leaf_sink)
                else:
                    leaf_src = NetUtils.get_source(leaf_sink)
                #3.
                for sources in leaf_src:
                    if hierarchy is None:
                        hier_src_bit = sources
                    else:
                        leaf_src_bus, leaf_src_index = sources, 0
                        if sources.bus_type.is_slice:
                            leaf_src_index = sources.index
                            leaf_src_bus = sources.bus
                            if leaf_src_bus.net_type.is_port:
                                hier_src_bit = hierarchy.pins[leaf_src_bus.key][leaf_src_index]
                            else: # is_pin
                                hier_src_bit = hierarchy.extend_hierarchy(below = leaf_src_bus.instance).pins[leaf_src_bus.model.key][leaf_src_index]
                        if hier_src_bit is None:
                            continue
                        if hierarchy.model._allow_multisource:
                            conn = NetUtils.get_connection(sources,leaf_sink)
                            G.add_edge(NetUtils._reference(hier_src_bit), NetUtils._reference(hier_pin_bit), cfg_bits =conn.get("cfg_bits",tuple()))
                        else:
                            G.add_edge(NetUtils._reference(hier_src_bit), NetUtils._reference(hier_pin_bit), cfg_bits = tuple())
        
        return G

    def add_hierarchial_instances_connections(self,top,G):
        """
        Recursively add all the connections in the submodules of the top module.
        All the connections are heirarchial
        """
        top_user = self.context._database[ModuleView.user,top.key] #User view of the top module
        
        height = top_user.height # Height of the FPGA Fabric
        width = top_user.width # Width of the FPGA Fabric
        
        for i in range(height):
            for j in range(width):
                
                # Store all the instances present in a tile
                tile_ij = [ArrayBuilder.get_hierarchical_root(top_user, Position(int(i),int(j)),corner = 0),ArrayBuilder.get_hierarchical_root(top_user, Position(i,j),corner = 2),
                        ArrayBuilder.get_hierarchical_root(top_user, Position(i,j),corner = 1),ArrayBuilder.get_hierarchical_root(top_user, Position(i,j),corner = 3),
                        ArrayBuilder.get_hierarchical_root(top_user, Position(i,j))]
                
                while None in tile_ij:
                    tile_ij.remove(None)
                
                try:
                    tile_ij.append(top._instances[Position(i,j)])
                    """
                    Generate the connections between outports and their source and 
                    the connections between input pins of instances and their source of tile_module
                    """
                    sinks = []
                    for key,pin in top._instances[Position(i,j)].pins.items():
                        if pin.bus.model.is_sink and not pin.bus.model.is_clock:
                            sinks.append((key,pin,top._instances[Position(i,j)]))
                    
                    G = self.helper(sinks,G)
                    sinks = []
                    for temp in itervalues(top._instances[Position(i,j)].model._instances):
                        for k,v in temp.pins.items():
                            if v.bus.model.is_source and not v.bus.model.is_clock:
                                sinks.append((k,v,top._instances[Position(i,j)].extend_hierarchy(below= temp)))
                    
                    G = self.helper(sinks,G)                    
                except:
                    x = 0

                queue = tile_ij
                visited = []
                while len(queue):
                    hierarchical_instance  = queue.pop(0)
                    if hierarchical_instance is None  or not hierarchical_instance.is_hierarchical:
                        continue
                    
                    hier_inst_key = tuple(i.key for i in hierarchical_instance.hierarchy)
                    if hier_inst_key in visited:
                        continue

                    visited.append(hier_inst_key)

                    for key,pin in hierarchical_instance.pins.items():
                        for index in range(len(pin)):
                            hier_pin_bit = hierarchical_instance.pins[key][index]
                            hier_src_bit = None # the one we want
                            # 1.
                            hierarchy, leaf_sink = None, None
                            if hier_pin_bit.bus.model.is_source:
                                hierarchy = hierarchical_instance.shrink_hierarchy(slice(1, None))
                                leaf_sink = hierarchical_instance.hierarchy[0].pins[key][index]
                            else:
                                hierarchy = hierarchical_instance
                                leaf_sink = hierarchical_instance.model.ports[key][index]
                            # 2.
                            leaf_src = None
                            if hierarchy.model._allow_multisource:
                                leaf_src = NetUtils.get_multisource(leaf_sink)
                            else:
                                leaf_src = NetUtils.get_source(leaf_sink)
                            # 3.
                            for sources in leaf_src:
                                if hierarchy is None:
                                    hier_src_bit = sources
                                else:
                                    leaf_src_bus, leaf_src_index = sources, 0
                                    if sources.bus_type.is_slice:
                                        leaf_src_index = sources.index
                                        leaf_src_bus = sources.bus
                                    if leaf_src_bus.net_type.is_port:
                                        hier_src_bit = hierarchy.pins[leaf_src_bus.key][leaf_src_index]
                                    else: # is_pin
                                        hier_src_bit = hierarchy.extend_hierarchy(below = leaf_src_bus.instance).pins[leaf_src_bus.model.key][leaf_src_index]
                                if hierarchy.model._allow_multisource:
                                    conn = NetUtils.get_connection(sources,leaf_sink)
                                    # print(hier_src_bit,hier_pin_bit)
                                    # print(NetUtils._reference(hier_src_bit), NetUtils._reference(hier_pin_bit))
                                    G.add_edge(NetUtils._reference(hier_src_bit), NetUtils._reference(hier_pin_bit), cfg_bits =conn.get("cfg_bits",tuple()))
                                else:
                                    # print(hier_src_bit,hier_pin_bit)
                                    # print(NetUtils._reference(hier_src_bit), NetUtils._reference(hier_pin_bit))
                                    G.add_edge(NetUtils._reference(hier_src_bit), NetUtils._reference(hier_pin_bit), cfg_bits = tuple())
                            
                            if hierarchy.is_hierarchical:
                                for _,sub_instance in iteritems(hierarchy.model.instances):
                                    leaf = hierarchy.extend_hierarchy(below = sub_instance)
                                    hier_inst_key = tuple(i.key for i in leaf.hierarchy) #hash
                                    if hier_inst_key not in visited:
                                        queue.append(leaf)

        self.graphs['top']['graph'] = G

    @property
    def key(self):
        return "test.cocotb"
 
    @property
    def dependences(self):
        return ("translation", "rtl.verilog")

    @property
    def is_readonly_pass(self):
        return True
    
    def run(self, context, renderer=None):
        top = context.system_top
        self.renderer = renderer
        self.context = context
        self.graphs = {}
        if top is None:
            raise PRGAInternalError("System top module is not set")
        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        self.visited = context.summary.rtl["sources"] = {}
        context.summary.rtl["includes"] = [self.header_output_dir]
        self._process_module(top)

        G = self.graphs['top']['graph']
        
        top_user = self.context._database[ModuleView.user,top.key]
        self.add_hierarchial_instances_connections(top,G)

        G = self.graphs['top']['graph']

        self.route_L(top_user,G)

        f = os.path.join(self.tests_dir,"test_route_1")
        self.renderer.add_top_level_python_test(top, os.path.join(f,"test.py"), "route.tmpl.py")
        self.renderer.add_top_level_makefile(top, os.path.join(f,"Makefile"), "test_base.tmpl")
        self.renderer.add_top_level_python_test(top, os.path.join(f,"config.py"), "config.py")