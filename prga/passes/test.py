# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.builder.array.array import ArrayBuilder
from ..core.common import ModuleView,ModuleClass,PrimitiveClass,Position
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
import pdb
__all__ = ['Tester']

# ----------------------------------------------------------------------------
# -- Tester Pass ------------------------------------------------------
# ----------------------------------------------------------------------------
class Tester(Object, AbstractPass):
    """Collecting Verilog rendering tasks.
    
    Args:
        renderer (`FileRenderer`): File generation tasks are added to the specified renderer
        src_output_dir (:obj:`str`): Verilog source files are generated in the specified directory. Default value is
            the current working directory.
        header_output_dir (:obj:`str`): Verilog header files are generated in the specified directory. Default value
            is "{src_output_dir}/include"
        view (`ModuleView`): Generate Verilog source files with the specified view. Currently No use in tester pass
    """

    __slots__ = ['renderer', 'src_output_dir', 'header_output_dir', 'view', 'visited']
    def __init__(self, rtl_dir, tests_dir, src_output_dir = ".", header_output_dir = None, view = ModuleView.logical):
        self.src_output_dir = src_output_dir
        self.tests_dir = os.path.abspath(tests_dir)
        self.rtl_dir = os.path.abspath(rtl_dir)
        self.header_output_dir = os.path.abspath(uno(header_output_dir, os.path.join(src_output_dir, "include")))
        self.view = view
        self.visited = {}
        if not path.exists(self.tests_dir):
            os.mkdir(self.tests_dir)

    def get_instance_file(self,module):

        instance_files = [path.join(self.rtl_dir,module.name+".v")]
        # if os.path.join(self.tests_dir,"test_"+module.name):
        #     makedirs(os.path.join(self.tests_dir,"test_"+module.name))

        # os.system('cp '+os.path.join(self.rtl_dir,module.name+".v")+' '+os.path.join(self.tests_dir,"test_"+module.name))
        queue = []
        # module = self.context.database[ModuleView.user,module.key]
        for temp in itervalues(module.instances):
            queue.append(temp.model)
        
        while len(queue)!=0:
            curr = queue.pop(0)
            curr_file = path.join(self.rtl_dir,curr.name+".v")
            if curr_file not in instance_files:
                instance_files.append(curr_file)
                # os.system('cp '+os.path.join(self.rtl_dir,curr.name+".v")+' '+os.path.join(self.tests_dir,"test_"+module.name))
            for temp in itervalues(curr.instances):
                queue.append(temp.model)

        return instance_files
    
    def get_primitives(self,module):
        queue = []
        primitives = []

        for instance in itervalues(module.instances):
            try:
                queue.append([instance,[str(instance.name)],instance.cfg_bitoffset])
            except:
                queue.append([instance,[str(instance.name)],0])
        
        while len(queue)!=0:
            parent, heirarchy,offset = queue.pop(0)

            if parent.model.module_class.is_primitive or parent.model.module_class == 9:
                try:
                    primitives.append([parent,heirarchy,offset+parent.cfg_bitcount])
                except:
                    primitives.append([parent,heirarchy,offset])

            for instance in itervalues(parent.model.instances):
                try:
                    queue.append([instance,heirarchy+[str(instance.name)],offset+instance.cfg_bitoffset])
                except:
                    queue.append([instance,heirarchy+[str(instance.name)],offset])
          
        return primitives
  
    def get_input_ports(self,module):
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
        var_name = "" 
        if bus_index.bus.net_type == 1:
            var_name = bus_index.bus.name+ "_" + str(bus_index.index.start) + "_port"
        else:
            var_name = bus_index.bus.model.name+ "_" + str(bus_index.index.start) + "_"+bus_index.bus.instance.name

        return var_name

    def switch_connections(self,module):
        # For modules using switches like cluster and switchbox
            module_temp = self.context.database[0,module.key]
            num_tests = 0
            for port in module_temp.ports.values():
                if port.is_sink:
                    for sink in port:
                        if module_temp._allow_multisource:
                            num_tests = max(len(NetUtils.get_multisource(sink)),num_tests)
                        else:
                            num_tests = max(len(NetUtils.get_source(sink)),num_tests)
            stack = [[] for i in range(num_tests+1)]
            G = nx.DiGraph()
            # print(module.view)
            # print(stack)
            if module_temp._allow_multisource:
                for port in module_temp.ports.values():
                    if port.is_sink:
                        for sink in port:
                            for i,src in enumerate(NetUtils.get_multisource(sink)):
                                if src.net_type == 0:
                                    continue
                                src_var_name = self.get_name(src) 
                                sink_var_name = self.get_name(sink) 
                                conn = NetUtils.get_connection(src,sink)
                                stack[i].append((src_var_name,src,sink_var_name,sink,conn.get("cfg_bits",tuple())))
                                G.add_edge(NetUtils._reference(src), NetUtils._reference(sink), cfg_bits =conn.get("cfg_bits",tuple()))
                            #     print("Conn: ",src," -> ",sink," : ",conn.get("cfg_bits",tuple()))
                            # print()
            else:
                for port in module_temp.ports.values():
                    if port.is_sink:
                        for sink in port:
                            for i,src in enumerate(NetUtils.get_source(sink)):
                                if src.net_type == 0:
                                    continue
                                
                                src_var_name = self.get_name(src) 
                                sink_var_name = self.get_name(sink) 

                                conn = NetUtils.get_connection(src,sink)
                                stack[i].append((src_var_name,src,sink_var_name,sink,conn.get("cfg_bits",tuple())))
                                G.add_edge(NetUtils._reference(src), NetUtils._reference(sink), cfg_bits =conn.get("cfg_bits",tuple()))
                            #     print("Conn: ",src," -> ",sink," : ",conn.get("cfg_bits",tuple()))
                            # print()
            
            while [] in stack:
                stack.remove([])
            # for conn in stack:
            #     for src_var,src,sink_var,sink,cfg_bits in conn:
            #         print("Conn: ",src," -> ",sink," : ",cfg_bits)
            #     print()
            
            return stack,G

    def get_connections(self,module):
        connections = []
        G = nx.DiGraph()
        try:
            module = self.context.database[ModuleView.user,module.key]
            if module._allow_multisource:
                for sink_bus in chain(iter(oport for oport in itervalues(module.ports) if oport.direction.is_output),
                            iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input and not ipin.model.is_clock)):
                    for sink_net in sink_bus:
                            for src_net in NetUtils.get_multisource(sink_net):
                                if src_net.net_type == 0:
                                    continue
                                src_var_name = self.get_name(src_net) 
                                sink_var_name = self.get_name(sink_net)

                                connections.append((src_var_name,src_net,sink_var_name,sink_net,tuple()))
                                G.add_edge(NetUtils._reference(src_net), NetUtils._reference(sink_net), cfg_bits = tuple())
            
            else:
                for sink_bus in chain(iter(oport for oport in itervalues(module.ports) if oport.direction.is_output),
                            iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input and not ipin.model.is_clock)):
                    for sink_net in sink_bus:
                            for src_net in NetUtils.get_source(sink_net):
                                if src_net.net_type == 0:
                                    continue

                                src_var_name = self.get_name(src_net) 
                                sink_var_name = self.get_name(sink_net) 
                                
                                connections.append((src_var_name,src_net,sink_var_name,sink_net,tuple()))
                                G.add_edge(NetUtils._reference(src_net), NetUtils._reference(sink_net), cfg_bits = tuple())
        except:
            x= 0+0    
        return connections,G

    def _process_module(self, module):
        if module.key in self.visited:
            return
        
        f = os.path.join(self.tests_dir, "test_" + module.name)
        
        self.visited[module.key] = f

        if not hasattr(module, "test_dir"):
            setattr(module,"test_dir",f)
        
        print(module.name)
        # print(module.key)
        # try:
        #     print(module.cfg_bitcount)
        # except:
        #     x = 0+0
        # print(module.module_class)

        if module.module_class == ModuleClass.switch_box or module.module_class == ModuleClass.connection_box or module.module_class.is_cluster:
            stack,nx_graph = self.switch_connections(module)
            setattr(module,"stack",stack)
            # for edge in nx_graph.edges(data = True):
            #     print(edge)
            self.graphs[module.name] = {'graph':nx_graph,'module':module}
            # for conn in stack:
            #     for src_var,src,sink_var,sink,cfg_bits in conn:
            #         print("Conn: ",src," -> ",sink," : ",cfg_bits)
            #     print()
            
        else:
            connections,nx_graph = self.get_connections(module)
            setattr(module,"stack",[connections])
            # for edge in nx_graph.edges(data = True):
            #     print(edge)
            self.graphs[module.name] = {'graph':nx_graph,'module':module}

            # for src_var,src,sink_var,sink,cfg_bits in connections:
            #     print("Conn: ",src," -> ",sink," : ",cfg_bits)
        # setattr(module,"connections",connections)
        

        input_ports = self.get_input_ports(module)
        setattr(module,"input_ports",input_ports)
        
        clocks = self.get_clocks(module)
        # print(clocks)
        setattr(module,"clocks",clocks)
       
        setattr(module,"verilog_file",path.join(self.rtl_dir,module.name+".v"))
        
        primitives = self.get_primitives(module)
        setattr(module,"primitives",primitives)
        # for ins,names,offset in primitives:
        #     print(ins,offset)

        instance_files = []
        instance_files  = self.get_instance_file(module)
        setattr(module,"files",' '.join(instance_files))
        setattr(module,"top_level",module.name)
        
        if module.module_class.is_cluster:
            # print("cluster.tmpl.py")
            self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "cluster.tmpl.py")
        elif module.module_class == ModuleClass.switch:
            # print("switch.tmpl.py")
            self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "switch.tmpl.py")
        elif not module.module_class.is_primitive:
            # print("module.tmpl.py")
            self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "module.tmpl.py")
        else:
            # print(getattr(module,"test_python_template","module.tmpl.py"))
            # print(module.primitive_class)
            if module.primitive_class == PrimitiveClass.memory:
                self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "memory.tmpl.py")
            else:
                self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), getattr(module,"test_python_template","module.tmpl.py"))

        self.renderer.add_top_level_makefile(module, path.join(f,"Makefile"), "test_base.tmpl")
        self.renderer.add_top_level_python_test(module, path.join(f,"config.py"), "config.py")
        print()
        
        for instance in itervalues(module.instances):
            self._process_module(instance.model)

    def get_random_input_port(self,instance):
        input_pins = []
        for k,v in iteritems(instance.pins):
            if v.is_sink and not v.is_clock:
                input_pins.append(v)
        random.shuffle(input_pins)
        for sink in input_pins:
            for sink_net in sink:
                for src in NetUtils.get_source(sink_net):
                    print(src,sink_net)
                print()
        return input_pins[0]
        # print(input_pins)


    def path_L(self,top,G):
        # - - - - - - 
        # | | | | | -
        # | | | | | -
        # | | | | | -
        # | | | | | -
        # | | | | | -
        # - represents the path on the FPGA fabric
        height = top.height
        width = top.width
        path = []
        for i in range(1,width-1):
            path.append((i,1))
        for i in range(1,height-1):
            path.append((width-2,i))
        path.reverse()
            
        print(path)
        
        src = path[1]
        target = path[0]
        tile_src = [ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]),corner = 0)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]),corner = 2)._hierarchy[1],
                ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]),corner = 1)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]),corner = 3)._hierarchy[1],
                ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]))]
        tile_target = [ArrayBuilder.get_hierarchical_root(top, Position(target[0],target[1]),corner = 0)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(target[0],target[1]),corner = 2)._hierarchy[1],
                ArrayBuilder.get_hierarchical_root(top, Position(target[0],target[1]),corner = 1)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(target[0],target[1]),corner = 3)._hierarchy[1],
                ArrayBuilder.get_hierarchical_root(top, Position(target[0],target[1]))]
        
        connections = [[] for i in range(len(path)-1)]
        for node in G.nodes:
            if NetUtils._dereference(top, node).bus.instance in tile_target:
                loop_path = nx.shortest_path(G, target=node)
                for k1,v1 in iteritems(loop_path):
                    for v2 in v1:
                        if NetUtils._dereference(top, v2).bus.instance in tile_src:
                            connections[0].append((k1,node))
                            # print("source",NetUtils._dereference(top, k1).bus)
                            # print(NetUtils._dereference(top, v2))
                            # print("target ",NetUtils._dereference(top, node).bus)
                            # print()

        for i in range(2,len(path)):
            target = src
            tile_target = tile_src
            src = path[i]
            tile_src = [ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]),corner = 0)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]),corner = 2)._hierarchy[1],
                        ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]),corner = 1)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]),corner = 3)._hierarchy[1],
                        ArrayBuilder.get_hierarchical_root(top, Position(src[0],src[1]))]
        
            for node in G.nodes:
                if NetUtils._dereference(top, node).bus.instance in tile_target:
                    loop_path = nx.shortest_path(G, target=node)
                    for k1,v1 in iteritems(loop_path):
                        for v2 in v1:
                            if NetUtils._dereference(top, v2).bus.instance in tile_src:
                                connections[i-1].append((k1,node))        
        
        for i in range(1,len(connections)):
            print(NetUtils._dereference(top, connections[i][0][0]),NetUtils._dereference(top, connections[i][0][1])) 

        # for i in range(len(connections[0])):
        #     print(NetUtils._dereference(top, connections[0][i][0]))
        # print()
        # for j in range(len(connections[1])):
        #     print(NetUtils._dereference(top, connections[1][j][1]))
        
        for index in range(1,len(connections)):
            for i in range(len(connections[index-1])):
                for j in range(len(connections[index])):
                    # if connections[index-1][i][0] == connections[index][j][1]:
                    #     print("SAME PIN")
                    try: 
                        loop_path = nx.shortest_path(G, source = connections[index][j][1], target = connections[index-1][i][0])
                        # for x in paths:
                        #     print(x)
                        # for k1,v1 in iteritems(loop_path):
                        #     for v2 in v1:
                        #         print(NetUtils._dereference(top, k1),NetUtils._dereference(top, v2)) 
                        print(loop_path)
                    except:
                        temp = 0
                    if index==1:
                        print(NetUtils._dereference(top,  connections[index][j][1]),NetUtils._dereference(top, connections[index-1][i][0])) 
 

    @property
    def key(self):
        return "test.cocotb"

    @property
    def dependences(self):
        if self.view.is_logical:
            return ()
        else:
            return ()

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
        top = self.context.database[ModuleView.user,top.key]
        G = self.graphs['top']['graph']


        
        # tile_66_pins = []
        # for x in tile_66:
        #     for k,v in iteritems(x.pins):
        #         if v.model.direction.is_input and not v.is_clock:
        #             for net in v:
        #                 tile_66_pins.append(NetUtils._reference(net))
        # # print(tile_66)
        # for node in G.nodes:
        #     if NetUtils._dereference(top, node).bus.instance in tile_66:
        #         path = nx.shortest_path(G, target=node)
        #         for k1,v1 in iteritems(path):
        #             for v2 in v1:
        #                 if NetUtils._dereference(top, v2).bus.instance in tile_55:
        #                     print("source",NetUtils._dereference(top, k1))
        #                     print(NetUtils._dereference(top, v2))
        #                     print("target ",NetUtils._dereference(top, node))
        #                     print()

        tile_61 = [ArrayBuilder.get_hierarchical_root(top, Position(6,1),corner = 0)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(6,1),corner = 2)._hierarchy[1],
                    ArrayBuilder.get_hierarchical_root(top, Position(6,1),corner = 1)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(6,1),corner = 3)._hierarchy[1],
                    ArrayBuilder.get_hierarchical_root(top, Position(6,1))]
        tile_41 = [ArrayBuilder.get_hierarchical_root(top, Position(4,1),corner = 0)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(4,1),corner = 2)._hierarchy[1],
                    ArrayBuilder.get_hierarchical_root(top, Position(4,1),corner = 1)._hierarchy[1],ArrayBuilder.get_hierarchical_root(top, Position(4,1),corner = 3)._hierarchy[1],
                    ArrayBuilder.get_hierarchical_root(top, Position(4,1))]
        
        routes = [[]]

        for node in G.nodes:
            if NetUtils._dereference(top, node).bus.instance in tile_61:
                path = nx.shortest_path(G, target=node)
                for k1,v1 in iteritems(path):
                    for v2 in v1:
                        if NetUtils._dereference(top, v2).bus.instance in tile_41:
                            src = NetUtils._dereference(top, k1)
                            sink = NetUtils._dereference(top, node)
                            src_var_name = self.get_name(src) 
                            sink_var_name = self.get_name(sink) 
                                
                            routes[0].append((src_var_name,src,sink_var_name,sink)) #(src,sink)
                            # print("source",NetUtils._dereference(top, k1))
                            # print(NetUtils._dereference(top, v2))
                            # print("target ",NetUtils._dereference(top, node))
                            # print()

        top  = self.context._database[ModuleView.logical,top.key]
        # for x in top.primitives:
        #     print(x)
        for i,route in enumerate(routes):
            setattr(top,"route",route)
            setattr(top,"start_pin",route[0][1]) # For testing purposes only
            f = os.path.join(self.tests_dir, "test_route_" + str(i))
            cfg_bits = [] # the bits which will be used to set up the route
            for path in route:
                conn = NetUtils.get_connection(path[1].bus,path[3].bus)
                for bit in conn.get("cfg_bits",tuple()):
                    cfg_bits.append((path[1].bus.instance.name,path[1].bus.instance.cfg_bitoffset+bit))

            setattr(top,"cfg_bits",cfg_bits)
            self.renderer.add_top_level_python_test(top, os.path.join(f,"test.py"), "route.tmpl.py")
            self.renderer.add_top_level_makefile(top, os.path.join(f,"Makefile"), "test_base.tmpl")
            self.renderer.add_top_level_python_test(top, os.path.join(f,"config.py"), "config.py")
        
        # self.path_L(top,G)