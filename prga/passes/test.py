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
        
        print(module._instances.keys())
                    
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


    def get_heirarchy(self,module):
        heirarchy = []

        # This function must be made recursive
        # Send only the primitive heirarchy
        for instance in itervalues(module.instances):
            temp = self.get_heirarchy(instance.model)
            for x in temp:
                x.insert(0,str(module.name))
                heirarchy.append(x)
        
        # print(heirarchy)
        if len(heirarchy)==0:
            heirarchy.insert(0,[str(module.name)])
        
        return heirarchy
    
    def get_primitives(self,module):
        queue = []
        primitives = []

        # queue.append((module,[str(module.name)]))
        for instance in itervalues(module.instances):
            queue.append((instance,[str(instance.name)]))
        
        while len(queue)!=0 :
            curr_module, heirarchy = queue.pop(0)
            if curr_module.model.module_class.is_primitive:
                primitives.append((curr_module,heirarchy))
                continue

            for instance in itervalues(curr_module.model.instances):
                queue.append((instance,heirarchy+[str(instance.name)]))
        
        return primitives

    def _process_module(self, module):
        if module.key in self.visited:
            return
        
        f = os.path.join(self.tests_dir, "test_" + module.name)
        
        self.visited[module.key] = f

        if not hasattr(module, "test_dir"):
            setattr(module,"test_dir",f)
        
        print(module.name)
        print(module.view)
        print(module.instances.m)
        # print(f)
        # print(path.join(f,"Makefile"))
        # print(path.join(f,"test.py"))

        setattr(module,"verilog_file",path.join(self.rtl_dir,module.name+".v"))
        
        # print(module.verilog_file)

        primitives = self.get_primitives(module)
        
        if len(primitives)!=0:
            # print(module)
            # for a,b in primitives:
            #     print(a,b)
            #     print(a.model)
            # print(primitives)
            # for k,v in module._instances:
            #     print(k,v)

            test_dir = path.join(self.tests_dir,"test_" + module.name)

            # for x in self.get_instance_file(module):
            #     print(x)

            instance_files = ' '.join(self.get_instance_file(module))
            
            for primitive,heirarchy in primitives:
                # print(primitive)
                # print(heirarchy)
                primitive_test_dir = path.join(test_dir,"test_" + '_'.join(heirarchy))
                # Add instances_files for makefile
                setattr(primitive,"test_hierarchy",'.'.join(heirarchy)+'.')
                # print(instance_files)
                setattr(primitive,"files",instance_files)
                self.renderer.add_makefile(primitive, path.join(primitive_test_dir,"Makefile"), "test_base.tmpl")
                
                # Add heirarchy for python test files
                if len(heirarchy)!=0 :
                    setattr(primitive,"test_hierarchy",'.'.join(heirarchy)+'.')
                else:
                    setattr(primitive,"test_hierarchy",'.')

                setattr(primitive,"top_level",module.name)
                # print(primitive.test_hierarchy)
                # print(getattr(primitive.model, "test_python_template", "test_base.tmpl.py"))
                # print(primitive.files)
                # print(primitive.test_hierarchy)
                # print(primitive.top_level)
                # print(primitive_test_dir)
                # print()
                self.renderer.add_python_test(primitive, path.join(primitive_test_dir,"test.py"), getattr(primitive.model, "test_python_template", "test_base.tmpl.py"))
                
                self.renderer.add_python_test(primitive, path.join(primitive_test_dir,"config.py"), "config.py")
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
