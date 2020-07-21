# -*- encoding: ascii -*-
# Python 2 and 3 compatible
from __future__ import division, absolute_import, print_function
from prga.compatible import *

from .base import AbstractPass
from ..core.common import ModuleView
from ..util import Object, uno
from ..exception import PRGAInternalError
from collections import OrderedDict
import os
from os import path
from prga.compatible import *
from itertools import chain
from prga.netlist.net.util import NetUtils

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
        # for x in module._instances:
        #     print(x)
        #     print(module.instances[x])
        
        # print(module._instances.keys())
                    
        queue = []

        for temp in itervalues(module.instances):
            queue.append(temp.model)
        
        while len(queue)!=0:
            curr = queue.pop(0)
            curr_file = path.join(self.rtl_dir,curr.name+".v")
            if curr_file not in instance_files:
                instance_files.append(curr_file)
            for temp in itervalues(curr.instances):
                # print(temp)
                queue.append(temp.model)

            # if module.name == "clb":
            #     print(queue)
            # instance_files+= self.get_instance_file(temp.model)
                
        return instance_files


    # def get_heirarchy(self,module):
    #     heirarchy = []

    #     # This function must be made recursive
    #     # Send only the primitive heirarchy
    #     for instance in itervalues(module.instances):
    #         temp = self.get_heirarchy(instance.model)
    #         for x in temp:
    #             x.insert(0,str(module.name))
    #             heirarchy.append(x)
        
    #     # print(heirarchy)
    #     if len(heirarchy)==0:
    #         heirarchy.insert(0,[str(module.name)])
        
    #     return heirarchy
    
    def get_primitives(self,module):
        queue = []
        primitives = []

        # queue.append((module,[str(module.name)]))
        for instance in itervalues(module.instances):
            # print(instance)
            try:
                # print(instance.cfg_bitoffset)
                queue.append([instance,[str(instance.name)],instance.cfg_bitoffset])
            except:
                queue.append([instance,[str(instance.name)],0])
                # x = 0+0
        # print(queue)
        while len(queue)!=0:
            curr_module, heirarchy,offset = queue.pop(0)

            # if curr_module.model.module_class.is_cluster:
            #     primitives.append([curr_module,heirarchy,offset+curr_module.cfg_bitoffset])

            if curr_module.model.module_class.is_primitive:
                for k,v in iteritems(curr_module.pins):
                    setattr(v,'test_heirarchy','_'.join(heirarchy))
                    # v.test_heirarchy =0 
                    # print('_'.join(heirarchy))
                    # print(v)
                    print(v.test_heirarchy)

                if curr_module.model.primitive_class.is_flipflop:
                    D = curr_module.pins['D']
                    # print(D)
                    # if module._allow_multisource:
                    #     print(NetUtils.get_multisource(D))
                    #     print(NetUtils.get_multisource(D).test_heirarchy)
                    #     # print(NetUtils.get_multisource(D).parent)
                    # else:
                    #     print(NetUtils.get_source(D))
                    #     print(NetUtils.get_source(D).test_heirarchy)
                        # print(NetUtils.get_source(D).parent)
                    setattr(curr_module,"test_heirarchy",'_'.join(heirarchy))

                primitives.append([curr_module,heirarchy,offset])
            # if module.name == "clb" or module.name == "cluster":    
            # print(curr_module)
            # try:
            #     print(curr_module.cfg_bitoffset)
            # except:
            #     x = 0+0
            for instance in itervalues(curr_module.model.instances):
                # print(instance)
                try:
                # print(instance.cfg_bitoffset)
                    queue.append([instance,heirarchy+[str(instance.name)],offset+instance.cfg_bitcount])
                except:
                    queue.append([instance,heirarchy+[str(instance.name)],offset])
                # queue.append((instance,heirarchy+[str(instance.name)]))
        
        return primitives

    def _process_module(self, module):
        if module.key in self.visited:
            return
        
        f = os.path.join(self.tests_dir, "test_" + module.name)
        
        self.visited[module.key] = f

        if not hasattr(module, "test_dir"):
            setattr(module,"test_dir",f)
        
        print(module.name)
        # try:
        #     print(module.cfg_bitcount)
        # except:
        #     print("Does not have bitcount")
        clocks = []
        # if module.name == "cluster":
        for x in iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input and ipin.model.is_clock):
            if module._allow_multisource:
                # print(NetUtils.get_multisource(x))
                source = NetUtils.get_multisource(x)
                if source not in clocks:
                    # print(source.name)
                    clocks.append(source) 
            else:
                source = NetUtils.get_source(x)
                if source not in clocks:
                    # print(source.name)
                    clocks.append(source)
            # print()
        # print(clocks)

        setattr(module,"verilog_file",path.join(self.rtl_dir,module.name+".v"))
        setattr(module,"clocks",clocks)
        
        # print(module.verilog_file)

        primitives = self.get_primitives(module)
        # for sink_bus in chain(iter(oport for oport in itervalues(module.ports) if oport.direction.is_output),
        #              iter(ipin for instance in itervalues(module.instances) for ipin in itervalues(instance.pins) if ipin.model.direction.is_input)):
        #     for sink_net in sink_bus:
        #         if module._allow_multisource:
        #             for src_net in NetUtils.get_multisource(sink_net):
        #                 conn = NetUtils.get_connection(src_net,sink_net)
        #                 cfg_bits = conn.get("cfg_bits",tuple())
        #                 print("Conn::",src_net,"->",sink_net,"::",cfg_bits)
        setattr(module,"primitives",primitives)
        instance_files = ' '.join(self.get_instance_file(module))
        setattr(module,"files",instance_files)
        setattr(module,"top_level",module.name)
        
        self.renderer.add_top_level_python_test(module, path.join(f,"test.py"), "module.tmpl.py")
        self.renderer.add_top_level_makefile(module, path.join(f,"Makefile"), "test_base.tmpl")
        self.renderer.add_python_test(module, path.join(f,"config.py"), "config.py")
        for a,b,x in primitives:
            print(a,b,x)
        #     if a.model.module_class.is_primitive and a.model.primitive_class.is_flipflop:
        #         print(a)
        #         print(a.pins['D'])
        #         if module._allow_multisource:
        #             print(NetUtils.get_multisource(a.pins['D']))
        #             print(dir(NetUtils.get_multisource(a.pins['D'])))
        #         else:
        #             print(NetUtils.get_source(a.pins['D']))

        # if len(primitives)!=0:
        #     # print(module)
        #     for a,b,x in primitives:
        #         print(a,b,x)
        #     #     print(a.model)
        #     # print(primitives)
        #     # for k,v in module._instances:
        #     #     print(k,v)

        #     test_dir = path.join(self.tests_dir,"test_" + module.name)

        #     # for x in self.get_instance_file(module):
        #     #     print(x)

            
        #     for primitive,heirarchy,_ in primitives:
        #         # print(primitive)
        #         # print(heirarchy)
        #         primitive_test_dir = path.join(test_dir,"test_" + '_'.join(heirarchy))
        #         # Add instances_files for makefile
        #         setattr(primitive,"test_hierarchy",'.'.join(heirarchy)+'.')
        #         # print(instance_files)
        #         setattr(primitive,"files",instance_files)
        #         self.renderer.add_makefile(primitive, path.join(primitive_test_dir,"Makefile"), "test_base.tmpl")
                
        #         # Add heirarchy for python test files
        #         if len(heirarchy)!=0 :
        #             setattr(primitive,"test_hierarchy",'.'.join(heirarchy)+'.')
        #         else:
        #             setattr(primitive,"test_hierarchy",'.')

        #         setattr(primitive,"top_level",module.name)
        #         # print(primitive.test_hierarchy)
        #         # print(getattr(primitive.model, "test_python_template", "test_base.tmpl.py"))
        #         # print(primitive.files)
        #         # print(primitive.test_hierarchy)
        #         # print(primitive.top_level)
        #         # print(primitive_test_dir)
        #         # print()
        #         self.renderer.add_python_test(primitive, path.join(primitive_test_dir,"test.py"), getattr(primitive.model, "test_python_template", "test_base.tmpl.py"))
                
        #         self.renderer.add_python_test(primitive, path.join(primitive_test_dir,"config.py"), "config.py")
        print()

        for instance in itervalues(module.instances):
            self._process_module(instance.model)


    @property
    def key(self):
        return "test.cocotb"

    @property
    def dependences(self):
        if self.view.is_logical:
            return ("translation", "rtl.verilog")
        else:
            return ("translation", "materialization","rtl.verilog")

    @property
    def is_readonly_pass(self):
        return True

    def run(self, context, renderer=None):
        top = context.system_top
        self.renderer=renderer
        if top is None:
            raise PRGAInternalError("System top module is not set")
        if not hasattr(context.summary, "rtl"):
            context.summary.rtl = {}
        self.visited = context.summary.rtl["sources"] = {}
        context.summary.rtl["includes"] = [self.header_output_dir]
        self._process_module(top)
