# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import ModuleView,ModuleClass,PrimitiveClass
from ..util import Object, uno
from ..exception import PRGAInternalError
from collections import OrderedDict
import os
from os import path
from prga.compatible import *
from itertools import chain
from prga.netlist.net.util import NetUtils
import networkx as nx

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

    def switch_connections(self,module):
        # For modules using switches like cluster and switchbox
            module_temp = self.context.database[0,module.key]
            stack = [[] for i in range(module.cfg_bitcount+1)]
            # print(module.cfg_bitcount)
            # print(module.view)
            # print(stack)
            if module_temp._allow_multisource:
                for port in module_temp.ports.values():
                    if port.is_sink:
                        for sink in port:
                            for i,src in enumerate(NetUtils.get_multisource(sink)):
                                # if src.net_type == 0:
                                #     continue
                                src_var_name = "" 
                                sink_var_name = "" 
                                # if src_net.value is not None:
                                if src.bus.net_type == 1:
                                    src_var_name = src.bus.name+ "_" + str(src.index.start) + "_port"
                                else:
                                    src_var_name = src.bus.model.name+ "_" + str(src.index.start) + "_"+src.bus.instance.name
                                if sink.bus.net_type == 1:
                                    sink_var_name = sink.bus.name+ "_" + str(sink.index.start) + "_port"
                                else:
                                    sink_var_name = sink.bus.model.name+ "_" + str(sink.index.start) + "_"+sink.bus.instance.name
                                
                                conn = NetUtils.get_connection(src,sink)
                                stack[i].append((src_var_name,src,sink_var_name,sink,conn.get("cfg_bits",tuple())))
                            #     print("Conn: ",src," -> ",sink," : ",conn.get("cfg_bits",tuple()))
                            # print()
            else:
                for port in module_temp.ports.values():
                    if port.is_sink:
                        for sink in port:
                            for i,src in enumerate(NetUtils.get_source(sink)):
                                # if src.net_type == 0:
                                #     continue
                                src_var_name = "" 
                                sink_var_name = "" 
                                if src.bus.net_type == 1:
                                    src_var_name = src.bus.name+ "_" + str(src.index.start) + "_port"
                                else:
                                    src_var_name = src.bus.model.name+ "_" + str(src.index.start) + "_"+src.bus.instance.name
                                if sink.bus.net_type == 1:
                                    sink_var_name = sink.bus.name+ "_" + str(sink.index.start) + "_port"
                                else:
                                    sink_var_name = sink.bus.model.name+ "_" + str(sink.index.start) + "_"+sink.bus.instance.name
                                
                                conn = NetUtils.get_connection(src,sink)
                                stack[i].append((src_var_name,src,sink_var_name,sink,conn.get("cfg_bits",tuple())))
                            #     print("Conn: ",src," -> ",sink," : ",conn.get("cfg_bits",tuple()))
                            # print()
            
            while [] in stack:
                stack.remove([])
            # for conn in stack:
            #     for src_var,src,sink_var,sink,cfg_bits in conn:
            #         print("Conn: ",src," -> ",sink," : ",cfg_bits)
            #     print()
            
            return stack

    def get_connections(self,module):
        connections = []
        try:

            if module.module_class == ModuleClass.io_block or module.module_class == ModuleClass.switch:
                module = self.context.database[ModuleView.logical,module.key]
            else:
                module = self.context.database[ModuleView.user,module.key]


            if module._allow_multisource:
                for sink_bus in chain(iter(oport for oport in itervalues(module.ports) if oport.direction.is_output),
                            iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input and not ipin.model.is_clock)):
                    for sink_net in sink_bus:
                            for src_net in NetUtils.get_multisource(sink_net):
                                if src_net.net_type == 0:
                                    continue
                                # print(src_net,sink_net)
                                src_var_name = "" 
                                sink_var_name = "" 
                                # if src_net.value is not None:
                                if src_net.bus.net_type == 1:
                                    # print(src_net.bus.name,src_net.index.start,src_net.bus.name)
                                    src_var_name = src_net.bus.name+ "_" + str(src_net.index.start) + "_src"
                                else:
                                    # print(src_net.bus.model.name,src_net.index.start,src_net.bus.instance.name,src_net.bus.model.name)
                                    src_var_name = src_net.bus.model.name+ "_" + str(src_net.index.start) + "_" + src_net.bus.instance.name

                                if sink_net.bus.net_type == 1:
                                    sink_var_name = sink_net.bus.name+ "_" + str(sink_net.index.start) + "_sink"
                                    # print(sink_net.bus.name,sink_net.index.start,sink_net.bus.name)
                                else:
                                    sink_var_name = sink_net.bus.model.name+ "_" + str(sink_net.index.start) + "_"+ sink_net.bus.instance.name
                                    # print(sink_net.bus.model.name,sink_net.index.start,sink_net.bus.instance.name,sink_net.bus.model.name)
                                connections.append((src_var_name,src_net,sink_var_name,sink_net,tuple()))
                            #     print("Conn: ",src," -> ",sink," : ",conn.get("cfg_bits",tuple()))
                            # print()
            
            else:
                for sink_bus in chain(iter(oport for oport in itervalues(module.ports) if oport.direction.is_output),
                            iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input and not ipin.model.is_clock)):
                    for sink_net in sink_bus:
                            for src_net in NetUtils.get_source(sink_net):
                                if src_net.net_type == 0:
                                    continue
                                    # print(src_net,sink_net)
                                src_var_name = "" 
                                sink_var_name = "" 
                                if src_net.bus.net_type == 1:
                                    # print(src_net.bus.name,src_net.index.start,src_net.bus.name)
                                    src_var_name = src_net.bus.name+ "_" + str(src_net.index.start) + "_src"
                                else:
                                    # print(src_net.bus.model.name,src_net.index.start,src_net.bus.instance.name,src_net.bus.model.name)
                                    src_var_name = src_net.bus.model.name+ "_" + str(src_net.index.start) + "_" + src_net.bus.instance.name
                                if sink_net.bus.net_type == 1:
                                    sink_var_name = sink_net.bus.name+ "_" + str(sink_net.index.start) + "_sink"
                                    # print(sink_net.bus.name,sink_net.index.start,sink_net.bus.name)
                                else:
                                    sink_var_name = sink_net.bus.model.name+ "_" + str(sink_net.index.start) + "_"+ sink_net.bus.instance.name
                                    # print(sink_net.bus.model.name,sink_net.index.start,sink_net.bus.instance.name,sink_net.bus.model.name)
                                connections.append((src_var_name,src_net,sink_var_name,sink_net,tuple()))
                                print("Conn: ",src," -> ",sink," : ",conn.get("cfg_bits",tuple()))
                            print()
            
        except:
            x= 0+0    
        return connections

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
            stack = self.switch_connections(module)
            setattr(module,"stack",stack)
            # for conn in stack:
            #     for src_var,src,sink_var,sink,cfg_bits in conn:
            #         print("Conn: ",src," -> ",sink," : ",cfg_bits)
            #     print()
            
            # print(stack)
        # elif module.module_class == ModuleClass.io_block or module.module_class == ModuleClass.switch:
            # print(module.key)
            # connections = self.get_connections(module)
            # setattr(module,"stack",[connections])
            # for src_var,src,sink_var,sink,cfg_bits in connections:
            #     if src.bus.net_type == 2:
            #         if src.bus.instance.name == "io":
            #             print(src.bus.node[0])
                # print("Conn: ",src," -> ",sink," : ",cfg_bits) 
        else:
            connections = self.get_connections(module)
            setattr(module,"stack",[connections])
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
        for ins,names,offset in primitives:
            print(ins,offset)

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
        if top is None:
            raise PRGAInternalError("System top module is not set")
        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        self.visited = context.summary.rtl["sources"] = {}
        context.summary.rtl["includes"] = [self.header_output_dir]
        self._process_module(top)
